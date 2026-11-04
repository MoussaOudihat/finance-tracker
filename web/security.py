"""
web/security.py — Protection CSRF, limitation des tentatives de connexion,
en-têtes de sécurité HTTP.
"""
from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware

# ── CSRF (jeton synchronisé stocké dans la session signée) ───────────────

def csrf_token(session: dict) -> str:
    tok = session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["csrf"] = tok
    return tok


def csrf_valid(session: dict, submitted: str | None) -> bool:
    expected = session.get("csrf")
    return bool(expected and submitted) and hmac.compare_digest(expected, submitted)


# ── Limitation des tentatives de connexion (mémoire du pod) ──────────────

class LoginRateLimiter:
    """Au plus `max_attempts` échecs par clé (IP) sur `window` secondes."""

    def __init__(self, max_attempts: int = 5, window: int = 300):
        self.max_attempts = max_attempts
        self.window = window
        self._fails: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        q = self._fails.setdefault(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return len(self._prune(key, now)) >= self.max_attempts

    def fail(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


# ── En-têtes de sécurité ─────────────────────────────────────────────────

_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; form-action 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; object-src 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, hsts: bool = True):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("Content-Security-Policy", _CSP)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path not in ("/healthz", "/readyz") and \
                not request.url.path.startswith("/static/"):
            # Données financières : jamais en cache navigateur / proxy.
            h.setdefault("Cache-Control", "no-store")
        if self.hsts:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response
