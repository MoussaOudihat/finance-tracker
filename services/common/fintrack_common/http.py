"""Middlewares et utilitaires HTTP communs à tous les services."""
from __future__ import annotations

import logging
import re
import time
import uuid
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import VERSION
from .logs import request_id_var

log = logging.getLogger(__name__)
_RID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")

API_CSP = "default-src 'none'; frame-ancestors 'none'"


class RequestContextMiddleware:
    """Propage/génère X-Request-ID, journalise chaque requête (sans corps ni
    en-têtes : aucune donnée financière ni jeton dans les logs), ajoute les
    en-têtes de sécurité de base.

    Middleware ASGI pur (et non BaseHTTPMiddleware, qui isole mal les
    contextvars et retarde les tâches de fond) : le request_id est posé pour
    toute la durée de la requête puis TOUJOURS retiré — il ne déborde plus
    sur la requête suivante traitée par le même worker."""

    def __init__(self, app: ASGIApp, csp: str = API_CSP, static_prefix: str | None = None):
        self.app = app
        self.csp = csp
        self.static_prefix = static_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = Headers(scope=scope).get("x-request-id", "")
        if not _RID_RE.match(rid):
            rid = uuid.uuid4().hex
        path, method = scope["path"], scope["method"]
        cache = self._cache_policy(path, scope.get("query_string", b""))
        state = {"status": 500, "started": False, "end": None}
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                state["status"], state["started"] = message["status"], True
                h = MutableHeaders(scope=message)
                h["X-Request-ID"] = rid
                h.setdefault("X-Content-Type-Options", "nosniff")
                h.setdefault("Content-Security-Policy", self.csp)
                h.setdefault("Referrer-Policy", "same-origin")
                h.setdefault("Cache-Control", cache)
            elif message["type"] == "http.response.body" and not message.get("more_body"):
                state["end"] = time.perf_counter()      # hors tâches de fond
            await send(message)

        token = request_id_var.set(rid)
        try:
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                log.exception("Erreur non gérée")
                if state["started"]:
                    raise
                await JSONResponse({"detail": "Erreur interne."}, status_code=500)(
                    scope, receive, send_wrapper)
            if path not in ("/healthz", "/readyz"):
                elapsed = ((state["end"] or time.perf_counter()) - start) * 1000
                log.info("%s %s -> %s (%.0f ms)", method, path, state["status"], elapsed)
        finally:
            request_id_var.reset(token)

    def _cache_policy(self, path: str, query_string: bytes) -> str:
        """Pages et API : jamais en cache (données financières). Fichiers
        statiques : mis en cache — un an s'ils sont versionnés (?v=<version>,
        l'URL change à chaque release), sinon revalidés par ETag (304)."""
        if self.static_prefix and path.startswith(self.static_prefix):
            if parse_qs(query_string.decode("latin-1")).get("v"):
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
