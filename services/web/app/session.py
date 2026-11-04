"""
session.py — Sessions CÔTÉ SERVEUR.

Le cookie ne contient qu'un identifiant aléatoire (256 bits). Les jetons
Supabase (accès + rafraîchissement) restent côté serveur, chiffrés (Fernet)
dans Redis — partagé entre réplicas — ou en mémoire (développement/tests).

  • Déconnexion = suppression côté serveur : un cookie volé ou copié ne
    vaut plus rien ensuite (corrige la revue v2.0.0).
  • Expiration glissante (inactivité) + durée de vie absolue.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from collections import OrderedDict
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class SessionStore:
    def __init__(self, encryption_key: str, redis_client=None, *,
                 idle_ttl: int = 3600, absolute_ttl: int = 12 * 3600, max_local: int = 5000):
        self.fernet = Fernet(encryption_key.encode())
        self.redis = redis_client
        self.idle_ttl = idle_ttl
        self.absolute_ttl = absolute_ttl
        self._local: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._max_local = max_local

    @staticmethod
    def _k(sid: str) -> str:
        return f"sess:{sid}"

    def _put(self, sid: str, data: dict) -> None:
        blob = self.fernet.encrypt(json.dumps(data).encode())
        if self.redis is not None:
            self.redis.set(self._k(sid), blob.decode(), ex=self.idle_ttl)
            return
        with self._lock:
            self._local[sid] = (blob, time.time() + self.idle_ttl)
            self._local.move_to_end(sid)
            while len(self._local) > self._max_local:
                self._local.popitem(last=False)

    def create(self, data: dict) -> str:
        sid = secrets.token_urlsafe(32)
        data = {**data, "created": time.time(), "csrf": secrets.token_urlsafe(32)}
        self._put(sid, data)
        return sid

    def get(self, sid: Optional[str]) -> Optional[dict]:
        if not sid or len(sid) > 64:
            return None
        if self.redis is not None:
            raw = self.redis.get(self._k(sid))
            blob = raw.encode() if raw else None
        else:
            with self._lock:
                item = self._local.get(sid)
                blob = item[0] if item and item[1] > time.time() else None
        if blob is None:
            return None
        try:
            data = json.loads(self.fernet.decrypt(blob))
        except (InvalidToken, ValueError):
            return None
        if time.time() - data.get("created", 0) > self.absolute_ttl:
            self.delete(sid)
            return None
        return data

    def save(self, sid: str, data: dict) -> None:
        """Réécrit la session (prolonge l'expiration glissante)."""
        self._put(sid, data)

    def delete(self, sid: Optional[str]) -> None:
        if not sid:
            return
        if self.redis is not None:
            self.redis.delete(self._k(sid))
        else:
            with self._lock:
                self._local.pop(sid, None)

    def ping(self) -> bool:
        if self.redis is not None:
            return bool(self.redis.ping())
        return True
