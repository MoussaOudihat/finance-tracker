"""Logs structurés JSON sur stdout (collectés par le runtime de conteneurs)."""
from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Bibliothèques bavardes : en DEBUG elles journalisent chaque en-tête HTTP
# (jetons compris pour certaines). Toujours limitées à WARNING.
_NOISY = ("httpx", "httpcore", "hpack", "h2", "h11", "urllib3", "anthropic",
          "google_genai", "google.genai", "asyncio")


class _JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(service: str) -> logging.Logger:
    level = getattr(logging, os.environ.get("FINTRACK_LOG_LEVEL", "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
    return logging.getLogger(service)
