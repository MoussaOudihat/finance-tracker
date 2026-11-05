"""
notifier — Notifications Fintrack : TickTick, ntfy, Discord/Slack.

  • API utilisateur (jeton Supabase) : préférences, connexion TickTick
    (OAuth2), choix de la liste TickTick, envoi de test.
  • API interne (X-Internal-Token) : événements émis par finance-api
    (franchissement de budget 80 % / 100 %, dépense inhabituelle), avec
    anti-doublon.
  • Bilan IA du mois, envoyé à la demande de l'utilisateur (5 par jour).
  • Planificateur : rappel mensuel de saisie, le jour choisi.

Avec état (SQLite sur volume) et planificateur : 1 seul réplica.
"""
from __future__ import annotations

import calendar
import contextlib
import datetime as dt
import threading
from typing import Annotated, Literal, Optional, Union

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from fintrack_common.auth import TokenVerifier, User, internal_dependency, user_dependency
from fintrack_common.config import VERSION, env, env_int
from fintrack_common.fmt import fmt_eur, month_name, shift_month
from fintrack_common.http import RequestContextMiddleware, add_health_routes
from fintrack_common.logs import setup_logging

from .channels import DEFAULT_ALLOWED_HOSTS, ChannelError, Channels, Message, validate_user_url
from .store import Prefs, Store

log = setup_logging("notifier")



REPORTS_PER_DAY = 5


class PrefsIn(BaseModel):
    budget_alerts: bool = True
    unusual_alerts: Optional[bool] = None          # None = inchangé
    reminder_enabled: bool = False
    reminder_day: Annotated[int, Field(ge=1, le=28)] = 1
    # None = inchangé ; "" = supprimer ; sinon nouvelle URL (validée)
    ntfy_url: Optional[Annotated[str, Field(max_length=500)]] = None
    webhook_url: Optional[Annotated[str, Field(max_length=500)]] = None
    ticktick_project: Optional[Annotated[str, Field(max_length=64)]] = None


class CallbackIn(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=512)]
    state: Annotated[str, Field(min_length=1, max_length=128)]


class BudgetEvent(BaseModel):
    type: Literal["budget.threshold"]
    user_id: Annotated[str, Field(min_length=1, max_length=64)]
    email: str = ""
    year: int
    month: Annotated[int, Field(ge=1, le=12)]
    category: Annotated[str, Field(max_length=60)]
    threshold: Literal[80, 100]
    spent: float
    budget: float


class UnusualEvent(BaseModel):
    type: Literal["spending.unusual"]
    user_id: Annotated[str, Field(min_length=1, max_length=64)]
    email: str = ""
    year: int
    month: Annotated[int, Field(ge=1, le=12)]
    category: Annotated[str, Field(max_length=60)]
    spent: float
    average: float


EventIn = Annotated[Union[BudgetEvent, UnusualEvent], Field(discriminator="type")]


class ReportIn(BaseModel):
    year: Annotated[int, Field(ge=2000, le=2100)]
    month: Annotated[int, Field(ge=1, le=12)]
    text: Annotated[str, Field(min_length=1, max_length=6000)]


def dispatch(ch: Channels, p: Prefs, msg: Message, *, due: dt.date | None = None) -> list[str]:
    """Envoie sur tous les canaux configurés. Renvoie la liste des échecs
    (un canal en panne n'empêche pas les autres) ; ["aucun canal"] si rien
    n'est configuré."""
    failures = []
    targets = []
    if p.ticktick_token:
        targets.append(("TickTick", lambda: ch.ticktick_task(
            p.ticktick_token, p.ticktick_project, msg,
            due.strftime("%Y-%m-%dT09:00:00+0000") if due else None)))
    if p.ntfy_url:
        targets.append(("ntfy", lambda: ch.ntfy(p.ntfy_url, msg)))
    if p.webhook_url:
        targets.append(("webhook", lambda: ch.webhook(p.webhook_url, msg)))
    if not targets:
        return ["aucun canal"]
    for name, send in targets:
        try:
            send()
        except (ChannelError, httpx.HTTPError) as exc:
            log.warning("Canal %s en échec : %s", name, exc.__class__.__name__)
            failures.append(name)
    return failures


def delivered(failures: list[str], p: Prefs) -> bool:
    """Au moins un canal a reçu le message."""
    configured = sum(bool(x) for x in (p.ticktick_token, p.ntfy_url, p.webhook_url))
    return configured > 0 and len(failures) < configured


def create_app(*, verifier: Optional[TokenVerifier] = None, store: Optional[Store] = None,
               channels: Optional[Channels] = None, start_scheduler: bool = True) -> FastAPI:
    supabase_url = env("SUPABASE_URL", required=True)
    st = store or Store(env("NOTIFIER_DB_PATH", "/data/notifier.db"),
                        env("NOTIFIER_ENCRYPTION_KEY", required=True))
    hosts = tuple(h.strip().lower() for h in env("NOTIFIER_ALLOWED_HOSTS", "").split(",")
                  if h.strip()) or DEFAULT_ALLOWED_HOSTS
    ch = channels or Channels(
        httpx.Client(timeout=httpx.Timeout(10.0, connect=3.0), follow_redirects=False),
        ticktick_client_id=env("TICKTICK_CLIENT_ID", ""),
        ticktick_client_secret=env("TICKTICK_CLIENT_SECRET", ""),
        ticktick_redirect_uri=env("TICKTICK_REDIRECT_URI", ""),
        allowed_hosts=hosts,
    )
    stop = threading.Event()
    interval = env_int("NOTIFIER_SCHEDULER_INTERVAL", 3600)

    def run_reminders(today: dt.date | None = None) -> int:
        today = today or dt.date.today()
        py, pm = shift_month(today.year, today.month, -1)
        sent = 0
        for p in st.reminder_candidates(today.day):
            key = f"reminder:{p.user_id}:{today:%Y-%m}"
            if not st.mark_once(key):
                continue
            last = calendar.monthrange(today.year, today.month)[1]
            msg = Message(title=f"Fintrack : saisir les dépenses de {month_name(pm)} {py}",
                          body="Pensez à compléter revenus, dépenses et épargne du mois "
                               "écoulé, puis à le clôturer.", priority=3)
            failures = dispatch(ch, p, msg, due=today.replace(day=min(today.day + 3, last)))
            if delivered(failures, p):
                sent += 1
            else:
                st.unmark(key)       # retenté au prochain passage du planificateur
        return sent

    def scheduler_loop():
        while not stop.wait(interval):
            try:
                n = run_reminders()
                if n:
                    log.info("Rappels mensuels envoyés : %d", n)
            except Exception:
                log.exception("Planificateur en erreur")

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        t = None
        if start_scheduler:
            t = threading.Thread(target=scheduler_loop, name="scheduler", daemon=True)
            t.start()
        yield
        stop.set()
        st.close()

    app = FastAPI(title="fintrack-notifier", version=VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestContextMiddleware)
    app.state.verifier = verifier or TokenVerifier(supabase_url)
    app.state.internal_token = env("NOTIFIER_INTERNAL_TOKEN", required=True, min_len=32)
    app.state.run_reminders = run_reminders

    def _ready():
        try:
            return st.ping(), "ok"
        except Exception:
            return False, "store-unavailable"
    add_health_routes(app, _ready)
    current_user = user_dependency()
    internal = internal_dependency()

    # ── Préférences ──────────────────────────────────────────
    @app.get("/v1/prefs")
    def get_prefs(user: User = Depends(current_user)):
        return {**st.get(user.id).public(), "ticktick_available": ch.ticktick_enabled,
                "allowed_hosts": list(hosts)}

    @app.put("/v1/prefs")
    def put_prefs(body: PrefsIn, user: User = Depends(current_user)):
        p = st.get(user.id)
        p.email = user.email
        p.budget_alerts, p.reminder_enabled = body.budget_alerts, body.reminder_enabled
        if body.unusual_alerts is not None:
            p.unusual_alerts = body.unusual_alerts
        p.reminder_day = body.reminder_day
        try:
            if body.ntfy_url is not None:
                p.ntfy_url = validate_user_url(body.ntfy_url, hosts)
            if body.webhook_url is not None:
                p.webhook_url = validate_user_url(body.webhook_url, hosts)
        except ChannelError as exc:
            raise HTTPException(422, str(exc)) from exc
        if body.ticktick_project is not None:
            p.ticktick_project = body.ticktick_project
        st.save(p)
        return p.public()

    @app.post("/v1/test")
    def send_test(user: User = Depends(current_user)):
        p = st.get(user.id)
        if not (p.ticktick_token or p.ntfy_url or p.webhook_url):
            raise HTTPException(409, "Aucun canal configuré.")
        failures = dispatch(ch, p, Message("Fintrack : notification de test",
                                           "Vos notifications Fintrack fonctionnent."))
        return {"failures": failures}

    @app.post("/v1/report")
    def send_report(body: ReportIn, user: User = Depends(current_user)):
        """Bilan IA du mois, généré à la demande (le service n'a pas accès aux
        données hors requête de l'utilisateur : pas d'envoi planifié)."""
        p = st.get(user.id)
        if not (p.ticktick_token or p.ntfy_url or p.webhook_url):
            raise HTTPException(409, "Aucun canal de notification configuré.")
        day = dt.date.today().isoformat()
        key = next((f"report:{user.id}:{day}:{i}" for i in range(REPORTS_PER_DAY)
                    if st.mark_once(f"report:{user.id}:{day}:{i}")), None)
        if key is None:
            raise HTTPException(429, f"{REPORTS_PER_DAY} bilans envoyés aujourd'hui : "
                                     "réessayez demain.")
        msg = Message(title=f"Fintrack : bilan {month_name(body.month)} {body.year}",
                      body=body.text.replace("**", "").strip(), priority=0)
        failures = dispatch(ch, p, msg)
        if not delivered(failures, p):
            st.unmark(key)
            raise HTTPException(502, "Envoi impossible sur tous les canaux configurés.")
        return {"failures": failures}

    # ── TickTick (OAuth2) ────────────────────────────────────
    @app.post("/v1/ticktick/authorize")
    def ticktick_authorize(user: User = Depends(current_user)):
        if not ch.ticktick_enabled:
            raise HTTPException(503, "TickTick n'est pas configuré sur ce serveur.")
        return {"url": ch.ticktick_authorize_url(st.new_state(user.id))}

    @app.post("/v1/ticktick/callback")
    def ticktick_callback(body: CallbackIn, user: User = Depends(current_user)):
        # L'état OAuth est lié à l'utilisateur ET à usage unique (anti-CSRF).
        if not st.consume_state(body.state, user.id):
            raise HTTPException(400, "Lien de connexion TickTick expiré — recommencez.")
        try:
            token = ch.ticktick_exchange(body.code)
        except (ChannelError, httpx.HTTPError) as exc:
            raise HTTPException(502, "Connexion TickTick refusée.") from exc
        p = st.get(user.id)
        p.ticktick_token, p.email = token, user.email
        st.save(p)
        return p.public()

    @app.get("/v1/ticktick/projects")
    def ticktick_projects(user: User = Depends(current_user)):
        p = st.get(user.id)
        if not p.ticktick_token:
            raise HTTPException(409, "TickTick n'est pas connecté.")
        try:
            return ch.ticktick_projects(p.ticktick_token)
        except (ChannelError, httpx.HTTPError) as exc:
            raise HTTPException(502, str(exc) if isinstance(exc, ChannelError)
                                else "TickTick indisponible.") from exc

    @app.delete("/v1/ticktick")
    def ticktick_disconnect(user: User = Depends(current_user)):
        p = st.get(user.id)
        p.ticktick_token, p.ticktick_project = "", ""
        st.save(p)
        return p.public()

    # ── Événements internes ──────────────────────────────────
    @app.post("/internal/v1/events", dependencies=[Depends(internal)], status_code=202)
    def on_event(ev: EventIn = Body(...)):
        p = st.get(ev.user_id)
        if isinstance(ev, UnusualEvent):
            return on_unusual(ev, p)
        if not p.budget_alerts:
            return {"status": "disabled"}
        key = f"budget:{ev.user_id}:{ev.year}-{ev.month:02d}:{ev.category}:{ev.threshold}"
        if not st.mark_once(key):
            return {"status": "duplicate"}
        over = ev.threshold >= 100
        msg = Message(
            title=(f"Budget {ev.category} dépassé" if over
                   else f"Budget {ev.category} à {ev.threshold} %"),
            body=(f"{month_name(ev.month, capitalize=True)} {ev.year} : {fmt_eur(ev.spent)} "
                  f"dépensés sur un budget de {fmt_eur(ev.budget)}."),
            priority=5 if over else 3)
        failures = dispatch(ch, p, msg)
        if not delivered(failures, p):
            st.unmark(key)           # aucun canal n'a reçu l'alerte : pas de faux « envoyé »
            return {"status": "failed", "failures": failures}
        return {"status": "sent", "failures": failures}

    def on_unusual(ev: UnusualEvent, p: Prefs) -> dict:
        if not p.unusual_alerts:
            return {"status": "disabled"}
        key = f"unusual:{ev.user_id}:{ev.year}-{ev.month:02d}:{ev.category}"
        if not st.mark_once(key):
            return {"status": "duplicate"}
        msg = Message(
            title=f"Dépenses inhabituelles : {ev.category}",
            body=(f"{month_name(ev.month, capitalize=True)} {ev.year} : {fmt_eur(ev.spent)} "
                  f"dépensés en {ev.category}, contre {fmt_eur(ev.average)} en moyenne "
                  "sur les mois précédents."),
            priority=3)
        failures = dispatch(ch, p, msg)
        if not delivered(failures, p):
            st.unmark(key)
            return {"status": "failed", "failures": failures}
        return {"status": "sent", "failures": failures}

    return app


app = create_app() if not env("FINTRACK_NO_AUTOAPP") else None
