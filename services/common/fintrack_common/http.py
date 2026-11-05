"""Middlewares et utilitaires HTTP communs à tous les services."""
from __future__ import annotations

import logging
import re
import time
import uuid

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import VERSION
from .logs import request_id_var

log = logging.getLogger(__name__)
_RID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")

API_CSP = "default-src 'none'; frame-ancestors 'none'"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Propage/génère X-Request-ID, journalise chaque requête (sans corps ni
    en-têtes : aucune donnée financière ni jeton dans les logs), ajoute les
    en-têtes de sécurité de base."""

    def __init__(self, app, csp: str = API_CSP, static_prefix: str | None = None):
        super().__init__(app)
        self.csp = csp
        self.static_prefix = static_prefix

    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id", "")
        if not _RID_RE.match(rid):
            rid = uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("Erreur non gérée")
            response = JSONResponse({"detail": "Erreur interne."}, status_code=500)
        finally:
            request_id_var.reset(token)
        elapsed = (time.perf_counter() - start) * 1000
        if request.url.path not in ("/healthz", "/readyz"):
            request_id_var.set(rid)
            log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path,
                     response.status_code, elapsed)
        h = response.headers
        h["X-Request-ID"] = rid
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Content-Security-Policy", self.csp)
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Cache-Control", self._cache_policy(request))
        return response

    def _cache_policy(self, request) -> str:
        """Pages et API : jamais en cache (données financières). Fichiers
        statiques : mis en cache — un an s'ils sont versionnés (?v=<version>,
        l'URL change à chaque release), sinon revalidés par ETag (304)."""
        if self.static_prefix and request.url.path.startswith(self.static_prefix):
            if request.query_params.get("v"):
                return "public, max-age=31536000, immutable"
            return "no-cache"
        return "no-store"


def add_health_routes(app: FastAPI, ready_check=None) -> None:
    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok", "version": VERSION}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        ok, detail = (ready_check() if ready_check else (True, "ok"))
        return JSONResponse({"status": "ok" if ok else detail}, status_code=200 if ok else 503)


def service_client(base_url: str, timeout: float = 10.0,
                   transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Client HTTP vers un autre service : timeouts stricts, pas de
    redirection suivie, request-id propagé."""
    def _add_rid(request: httpx.Request):
        request.headers["X-Request-ID"] = request_id_var.get()

    return httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(timeout, connect=3.0),
        follow_redirects=False,
        event_hooks={"request": [_add_rid]},
        headers={"User-Agent": f"fintrack/{VERSION}"},
        transport=transport,         # tests : transport simulé
    )
