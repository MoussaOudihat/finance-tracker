"""
web — BFF (Backend For Frontend) de Fintrack : pages HTML, sessions,
orchestration des appels à finance-api, ai-service et notifier.

Sans état (sessions dans Redis) : réplicable (HPA). Ne touche jamais la
base directement.
"""
from __future__ import annotations

import contextvars
import hashlib
import html
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Annotated, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

import httpx
from fastapi import FastAPI, Form, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from fintrack_common.auth import secure_equals
from fintrack_common.config import VERSION, env, env_bool, env_int
from fintrack_common.fmt import MONTHS_FR as _MONTHS
from fintrack_common.fmt import fmt_eur, shift_month
from fintrack_common.http import RequestContextMiddleware, add_health_routes, service_client
from fintrack_common.logs import setup_logging
from fintrack_common.ratelimit import Counter, redis_from_url

from .backends import AuthExpired, BackendError, Backends, SupabaseAuth
from .session import SessionStore

log = setup_logging("web")
_HERE = os.path.dirname(os.path.abspath(__file__))

MONTHS_FR = [n.capitalize() for n in _MONTHS]
ASSET_LABEL = {"bourse": "Bourse / ETF / PEA", "immobilier": "Immobilier", "crypto": "Crypto",
               "or_metaux": "Or & Métaux", "compte": "Compte / Épargne", "autre": "Autre"}
LIABILITY_LABEL = {"voiture": "Prêt voiture", "conso": "Prêt conso/perso", "autre": "Autre"}
SECTIONS = {"depenses": ("expenses", "Dépenses"), "revenus": ("revenues", "Revenus"),
            "epargne": ("savings", "Épargne")}
COOKIE = "fintrack_sid"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; form-action 'self' https://ticktick.com; "
       "frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
LOGIN_MAX_PER_IP_ID = 5        # échecs / 15 min pour un couple (IP, identifiant)
LOGIN_MAX_PER_IP = 30          # échecs / 15 min pour une IP, tous comptes confondus
CHAT_MAX_MESSAGES = 20


class CategorizeReq(BaseModel):
    label: Annotated[str, Field(max_length=120)] = ""
    payee: Annotated[str, Field(max_length=60)] = ""


class _Redirect(Exception):
    def __init__(self, url: str):
        self.url = url


def render_ai_text(text: str) -> Markup:  # sûr : chaque ligne passe par html.escape()
    """Mise en forme MINIMALE et sûre d'une réponse IA : tout est échappé,
    seuls **gras** et les listes « - » sont rendus."""
    out, in_list = [], False
    for line in (text or "").splitlines():
        esc = html.escape(line.strip())
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        if esc.startswith(("- ", "• ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if esc:
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return Markup("".join(out))  # noqa: S704  # nosec B704


def _static_hashes(directory: str) -> dict[str, str]:
    """Empreinte (12 caractères hexadécimaux du SHA-256) de chaque fichier
    statique, calculée une fois au démarrage."""
    out = {}
    for name in sorted(os.listdir(directory)):
        full = os.path.join(directory, name)
        if os.path.isfile(full):
            with open(full, "rb") as f:
                out[name] = hashlib.sha256(f.read()).hexdigest()[:12]
    return out


def parse_amount(raw: str) -> str:
    """Normalise la saisie ('1 234,50') ; la validation (> 0, fini) est
    faite par finance-api (pydantic : NaN/inf refusés)."""
    return (raw or "").replace(" ", "").replace("\xa0", "").replace(" ", "") \
        .replace("€", "").replace(",", ".").strip()


def create_app(*, backends: Optional[Backends] = None, sessions: Optional[SessionStore] = None,
               counter: Optional[Counter] = None) -> FastAPI:
    supabase_url = env("SUPABASE_URL", required=True)
    cookie_secure = env_bool("FINTRACK_COOKIE_SECURE", True)
    redis = redis_from_url(env("REDIS_URL", ""))
    sessions = sessions or SessionStore(
        env("SESSION_ENCRYPTION_KEY", required=True), redis,
        idle_ttl=env_int("SESSION_IDLE_TTL", 3600),
        absolute_ttl=env_int("SESSION_ABSOLUTE_TTL", 12 * 3600))
    limiter = counter or Counter(redis, prefix="login")
    if backends is None:
        def _opt(name):
            url = env(name, "")
            return service_client(url, timeout=60.0) if url else None
        backends = Backends(
            SupabaseAuth(httpx.Client(base_url=supabase_url.rstrip("/"), timeout=10.0,
                                      follow_redirects=False),
                         env("SUPABASE_ANON_KEY", required=True)),
            service_client(env("FINANCE_API_URL", required=True)),
            _opt("AI_SERVICE_URL"), _opt("NOTIFIER_URL"))

    app = FastAPI(title="fintrack-web", version=VERSION,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestContextMiddleware, csp=CSP, static_prefix="/static/")
    # Pool partagé (borné) pour les appels parallèles vers les services
    pool = ThreadPoolExecutor(max_workers=env_int("WEB_BACKEND_PARALLELISM", 16),
                              thread_name_prefix="backend")
    app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")
    templates = Jinja2Templates(directory=os.path.join(_HERE, "templates"))
    templates.env.filters["eur"] = fmt_eur
    asset_hashes = _static_hashes(os.path.join(_HERE, "static"))

    def static(path: str) -> str:
        """URL d'un fichier statique avec l'empreinte de son contenu : le
        navigateur peut le garder en cache un an, l'URL change dès que le
        fichier change (aucun risque de CSS périmé après une mise à jour)."""
        return f"/static/{path}?v={asset_hashes[path]}"

    templates.env.globals.update(VERSION=VERSION, MONTHS_FR=MONTHS_FR, static=static,
                                 ASSET_LABEL=ASSET_LABEL, LIABILITY_LABEL=LIABILITY_LABEL)
    app.state.sessions = sessions
    app.state.backends = backends

    def _ready():
        try:
            return sessions.ping(), "ok"
        except Exception:
            return False, "session-store-unavailable"
    add_health_routes(app, _ready)

    # ── Session / rendu ──────────────────────────────────────
    def load(request: Request) -> tuple[str, dict]:
        sid = request.cookies.get(COOKIE)
        sess = sessions.get(sid)
        if sess is None:
            raise _Redirect("/connexion")
        return sid, sess

    def call(sid: str, sess: dict, service: str, method: str, path: str, **kw):
        if backends.fresh_token(sess):
            sessions.update(sid, access_token=sess["access_token"],
                            refresh_token=sess["refresh_token"], expires_at=sess["expires_at"])
        return backends.call(sess, service, method, path, **kw)

    def call_parallel(sid: str, sess: dict, *specs: tuple) -> list:
        """Plusieurs appels de LECTURE indépendants, en parallèle (une page
        n'attend plus la somme des latences). Le jeton est rafraîchi une seule
        fois avant (pas de rotation concurrente) ; le contexte de la requête
        (request_id) est copié dans chaque thread. Chaque spec :
        (service, méthode, chemin) ou (service, méthode, chemin, kwargs)."""
        if backends.fresh_token(sess):
            sessions.update(sid, access_token=sess["access_token"],
                            refresh_token=sess["refresh_token"], expires_at=sess["expires_at"])
        futures = [
            pool.submit(contextvars.copy_context().run, backends.call, sess, *spec[:3],
                        **(spec[3] if len(spec) > 3 else {}))
            for spec in specs
        ]
        return [f.result() for f in futures]     # 1re erreur relancée telle quelle

    def flash(sid: str, sess: dict, message: str, kind: str = "ok") -> None:
        sess["flash"] = {"message": message, "kind": kind}
        sessions.update(sid, flash=sess["flash"])

    def render(request: Request, name: str, sid: str | None, sess: dict | None,
               status_code: int = 200, **ctx) -> HTMLResponse:
        if sess is not None:
            ctx.setdefault("flash", sess.pop("flash", None))
            sessions.update(sid, flash=None)     # consomme le message, prolonge la session
            ctx["csrf"] = sess["csrf"]
            ctx["user_email"] = sess.get("email", "")
        ctx.setdefault("active", "")
        return templates.TemplateResponse(request, name, ctx, status_code=status_code)

    def redirect(url: str) -> RedirectResponse:
        """Redirection LOCALE uniquement (anti open-redirect) : un chemin
        absolu du site, jamais « //hôte » ni une barre oblique inverse."""
        if not url.startswith("/") or url.startswith(("//", "/\\")):
            url = "/"
        return RedirectResponse(url, status_code=303)

    def ticktick_handoff(request: Request, sid: str, sess: dict, url: str) -> HTMLResponse:
        """Seule navigation externe de l'application : l'autorisation OAuth
        TickTick, validée strictement (https, hôte exact, chemin exact).

        Pas de 303 vers TickTick : CSP3 applique `form-action` à TOUTE la
        chaîne de redirections qui suit un POST, et TickTick redirige ensuite
        vers des pages (connexion, consentement…) hors de notre liste — le
        navigateur bloquait silencieusement la navigation. On renvoie donc une
        page 200 qui part vers TickTick par meta refresh (+ lien de secours) :
        cette navigation n'est plus une soumission de formulaire, la CSP reste
        inchangée et sans script inline."""
        p = urlsplit(url)
        if p.scheme != "https" or p.netloc != "ticktick.com" or p.path != "/oauth/authorize":
            raise BackendError(502, "URL d'autorisation inattendue.")
        return render(request, "ticktick_redirect.html", sid, sess, active="parametres",
                      authorize_url=url)

    def check_csrf(sess: dict, token: str) -> None:
        if not secure_equals(token, sess.get("csrf", "")):
            raise BackendError(400, "Formulaire expiré — rechargez la page et réessayez.")

    def back_url(request: Request, default: str = "/") -> str:
        ref = request.headers.get("referer", "")
        p = urlsplit(ref)
        if p.netloc and p.netloc == request.url.netloc and p.path.startswith("/"):
            return p.path + (f"?{p.query}" if p.query else "")
        return default

    def month_params(sid, sess, y: Optional[str], m: Optional[str]) -> tuple[int, int]:
        if y is None and m is None:
            last = call(sid, sess, "finance", "GET", "/v1/last-month")
            if last:
                return last["year"], last["month"]
            t = date.today()
            return t.year, t.month
        try:
            yi, mi = int(y or ""), int(m or "")
        except ValueError:
            yi = mi = 0
        if not (2000 <= yi <= 2100 and 1 <= mi <= 12):
            raise BackendError(400, "Mois invalide.")
        return yi, mi

    @app.exception_handler(_Redirect)
    async def _on_redirect(request, exc: _Redirect):
        return redirect(exc.url)

    @app.exception_handler(AuthExpired)
    async def _on_auth_expired(request: Request, exc):
        sessions.delete(request.cookies.get(COOKIE))
        resp = redirect("/connexion")
        resp.delete_cookie(COOKIE)
        return resp

    @app.exception_handler(BackendError)
    async def _on_backend_error(request: Request, exc: BackendError):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.message}, status_code=exc.status)
        sid = request.cookies.get(COOKIE)
        sess = sessions.get(sid)
        if sess is None:
            return redirect("/connexion")
        if exc.message == "Mois invalide.":
            flash(sid, sess, exc.message, "error")
            return redirect(request.url.path)
        if request.method == "GET":
            # Afficher l'erreur sur place : rediriger vers la page précédente
            # pourrait reproduire la même erreur et boucler indéfiniment.
            return render(request, "error.html", sid, sess,
                          status_code=exc.status if 400 <= exc.status < 600 else 502,
                          active="erreur", message=exc.message)
        flash(sid, sess, exc.message, "error")   # POST : retour au formulaire
        return redirect(back_url(request))

    # ── Connexion ────────────────────────────────────────────
    def client_ip(request: Request) -> str:
        # request.client vient d'uvicorn --proxy-headers, qui ne fait confiance
        # à X-Forwarded-For QUE depuis FORWARDED_ALLOW_IPS (le proxy d'entrée).
        return request.client.host if request.client else "?"

    @app.get("/connexion", response_class=HTMLResponse)
    def login_form(request: Request):
        if sessions.get(request.cookies.get(COOKIE)):
            return redirect("/")
        # Jeton CSRF de pré-session (cookie dédié, SameSite=Strict)
        pre = request.cookies.get("fintrack_pre") or os.urandom(24).hex()
        resp = render(request, "login.html", None, None, csrf=pre)
        resp.set_cookie("fintrack_pre", pre, httponly=True, secure=cookie_secure,
                        samesite="strict", max_age=1800)
        return resp

    @app.post("/connexion")
    def login(request: Request, identifier: str = Form(""), password: str = Form(""),
              csrf: str = Form("")):
        pre = request.cookies.get("fintrack_pre", "")

        def fail(msg: str, code: int):
            return render(request, "login.html", None, None, code, csrf=pre or "",
                          error=msg, identifier=identifier[:120])

        if not pre or not secure_equals(csrf, pre):
            return fail("Formulaire expiré — réessayez.", 400)
        ip, ident = client_ip(request), identifier.strip().lower()[:120]
        if (limiter.get("ipid", ip, ident) >= LOGIN_MAX_PER_IP_ID
                or limiter.get("ip", ip) >= LOGIN_MAX_PER_IP):
            return fail("Trop de tentatives. Réessayez dans quelques minutes.", 429)
        if not ident or not password:
            return fail("Email et mot de passe requis.", 400)
        try:
            supa = backends.auth.sign_in(ident, password)
        except httpx.HTTPError:
            return fail("Service d'authentification indisponible.", 503)
        if supa is None:
            limiter.incr("ipid", ip, ident, window=900)
            limiter.incr("ip", ip, window=900)
            log.info("Connexion refusée")
            return fail("Email ou mot de passe incorrect.", 401)
        limiter.reset("ipid", ip, ident)
        sid = sessions.create(supa)      # nouvel identifiant : anti-fixation
        resp = redirect("/")
        resp.set_cookie(COOKIE, sid, httponly=True, secure=cookie_secure, samesite="lax",
                        max_age=sessions.absolute_ttl, path="/")
        resp.delete_cookie("fintrack_pre")
        return resp

    @app.post("/deconnexion")
    def logout(request: Request, csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        backends.auth.sign_out(sess["access_token"])     # scope local
        sessions.delete(sid)                              # révocation réelle
        resp = redirect("/connexion")
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # ── Tableau de bord ──────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        s, hist, pat = call_parallel(
            sid, sess,
            ("finance", "GET", f"/v1/months/{yy}/{mm}/summary"),
            ("finance", "GET", "/v1/history", {"params": {"limit": 12}}),
            ("finance", "GET", "/v1/patrimoine"))
        return render(request, "dashboard.html", sid, sess, active="dashboard", y=yy, m=mm,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1), s=s, history=hist,
                      closed=s["closed"], net_worth=pat["net_worth"],
                      max_cat=max((c["total"] for c in s["by_category"]), default=0) or 1,
                      max_hist=max((max(h["rev"], h["exp"]) for h in hist), default=0) or 1)

    # ── Saisies ──────────────────────────────────────────────
    def entry_payload(kind, amount, label, category_id, payee, source, account) -> dict:
        p = {"amount": parse_amount(amount), "label": label}
        if kind == "expenses":
            try:
                p.update(category_id=int(category_id), payee=payee)
            except ValueError:
                raise BackendError(422, "Catégorie invalide.") from None
        elif kind == "revenues":
            p["source"] = source
        else:
            p["account"] = account
        return p

    @app.get("/patrimoine", response_class=HTMLResponse)
    def patrimoine(request: Request):
        sid, sess = load(request)
        pat = call(sid, sess, "finance", "GET", "/v1/patrimoine")
        return render(request, "patrimoine.html", sid, sess, active="patrimoine", pat=pat,
                      max_type=max((t["total"] for t in pat["by_type"]), default=0) or 1)

    @app.get("/budgets", response_class=HTMLResponse)
    def budgets(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        s, cats = call_parallel(sid, sess,
                                ("finance", "GET", f"/v1/months/{yy}/{mm}/summary"),
                                ("finance", "GET", "/v1/categories"))
        budgeted = {b["category"] for b in s["budgets"]}
        spent = {c["name"]: c["total"] for c in s["by_category"]}
        return render(request, "budgets.html", sid, sess, active="budgets", y=yy, m=mm,
                      prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1), s=s, closed=False,
                      unbudgeted=[{"name": c["name"], "spent": spent.get(c["name"], 0.0)}
                                  for c in cats if c["name"] not in budgeted])

    @app.post("/budgets")
    def set_budget(request: Request, y: int = Form(...), m: int = Form(...),
                   category: str = Form(""), amount: str = Form("0"), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        call(sid, sess, "finance", "PUT", f"/v1/budgets/{y}/{m}",
             json={"category": category, "amount": parse_amount(amount) or "0"})
        flash(sid, sess, "Budget enregistré.")
        return redirect(f"/budgets?y={y}&m={m}")

    @app.post("/budgets/copier")
    def copy_budgets(request: Request, y: int = Form(...), m: int = Form(...),
                     csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        n = call(sid, sess, "finance", "POST", f"/v1/budgets/{y}/{m}/copy-previous")["copied"]
        flash(sid, sess, f"{n} budget(s) copié(s) depuis le mois précédent.")
        return redirect(f"/budgets?y={y}&m={m}")

    # ── IA ───────────────────────────────────────────────────
    def ai_state(sid, sess) -> dict:
        try:
            return call(sid, sess, "ai", "GET", "/v1/providers")
        except BackendError:
            return {"providers": [], "daily_limit": 0, "remaining": 0}

    @app.get("/ia", response_class=HTMLResponse)
    def ia_page(request: Request, y: Optional[str] = None, m: Optional[str] = None):
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        st = ai_state(sid, sess)
        chat = sess.get("chat", [])
        return render(request, "ia.html", sid, sess, active="ia", y=yy, m=mm, ai=st,
                      provider=sess.get("ai_provider") or (st["providers"] or ["claude"])[0],
                      consent=sess.get("ai_consent", False),
                      insight=render_ai_text(sess.get("insight", {}).get("text", "")),
                      insight_meta=sess.get("insight", {}),
                      chat=[{"role": c["role"], "html": render_ai_text(c["content"])
                             if c["role"] == "assistant" else c["content"]} for c in chat])

    def ai_common(sess, provider: str, consent: str) -> str:
        if provider not in ("claude", "gemini"):
            raise BackendError(422, "Fournisseur IA inconnu.")
        if consent != "1" and not sess.get("ai_consent"):
            raise BackendError(400, "Cochez la case de consentement avant d'utiliser l'IA.")
        sess["ai_consent"] = True
        sess["ai_provider"] = provider
        return provider

    @app.post("/ia/analyse")
    def ia_insights(request: Request, y: int = Form(...), m: int = Form(...),
                    months: int = Form(3), provider: str = Form("claude"),
                    consent: str = Form(""), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        provider = ai_common(sess, provider, consent)
        res = call(sid, sess, "ai", "POST", "/v1/insights", timeout=120.0,
                   json={"provider": provider, "year": y, "month": m,
                         "months": max(1, min(months, 12))})
        sessions.update(sid, ai_consent=True, ai_provider=provider,
                        insight={"text": res["text"], "provider": provider,
                                 "period": f"{MONTHS_FR[m - 1]} {y}", "months": months})
        return redirect(f"/ia?y={y}&m={m}")

    @app.post("/ia/chat")
    def ia_chat(request: Request, y: int = Form(...), m: int = Form(...),
                question: str = Form(""), provider: str = Form("claude"),
                consent: str = Form(""), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        provider = ai_common(sess, provider, consent)
        q = question.strip()[:2000]
        if not q:
            raise BackendError(422, "Posez une question.")
        history = (sess.get("chat", []) + [{"role": "user", "content": q}])[-CHAT_MAX_MESSAGES:]
        if history[0]["role"] != "user":
            history = history[1:]
        res = call(sid, sess, "ai", "POST", "/v1/chat", timeout=120.0,
                   json={"provider": provider, "year": y, "month": m, "messages": history})
        sessions.update(sid, ai_consent=True, ai_provider=provider,
                        chat=(history + [{"role": "assistant", "content": res["text"]}])[-CHAT_MAX_MESSAGES:])
        return redirect(f"/ia?y={y}&m={m}#chat")

    @app.post("/ia/chat/effacer")
    def ia_chat_clear(request: Request, y: int = Form(...), m: int = Form(...),
                      csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        sessions.update(sid, chat=[])
        return redirect(f"/ia?y={y}&m={m}#chat")

    @app.post("/api/categorize")
    def api_categorize(request: Request, body: CategorizeReq,
                       x_csrf_token: str = Header("")):
        sid = request.cookies.get(COOKIE)
        sess = sessions.get(sid)
        if sess is None:
            return JSONResponse({"detail": "Session expirée."}, status_code=401)
        check_csrf(sess, x_csrf_token)
        if not sess.get("ai_consent"):
            raise BackendError(400, "Activez d'abord l'IA depuis la page « Assistant IA ».")
        return call(sid, sess, "ai", "POST", "/v1/categorize", timeout=60.0,
                    json={"provider": sess.get("ai_provider") or "claude",
                          "label": body.label, "payee": body.payee})

    # ── Paramètres / notifications ───────────────────────────
    @app.get("/parametres", response_class=HTMLResponse)
    def settings_page(request: Request):
        sid, sess = load(request)
        try:
            prefs = call(sid, sess, "notifier", "GET", "/v1/prefs")
        except BackendError as exc:
            prefs, err = None, exc.message
        else:
            err = None
        projects = []
        if prefs and prefs.get("ticktick_connected"):
            try:
                projects = call(sid, sess, "notifier", "GET", "/v1/ticktick/projects")
            except BackendError as exc:
                err = exc.message
        return render(request, "settings.html", sid, sess, active="parametres", prefs=prefs,
                      projects=projects, notifier_error=err)

    @app.post("/parametres/notifications")
    def save_prefs(request: Request, budget_alerts: str = Form(""),
                   reminder_enabled: str = Form(""), reminder_day: int = Form(1),
                   ntfy_url: str = Form(""), webhook_url: str = Form(""),
                   clear_ntfy: str = Form(""), clear_webhook: str = Form(""),
                   ticktick_project: Optional[str] = Form(None), csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        body = {"budget_alerts": budget_alerts == "1",
                "reminder_enabled": reminder_enabled == "1",
                "reminder_day": max(1, min(reminder_day, 28)),
                # champ vide = inchangé (les URLs enregistrées ne sont jamais réaffichées)
                "ntfy_url": "" if clear_ntfy else (ntfy_url.strip() or None),
                "webhook_url": "" if clear_webhook else (webhook_url.strip() or None)}
        if ticktick_project is not None:
            body["ticktick_project"] = ticktick_project
        call(sid, sess, "notifier", "PUT", "/v1/prefs", json=body)
        flash(sid, sess, "Préférences de notification enregistrées.")
        return redirect("/parametres")

    @app.post("/parametres/test")
    def test_notif(request: Request, csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        res = call(sid, sess, "notifier", "POST", "/v1/test")
        if res["failures"]:
            flash(sid, sess, "Échec sur : " + ", ".join(res["failures"]), "error")
        else:
            flash(sid, sess, "Notification de test envoyée.")
        return redirect("/parametres")

    @app.post("/parametres/ticktick/connecter")
    def ticktick_connect(request: Request, csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        url = call(sid, sess, "notifier", "POST", "/v1/ticktick/authorize")["url"]
        return ticktick_handoff(request, sid, sess, url)

    @app.get("/parametres/ticktick/callback")
    def ticktick_callback(request: Request, code: str = "", state: str = "",
                          error: str = ""):
        sid, sess = load(request)
        if error or not code or not state:
            flash(sid, sess, "Connexion TickTick annulée.", "error")
            return redirect("/parametres")
        call(sid, sess, "notifier", "POST", "/v1/ticktick/callback",
             json={"code": code[:512], "state": state[:128]})
        flash(sid, sess, "TickTick connecté. Choisissez la liste où créer les tâches.")
        return redirect("/parametres")

    @app.post("/parametres/ticktick/deconnecter")
    def ticktick_disconnect(request: Request, csrf: str = Form("")):
        sid, sess = load(request)
        check_csrf(sess, csrf)
        call(sid, sess, "notifier", "DELETE", "/v1/ticktick")
        flash(sid, sess, "TickTick déconnecté.")
        return redirect("/parametres")

    # ── Saisies (routes génériques en dernier) ───────────────
    @app.get("/{section}", response_class=HTMLResponse)
    def list_entries(request: Request, section: str, y: Optional[str] = None,
                     m: Optional[str] = None):
        if section not in SECTIONS:
            return Response(status_code=404)
        kind, title = SECTIONS[section]
        sid, sess = load(request)
        yy, mm = month_params(sid, sess, y, m)
        if kind == "expenses":
            data, cats, payees = call_parallel(
                sid, sess,
                ("finance", "GET", f"/v1/months/{yy}/{mm}/entries"),
                ("finance", "GET", "/v1/categories"),
                ("finance", "GET", "/v1/payees"))
        else:
            data, cats, payees = call(sid, sess, "finance", "GET", f"/v1/months/{yy}/{mm}/entries"), [], []
        rows = data[kind]
        return render(request, "entries.html", sid, sess, active=section, section=section,
                      title=title, y=yy, m=mm, prev=shift_month(yy, mm, -1), next=shift_month(yy, mm, 1),
                      rows=rows, total=sum(r["amount"] for r in rows), categories=cats,
                      payees=payees, closed=data["closed"],
                      ai_enabled=bool(sess.get("ai_consent")))

    @app.post("/{section}")
    def add_entry(request: Request, section: str, y: int = Form(...), m: int = Form(...),
                  amount: str = Form(""), label: str = Form(""), category_id: str = Form(""),
                  payee: str = Form(""), source: str = Form(""), account: str = Form(""),
                  csrf: str = Form("")):
        if section not in SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        kind = SECTIONS[section][0]
        yy, mm = month_params(sid, sess, str(y), str(m))
        body = entry_payload(kind, amount, label, category_id, payee, source, account)
        row = call(sid, sess, "finance", "POST", f"/v1/{kind}", json={**body, "year": yy, "month": mm})
        msg = {"expenses": "Dépense ajoutée.", "revenues": "Revenu ajouté.",
               "savings": "Épargne ajoutée."}[kind]
        if kind == "savings" and row.get("linked_asset_name"):
            msg += f" Compte « {row['linked_asset_name']} » mis à jour dans le patrimoine."
        flash(sid, sess, msg)
        return redirect(f"/{section}?y={yy}&m={mm}")

    @app.get("/{section}/{entry_id}/modifier", response_class=HTMLResponse)
    def edit_form(request: Request, section: str, entry_id: int):
        if section not in SECTIONS:
            return Response(status_code=404)
        kind, title = SECTIONS[section]
        sid, sess = load(request)
        if kind == "expenses":
            entry, cats = call_parallel(sid, sess,
                                        ("finance", "GET", f"/v1/entries/{kind}/{entry_id}"),
                                        ("finance", "GET", "/v1/categories"))
        else:
            entry, cats = call(sid, sess, "finance", "GET", f"/v1/entries/{kind}/{entry_id}"), []
        return render(request, "edit.html", sid, sess, active=section, section=section,
                      title=title, entry=entry, categories=cats, closed=entry["closed"])

    @app.post("/{section}/{entry_id}/modifier")
    def edit_entry(request: Request, section: str, entry_id: int, amount: str = Form(""),
                   label: str = Form(""), category_id: str = Form(""), payee: str = Form(""),
                   source: str = Form(""), account: str = Form(""), csrf: str = Form("")):
        if section not in SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        kind = SECTIONS[section][0]
        body = entry_payload(kind, amount, label, category_id, payee, source, account)
        entry = call(sid, sess, "finance", "GET", f"/v1/entries/{kind}/{entry_id}")
        call(sid, sess, "finance", "PUT", f"/v1/{kind}/{entry_id}", json=body)
        flash(sid, sess, "Modification enregistrée.")
        return redirect(f"/{section}?y={entry['year']}&m={entry['month']}")

    @app.post("/{section}/{entry_id}/supprimer")
    def delete_entry(request: Request, section: str, entry_id: int, csrf: str = Form("")):
        if section not in SECTIONS:
            return Response(status_code=404)
        sid, sess = load(request)
        check_csrf(sess, csrf)
        res = call(sid, sess, "finance", "DELETE", f"/v1/{SECTIONS[section][0]}/{entry_id}")
        flash(sid, sess, "Élément supprimé.")
        return redirect(f"/{section}?y={res['year']}&m={res['month']}")

    return app


app = create_app() if not env("FINTRACK_NO_AUTOAPP") else None
