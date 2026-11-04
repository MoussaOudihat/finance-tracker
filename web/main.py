"""
web/main.py — Application FastAPI de Fintrack (interface web).

Lancement local :
    uvicorn web.main:app --port 8000
Conteneur : voir Dockerfile (uvicorn derrière l'Ingress Kubernetes).

Pages : tableau de bord, dépenses, revenus, épargne (saisie / modification /
suppression), patrimoine (lecture). Toutes les données passent par
database.Database, exactement comme l'application desktop.
"""
from __future__ import annotations

import contextlib
import os
from datetime import date
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import APP_VERSION, MONTHS_FR, ASSET_LABEL, LIABILITY_LABEL
from logger import log
from utils import fmt_amount, parse_amount
from web.security import (
    LoginRateLimiter, SecurityHeadersMiddleware, csrf_token, csrf_valid,
)
from web.settings import WebSettings
from web.workspace import Workspace, WorkspaceManager

_HERE = os.path.dirname(os.path.abspath(__file__))


class _NotAuthenticated(Exception):
    pass


class _BadRequest(Exception):
    pass


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _month_params(ws: Workspace, y: Optional[int], m: Optional[int]) -> tuple[int, int]:
    """Mois demandé, sinon dernier mois avec données, sinon mois courant."""
    if y and m and 2000 <= y <= 2100 and 1 <= m <= 12:
        return y, m
    last = ws.db.get_last_month_with_data()
    if last:
        return last
    today = date.today()
    return today.year, today.month


def _shift(y: int, m: int, delta: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + delta
    return idx // 12, idx % 12 + 1


def _parse_positive_amount(raw: str) -> float:
    amount = parse_amount(raw or "")
    if amount <= 0 or amount > 1e9:
        raise _BadRequest("Montant invalide : saisissez un nombre positif (ex. 42,50).")
    return round(amount, 2)


def _clean(text: str, max_len: int = 120) -> str:
    return (text or "").strip()[:max_len]


def create_app(settings: Optional[WebSettings] = None,
               manager: Optional[WorkspaceManager] = None) -> FastAPI:
    settings = settings or WebSettings.from_env()
    manager = manager or WorkspaceManager(
        settings.users_dir, settings.sync_delay, settings.idle_timeout
    )
    limiter = LoginRateLimiter()

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        os.makedirs(settings.users_dir, exist_ok=True)
        manager.start_reaper()
        log.info("=== Fintrack web v%s — démarrage (auth=%s) ===",
                 APP_VERSION, settings.auth_mode)
        yield
        log.info("[Web] Arrêt : synchronisation finale des espaces ouverts…")
        manager.close_all()

    app = FastAPI(title="Fintrack", version=APP_VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.cookie_secure)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="fintrack_session",
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=settings.cookie_secure,
    )
    app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")

    templates = Jinja2Templates(directory=os.path.join(_HERE, "templates"))
    templates.env.filters["eur"] = lambda v, sign=False: fmt_amount(float(v or 0), sign)
    templates.env.globals.update(
        APP_VERSION=APP_VERSION, MONTHS_FR=MONTHS_FR,
        ASSET_LABEL=ASSET_LABEL, LIABILITY_LABEL=LIABILITY_LABEL,
    )
    app.state.settings = settings
    app.state.manager = manager

    # ── Rendu / session ──────────────────────────────────────
    def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
        ctx.setdefault("flash", request.session.pop("flash", None))
        ctx["csrf"] = csrf_token(request.session)
        ctx["user_email"] = request.session.get("email", "")
        ctx["active"] = ctx.get("active", "")
        return templates.TemplateResponse(request, name, ctx, status_code=status_code)

    def flash(request: Request, message: str, kind: str = "ok") -> None:
        request.session["flash"] = {"message": message, "kind": kind}

    def redirect(url: str) -> RedirectResponse:
        return RedirectResponse(url, status_code=303)

    def workspace(request: Request) -> Workspace:
        uid = request.session.get("uid")
        ws = manager.get(uid) if uid else None
        if ws is None:
            # Session expirée côté serveur (pod redémarré, inactivité…).
            request.session.pop("uid", None)
            raise _NotAuthenticated()
        return ws

    def check_csrf(request: Request, token: str) -> None:
        if not csrf_valid(request.session, token):
            raise _BadRequest("Formulaire expiré — rechargez la page et réessayez.")

    @app.exception_handler(_NotAuthenticated)
    async def _on_not_auth(request: Request, _exc):
        return redirect("/connexion")

    @app.exception_handler(_BadRequest)
    async def _on_bad_request(request: Request, exc: _BadRequest):
        flash(request, str(exc), "error")
        back = request.headers.get("referer", "/")
        # N'accepter qu'un retour vers ce même site.
        if not back.startswith(str(request.base_url)):
            back = "/"
        return redirect(back)

    # ── Santé (sondes Kubernetes) ────────────────────────────
    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return JSONResponse({"status": "ok", "version": APP_VERSION})

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        writable = os.access(settings.users_dir, os.W_OK)
        return JSONResponse(
            {"status": "ok" if writable else "data-dir-not-writable",
             "workspaces": manager.count()},
            status_code=200 if writable else 503,
        )

    # ── Connexion / déconnexion ──────────────────────────────
    @app.get("/connexion", response_class=HTMLResponse)
    def login_form(request: Request):
        if request.session.get("uid") and manager.get(request.session["uid"]):
            return redirect("/")
        return render(request, "login.html", auth_mode=settings.auth_mode)

    @app.post("/connexion")
    def login(request: Request, identifier: str = Form(""), password: str = Form(""),
              csrf: str = Form("")):
        if not csrf_valid(request.session, csrf):
            return render(request, "login.html", 400, auth_mode=settings.auth_mode,
                          error="Formulaire expiré — réessayez.")
        ip = request.client.host if request.client else "?"
        keys = (f"ip:{ip}", f"id:{identifier.strip().lower()}")
        if any(limiter.blocked(k) for k in keys):
            return render(request, "login.html", 429, auth_mode=settings.auth_mode,
                          error="Trop de tentatives. Réessayez dans quelques minutes.")

        ws, error = _authenticate(identifier, password)
        if ws is None:
            for k in keys:
                limiter.fail(k)
            log.info("[Web] Connexion refusée (%s)", ip)
            return render(request, "login.html", 401, auth_mode=settings.auth_mode,
                          error=error, identifier=identifier)
        for k in keys:
            limiter.reset(k)
        request.session.clear()          # nouvelle session (anti-fixation)
        request.session["uid"] = ws.user_id
        request.session["email"] = ws.email
        if ws.last_sync_msg.startswith("⚠️"):
            flash(request, ws.last_sync_msg, "error")
        log.info("[Web] Connexion de %s", ws.user_id)
        return redirect("/")

    def _authenticate(identifier: str, password: str):
        if not identifier or not password:
            return None, "Identifiant et mot de passe requis."
        if settings.auth_mode == "local":
            import bcrypt
            import hmac as _hmac
            ok_user = _hmac.compare_digest(identifier.strip(), settings.local_user)
            try:
                ok_pwd = bcrypt.checkpw(password.encode("utf-8"),
                                        settings.local_password_hash.encode("utf-8"))
            except ValueError:
                ok_pwd = False
            if not (ok_user and ok_pwd):
                return None, "Identifiant ou mot de passe incorrect."
            return manager.open_local("local", settings.local_user), ""

        import cloud_auth
        client = cloud_auth.build_client(settings.supabase_url, settings.supabase_anon_key)
        ok, err, session = cloud_auth.sign_in(client, identifier, password)
        if not ok or session is None:
            return None, err or "Connexion impossible."
        try:
            ws = manager.open_supabase(client, session.user.id, session.user.email or identifier)
        except Exception:
            log.error("[Web] Ouverture de l'espace échouée", exc_info=True)
            return None, "Connexion réussie, mais vos données n'ont pas pu être chargées."
        return ws, ""

    @app.post("/deconnexion")
    def logout(request: Request, csrf: str = Form("")):
        check_csrf(request, csrf)
        uid = request.session.get("uid")
        request.session.clear()
        if uid:
            manager.close(uid)           # push final + fermeture
        return redirect("/connexion")

    # ── Tableau de bord ──────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, y: Optional[int] = None, m: Optional[int] = None):
        ws = workspace(request)
        with ws.lock:
            db = ws.db
            y, m = _month_params(ws, y, m)
            rev = sum(r["amount"] for r in db.get_revenues(y, m))
            exp = sum(r["amount"] for r in db.get_expenses(y, m))
            sav = sum(r["amount"] for r in db.get_savings(y, m))
            by_cat = [dict(r) for r in db.get_expenses_by_category(y, m)]
            budgets = [b for b in db.get_budget_vs_actual(y, m) if b["has_budget"]]
            history = [dict(r) for r in reversed(db.monthly_summary(12))]
            assets_total = sum(a["value"] for a in db.get_assets_current())
            liabilities_total = db.get_total_liabilities()
        max_cat = max((c["total"] for c in by_cat), default=0) or 1
        max_hist = max((max(h["rev"], h["exp"]) for h in history), default=0) or 1
        return render(
            request, "dashboard.html", active="dashboard", y=y, m=m,
            prev=_shift(y, m, -1), next=_shift(y, m, 1),
            rev=rev, exp=exp, sav=sav, balance=rev - exp - sav,
            by_cat=by_cat, max_cat=max_cat, budgets=budgets,
            history=history, max_hist=max_hist,
            net_worth=assets_total - liabilities_total,
        )

    # ── Saisies (dépenses / revenus / épargne) ───────────────
    _KINDS = {
        "depenses": ("expense", "Dépenses", "entries.html"),
        "revenus":  ("revenue", "Revenus",  "entries.html"),
        "epargne":  ("saving",  "Épargne",  "entries.html"),
    }

    def _list_ctx(ws: Workspace, kind: str, y: int, m: int) -> dict:
        db = ws.db
        if kind == "expense":
            rows = [dict(r) for r in db.get_expenses(y, m)]
        elif kind == "revenue":
            rows = [dict(r) for r in db.get_revenues(y, m)]
        else:
            rows = [dict(r) for r in db.get_savings(y, m)]
        return {
            "rows": rows, "total": sum(r["amount"] for r in rows),
            "categories": [dict(c) for c in db.get_categories()],
            "payees": db.get_payees()[:200] if kind == "expense" else [],
            "closed": db.is_month_closed(y, m),
        }

    def _ensure_open(ws: Workspace, y: int, m: int) -> None:
        if ws.db.is_month_closed(y, m):
            raise _BadRequest(f"{MONTHS_FR[m-1]} {y} est clôturé : rouvrez-le "
                              "depuis l'application desktop pour le modifier.")

    def _category_id(ws: Workspace, raw: str) -> int:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            raise _BadRequest("Catégorie invalide.")
        if cid not in {c["id"] for c in ws.db.get_categories()}:
            raise _BadRequest("Catégorie inconnue.")
        return cid

    def _entry_or_400(ws: Workspace, kind: str, entry_id: int) -> dict:
        entry = ws.db.get_entry(kind, entry_id)
        if entry is None:
            raise _BadRequest("Élément introuvable (déjà supprimé ?).")
        return entry

    @app.get("/{section}", response_class=HTMLResponse)
    def list_entries(request: Request, section: str,
                     y: Optional[int] = None, m: Optional[int] = None):
        if section == "patrimoine":
            return patrimoine(request)
        if section not in _KINDS:
            return Response(status_code=404)
        kind, title, tpl = _KINDS[section]
        ws = workspace(request)
        with ws.lock:
            y, m = _month_params(ws, y, m)
            ctx = _list_ctx(ws, kind, y, m)
        return render(request, tpl, active=section, section=section, title=title,
                      y=y, m=m, prev=_shift(y, m, -1), next=_shift(y, m, 1), **ctx)

    @app.post("/{section}")
    def add_entry(request: Request, section: str, y: int = Form(...), m: int = Form(...),
                  amount: str = Form(""), label: str = Form(""),
                  category_id: str = Form(""), payee: str = Form(""),
                  source: str = Form(""), account: str = Form(""),
                  csrf: str = Form("")):
        if section not in _KINDS:
            return Response(status_code=404)
        check_csrf(request, csrf)
        kind = _KINDS[section][0]
        ws = workspace(request)
        y, m = _month_params(ws, y, m)
        value = _parse_positive_amount(amount)
        with ws.lock:
            _ensure_open(ws, y, m)
            db = ws.db
            if kind == "expense":
                db.add_expense(y, m, _category_id(ws, category_id), value,
                               _clean(label), _clean(payee, 60))
                msg = "Dépense ajoutée."
            elif kind == "revenue":
                if not _clean(source):
                    raise _BadRequest("La source du revenu est obligatoire.")
                db.add_revenue(y, m, _clean(source), value, _clean(label))
                msg = "Revenu ajouté."
            else:
                linked = db.add_saving(y, m, _clean(account, 80), value, _clean(label))
                msg = "Épargne ajoutée." + (
                    f" Compte « {linked} » mis à jour dans le patrimoine." if linked else "")
        ws.mark_dirty()
        flash(request, msg)
        return redirect(f"/{section}?y={y}&m={m}")

    @app.get("/{section}/{entry_id}/modifier", response_class=HTMLResponse)
    def edit_form(request: Request, section: str, entry_id: int):
        if section not in _KINDS:
            return Response(status_code=404)
        kind, title, _ = _KINDS[section]
        ws = workspace(request)
        with ws.lock:
            entry = _entry_or_400(ws, kind, entry_id)
            categories = [dict(c) for c in ws.db.get_categories()]
            closed = ws.db.is_month_closed(entry["year"], entry["month"])
        return render(request, "edit.html", active=section, section=section,
                      kind=kind, title=title, entry=entry, categories=categories,
                      closed=closed)

    @app.post("/{section}/{entry_id}/modifier")
    def edit_entry(request: Request, section: str, entry_id: int,
                   amount: str = Form(""), label: str = Form(""),
                   category_id: str = Form(""), payee: str = Form(""),
                   source: str = Form(""), account: str = Form(""),
                   csrf: str = Form("")):
        if section not in _KINDS:
            return Response(status_code=404)
        check_csrf(request, csrf)
        kind = _KINDS[section][0]
        ws = workspace(request)
        value = _parse_positive_amount(amount)
        with ws.lock:
            entry = _entry_or_400(ws, kind, entry_id)
            y, m = entry["year"], entry["month"]
            _ensure_open(ws, y, m)
            db = ws.db
            if kind == "expense":
                db.update_expense(entry_id, _category_id(ws, category_id), value,
                                  _clean(label), _clean(payee, 60))
            elif kind == "revenue":
                if not _clean(source):
                    raise _BadRequest("La source du revenu est obligatoire.")
                db.update_revenue(entry_id, _clean(source), value, _clean(label))
            else:
                db.update_saving(entry_id, _clean(account, 80), value, _clean(label))
        ws.mark_dirty()
        flash(request, "Modification enregistrée.")
        return redirect(f"/{section}?y={y}&m={m}")

    @app.post("/{section}/{entry_id}/supprimer")
    def delete_entry(request: Request, section: str, entry_id: int, csrf: str = Form("")):
        if section not in _KINDS:
            return Response(status_code=404)
        check_csrf(request, csrf)
        kind = _KINDS[section][0]
        ws = workspace(request)
        with ws.lock:
            entry = _entry_or_400(ws, kind, entry_id)
            y, m = entry["year"], entry["month"]
            _ensure_open(ws, y, m)
            {"expense": ws.db.delete_expense, "revenue": ws.db.delete_revenue,
             "saving": ws.db.delete_saving}[kind](entry_id)
        ws.mark_dirty()
        flash(request, "Élément supprimé.")
        return redirect(f"/{section}?y={y}&m={m}")

    # ── Patrimoine (lecture) ─────────────────────────────────
    def patrimoine(request: Request):
        ws = workspace(request)
        with ws.lock:
            assets = [dict(a) for a in ws.db.get_assets_current()]
            liabilities = [dict(l) for l in ws.db.get_liabilities_current()]
        by_type: dict[str, float] = {}
        for a in assets:
            by_type[a["asset_type"]] = by_type.get(a["asset_type"], 0.0) + a["value"]
        total_assets = sum(by_type.values())
        total_liab = sum(l["remaining_capital"] for l in liabilities)
        return render(request, "patrimoine.html", active="patrimoine",
                      assets=assets, liabilities=liabilities,
                      by_type=sorted(by_type.items(), key=lambda kv: -kv[1]),
                      total_assets=total_assets, total_liab=total_liab,
                      max_type=max(by_type.values(), default=0) or 1)

    return app


def _build_default_app() -> FastAPI:
    return create_app()


# `uvicorn web.main:app` — construit à l'import ; la configuration est lue
# depuis l'environnement et validée (refus de démarrer si incomplète).
app = _build_default_app() if os.environ.get("FINTRACK_WEB_NO_AUTOAPP") != "1" else None
