"""
routes_auth.py — Connexion, déconnexion et consentement OAuth (clients MCP).
"""
from __future__ import annotations

import os
from typing import Optional
from types import SimpleNamespace
from urllib.parse import quote, urlsplit

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from fintrack_common.auth import secure_equals

from .backends import BackendError
from .common import COOKIE, LOGIN_MAX_PER_IP, LOGIN_MAX_PER_IP_ID, OAUTH_AUTH_ID_RE, _Redirect, log, oauth_redirect_allowed, safe_next


def register(app: FastAPI, w: SimpleNamespace) -> None:
    """Enregistre les routes de ce module (dépendances partagées dans `w`)."""
    # Dépendances partagées, créées par main.create_app
    backends, check_csrf, cookie_secure, flash = w.backends, w.check_csrf, w.cookie_secure, w.flash
    limiter, load, oauth_hosts, redirect = w.limiter, w.load, w.oauth_hosts, w.redirect
    refresh, render, sessions = w.refresh, w.render, w.sessions

    # ── Connexion ────────────────────────────────────────────
    def client_ip(request: Request) -> str:
        # request.client vient d'uvicorn --proxy-headers, qui ne fait confiance
        # à X-Forwarded-For QUE depuis FORWARDED_ALLOW_IPS (le proxy d'entrée).
        return request.client.host if request.client else "?"

    @app.get("/connexion", response_class=HTMLResponse)
    def login_form(request: Request, next: Optional[str] = None):  # noqa: A002
        target = safe_next(next)
        if sessions.get(request.cookies.get(COOKIE)):
            return redirect(target)
        # Jeton CSRF de pré-session (cookie dédié, SameSite=Strict)
        pre = request.cookies.get("fintrack_pre") or os.urandom(24).hex()
        resp = render(request, "login.html", None, None, csrf=pre, next=target)
        resp.set_cookie("fintrack_pre", pre, httponly=True, secure=cookie_secure,
                        samesite="strict", max_age=1800)
        return resp

    @app.post("/connexion")
    def login(request: Request, identifier: str = Form(""), password: str = Form(""),
              csrf: str = Form(""), next: str = Form("/")):  # noqa: A002
        pre = request.cookies.get("fintrack_pre", "")
        target = safe_next(next)

        def fail(msg: str, code: int):
            return render(request, "login.html", None, None, code, csrf=pre or "",
                          error=msg, identifier=identifier[:120], next=target)

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
        resp = redirect(target)
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

    # ── Consentement OAuth (clients MCP) ─────────────────────
    # Supabase Auth (serveur OAuth 2.1) redirige ici avec ?authorization_id=…
    # (réglage « Authorization path » = /oauth/consent). L'utilisateur
    # connecté approuve ou refuse ; Supabase renvoie alors l'adresse de retour
    # du client, munie du code d'autorisation (PKCE).
    def oauth_session(request: Request, authorization_id: str):
        if not OAUTH_AUTH_ID_RE.match(authorization_id or ""):
            raise BackendError(400, "Demande d'autorisation invalide.")
        sid = request.cookies.get(COOKIE)
        sess = sessions.get(sid)
        if sess is None:
            here = f"/oauth/consent?authorization_id={authorization_id}"
            raise _Redirect(f"/connexion?next={quote(here, safe='')}")
        refresh(sid, sess)
        return sid, sess

    def oauth_handoff(request: Request, sid: str, sess: dict, url: str, approved: bool):
        """Retour vers le client par meta refresh (même raison que TickTick :
        `form-action` s'appliquerait à la redirection après le POST)."""
        if not oauth_redirect_allowed(url, oauth_hosts):
            raise BackendError(400, "Adresse de retour du client non autorisée.")
        return render(request, "oauth_redirect.html", sid, sess, url=url, approved=approved)

    @app.get("/oauth/consent", response_class=HTMLResponse)
    def oauth_consent_page(request: Request, authorization_id: str = ""):
        sid, sess = oauth_session(request, authorization_id)
        details = backends.auth.oauth_authorization(sess["access_token"], authorization_id)
        if "authorization_id" not in details:          # accès déjà accordé à ce client
            return oauth_handoff(request, sid, sess, details.get("redirect_url", ""), True)
        redirect_uri = details.get("redirect_uri", "")
        return render(request, "oauth_consent.html", sid, sess,
                      authorization_id=authorization_id, client=details.get("client") or {},
                      redirect_uri=redirect_uri,
                      redirect_host=urlsplit(redirect_uri).hostname or "?",
                      scopes=(details.get("scope") or "").split(),
                      allowed=oauth_redirect_allowed(redirect_uri, oauth_hosts))

    @app.post("/oauth/consent")
    def oauth_consent_submit(request: Request, authorization_id: str = Form(""),
                             action: str = Form(""), csrf: str = Form("")):
        sid, sess = oauth_session(request, authorization_id)
        check_csrf(sess, csrf)
        if action not in ("approve", "deny"):
            raise BackendError(400, "Action inconnue.")
        approve = action == "approve"
        if approve:
            # Revérifié côté serveur : le formulaire n'est pas une preuve.
            details = backends.auth.oauth_authorization(sess["access_token"], authorization_id)
            if not oauth_redirect_allowed(details.get("redirect_uri", ""), oauth_hosts):
                raise BackendError(400, "Adresse de retour du client non autorisée.")
        url = backends.auth.oauth_consent(sess["access_token"], authorization_id, approve)
        log.info("Consentement OAuth %s", "accordé" if approve else "refusé")
        if not approve and not oauth_redirect_allowed(url, oauth_hosts):
            flash(sid, sess, "Accès refusé.")
            return redirect("/")
        return oauth_handoff(request, sid, sess, url, approve)
