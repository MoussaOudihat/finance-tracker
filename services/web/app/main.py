"""
web — BFF (Backend For Frontend) de Fintrack : pages HTML, sessions,
orchestration des appels à finance-api, ai-service et notifier.

Sans état (sessions dans Redis) : réplicable (HPA). Ne touche jamais la
base directement. Les routes sont réparties par domaine dans routes_*.py ;
ce module crée l'application et les dépendances partagées (session, rendu,
appels aux services).
"""
from __future__ import annotations

import contextvars
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Optional
from types import SimpleNamespace
from urllib.parse import quote, urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fintrack_common.auth import secure_equals
from fintrack_common.config import VERSION, env, env_bool, env_int
from fintrack_common.fmt import fmt_eur
from fintrack_common.http import RequestContextMiddleware, add_health_routes, service_client
from fintrack_common.ratelimit import Counter, redis_from_url

from .backends import AuthExpired, BackendError, Backends, SupabaseAuth
from .session import SessionStore

from . import routes_auth, routes_finance, routes_ia, routes_settings, routes_misc, routes_entries
from .common import (ASSET_LABEL, COOKIE, CSP, LIABILITY_LABEL, MONTHS_FR,
                     OAUTH_DEFAULT_REDIRECT_HOSTS, SECTIONS, THEME_COOKIE, THEME_LABEL,
                     _HERE, _Redirect, _static_hashes)
# Ré-exportés : API historique de ce module (tests, outils)
from .common import (line_points, oauth_redirect_allowed, parse_amount,  # noqa: F401
                     render_ai_text)
from .common import safe_next


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
    oauth_hosts = tuple(h.strip().lower() for h in env(
        "OAUTH_ALLOWED_REDIRECT_HOSTS", OAUTH_DEFAULT_REDIRECT_HOSTS).split(",") if h.strip())
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
                                 ASSET_LABEL=ASSET_LABEL, LIABILITY_LABEL=LIABILITY_LABEL,
                                 THEME_LABEL=THEME_LABEL, SECTIONS=SECTIONS)
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

    def refresh(sid: str, sess: dict) -> None:
        """Rafraîchit le jeton Supabase s'il expire bientôt et enregistre la
        session (rotation du refresh token) — point UNIQUE pour toutes les
        routes."""
        if backends.fresh_token(sess):
            sessions.update(sid, access_token=sess["access_token"],
                            refresh_token=sess["refresh_token"], expires_at=sess["expires_at"])

    def call(sid: str, sess: dict, service: str, method: str, path: str, **kw):
        refresh(sid, sess)
        return backends.call(sess, service, method, path, **kw)

    def call_parallel(sid: str, sess: dict, *specs: tuple) -> list:
        """Plusieurs appels de LECTURE indépendants, en parallèle (une page
        n'attend plus la somme des latences). Le jeton est rafraîchi une seule
        fois avant (pas de rotation concurrente) ; le contexte de la requête
        (request_id) est copié dans chaque thread. Chaque spec :
        (service, méthode, chemin) ou (service, méthode, chemin, kwargs)."""
        refresh(sid, sess)
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
        theme = request.cookies.get(THEME_COOKIE, "auto")
        ctx["theme"] = theme if theme in THEME_LABEL else "auto"
        return templates.TemplateResponse(request, name, ctx, status_code=status_code)

    def redirect(url: str) -> RedirectResponse:
        """Redirection LOCALE uniquement (anti open-redirect, règle unique :
        common.safe_next)."""
        return RedirectResponse(safe_next(url), status_code=303)

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
        # GET : revenir sur la page demandée après reconnexion (indispensable
        # pour le consentement OAuth : le client MCP attend son retour).
        target = "/connexion"
        if request.method == "GET":
            here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            if here != "/":
                target += "?next=" + quote(safe_next(here), safe="")
        resp = redirect(target)
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

    w = SimpleNamespace(
        cookie_secure=cookie_secure, limiter=limiter, oauth_hosts=oauth_hosts, sessions=sessions,
        backends=backends, pool=pool, templates=templates, load=load, refresh=refresh, call=call,
        call_parallel=call_parallel, flash=flash, render=render, redirect=redirect,
        ticktick_handoff=ticktick_handoff, check_csrf=check_csrf, back_url=back_url,
        month_params=month_params)
    # Ordre d'enregistrement significatif : les routes génériques /{section}
    # (routes_entries) doivent rester les dernières.
    for module in (routes_auth, routes_finance, routes_ia, routes_settings, routes_misc, routes_entries):
        module.register(app, w)
    return app


app = create_app() if not env("FINTRACK_NO_AUTOAPP") else None
