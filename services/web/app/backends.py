"""
backends.py — Accès du BFF aux autres services et à Supabase Auth.

  • Supabase Auth (GoTrue) : connexion, rafraîchissement, déconnexion
    (scope « local » : seulement cette session, pas les autres appareils).
  • finance-api / ai-service / notifier : appels JSON avec le jeton
    d'accès de l'utilisateur, rafraîchi automatiquement avant expiration.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)
REFRESH_MARGIN = 120       # secondes avant expiration


class BackendError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class AuthExpired(Exception):
    """La session Supabase ne peut plus être rafraîchie : reconnexion."""


@dataclass
class SupabaseAuth:
    http: httpx.Client          # base_url = SUPABASE_URL
    anon_key: str

    def _post(self, path: str, json: dict, token: str | None = None) -> httpx.Response:
        headers = {"apikey": self.anon_key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.http.post(path, json=json, headers=headers)

    def sign_in(self, email: str, password: str) -> dict | None:
        r = self._post("/auth/v1/token?grant_type=password",
                       {"email": email.strip(), "password": password})
        if r.status_code in (400, 401, 422):
            return None
        r.raise_for_status()
        return _session_from(r.json())

    def refresh(self, refresh_token: str) -> dict:
        r = self._post("/auth/v1/token?grant_type=refresh_token",
                       {"refresh_token": refresh_token})
        if r.status_code >= 400:
            raise AuthExpired()
        return _session_from(r.json())

    # ── Serveur OAuth 2.1 de Supabase Auth (consentement des clients MCP) ──
    def _oauth(self, method: str, path: str, access_token: str, json: dict | None = None,
               *, what: str = "") -> dict:
        try:
            r = self.http.request(method, path, json=json, headers={
                "apikey": self.anon_key, "Authorization": f"Bearer {access_token}"})
        except httpx.HTTPError as exc:
            raise BackendError(503, "Service d'authentification indisponible.") from exc
        if r.status_code == 401:
            raise AuthExpired()
        if r.status_code in (400, 404, 410, 422):
            raise BackendError(400, "Demande d'autorisation invalide ou expirée — relancez "
                                    "la connexion depuis votre client MCP.")
        if r.status_code >= 400:
            log.warning("Supabase OAuth (%s) -> %s", what or method, r.status_code)
            raise BackendError(502, "Erreur du service d'authentification.")
        return r.json()

    def oauth_authorization(self, access_token: str, authorization_id: str) -> dict:
        """Détails de la demande (client, redirect_uri, scope) ; si l'accès a
        déjà été accordé : {"redirect_url": …} directement."""
        return self._oauth("GET", f"/auth/v1/oauth/authorizations/{authorization_id}",
                           access_token, what="détails de la demande")

    def oauth_consent(self, access_token: str, authorization_id: str, approve: bool) -> str:
        data = self._oauth("POST", f"/auth/v1/oauth/authorizations/{authorization_id}/consent",
                           access_token, {"action": "approve" if approve else "deny"},
                           what="consentement")
        return data.get("redirect_url", "")

    def sign_out(self, access_token: str) -> None:
        try:
            self._post("/auth/v1/logout?scope=local", {}, token=access_token)
        except httpx.HTTPError:
            pass


def _session_from(data: dict) -> dict:
    return {
        "user_id": data["user"]["id"],
        "email": data["user"].get("email", ""),
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": time.time() + int(data.get("expires_in", 3600)),
    }


class Backends:
    def __init__(self, auth: SupabaseAuth, finance: httpx.Client, ai: httpx.Client | None,
                 notifier: httpx.Client | None):
        self.auth = auth
        self.clients = {"finance": finance, "ai": ai, "notifier": notifier}

    def fresh_token(self, sess: dict) -> bool:
        """Rafraîchit le jeton si besoin. Renvoie True si la session a changé."""
        if sess["expires_at"] - time.time() > REFRESH_MARGIN:
            return False
        sess.update(self.auth.refresh(sess["refresh_token"]))
        return True

    def call(self, sess: dict, service: str, method: str, path: str, *,
             json: Any = None, params: dict | None = None, timeout: float | None = None) -> Any:
        client = self.clients.get(service)
        if client is None:
            raise BackendError(503, "Ce service n'est pas déployé.")
        kwargs: dict = {"json": json, "params": params,
                        "headers": {"Authorization": f"Bearer {sess['access_token']}"}}
        if timeout:
            kwargs["timeout"] = timeout
        try:
            r = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            log.warning("%s injoignable : %s", service, exc.__class__.__name__)
            raise BackendError(503, "Service momentanément indisponible.") from exc
        if r.status_code == 401:
            raise AuthExpired()
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = None
            if isinstance(detail, list):        # erreurs de validation pydantic
                detail = "Données invalides : vérifiez les champs saisis."
            raise BackendError(r.status_code, detail or "Erreur du service.")
        return r.json() if r.content else None
