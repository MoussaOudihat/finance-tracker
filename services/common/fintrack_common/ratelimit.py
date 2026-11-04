"""
Compteurs à fenêtre fixe partagés via Redis (plusieurs réplicas), avec
repli en mémoire BORNÉ (taille maximale, entrées expirées purgées) quand
Redis n'est pas configuré — utile en développement et dans les tests.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict


def _key(*parts: str) -> str:
    # Clés hachées : pas d'e-mail ni d'IP en clair dans Redis, taille bornée.
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


class Counter:
    def __init__(self, redis_client=None, prefix: str = "rl", max_local: int = 10_000):
        self.redis = redis_client
        self.prefix = prefix
        self._local: OrderedDict[str, tuple[int, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._max_local = max_local

    def _full(self, scope: str, *parts: str) -> str:
        return f"{self.prefix}:{scope}:{_key(*parts)}"

    def get(self, scope: str, *parts: str) -> int:
        k = self._full(scope, *parts)
        if self.redis is not None:
            return int(self.redis.get(k) or 0)
        with self._lock:
            v = self._local.get(k)
            if v is None or v[1] < time.monotonic():
                self._local.pop(k, None)
                return 0
            return v[0]

    def incr(self, scope: str, *parts: str, window: int) -> int:
        k = self._full(scope, *parts)
        if self.redis is not None:
            pipe = self.redis.pipeline()
            pipe.incr(k)
            pipe.expire(k, window, nx=True)
            return int(pipe.execute()[0])
        now = time.monotonic()
        with self._lock:
            count, exp = self._local.get(k, (0, now + window))
            if exp < now:
                count, exp = 0, now + window
            self._local[k] = (count + 1, exp)
            self._local.move_to_end(k)
            while len(self._local) > self._max_local:
                self._local.popitem(last=False)     # éviction : mémoire bornée
            return count + 1

    def reset(self, scope: str, *parts: str) -> None:
        k = self._full(scope, *parts)
        if self.redis is not None:
            self.redis.delete(k)
        else:
            with self._lock:
                self._local.pop(k, None)


def redis_from_url(url: str):
    if not url:
        return None
    import redis
    return redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2,
                                health_check_interval=30, decode_responses=True)
