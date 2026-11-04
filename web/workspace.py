"""
web/workspace.py — Espaces de travail par utilisateur (base SQLite + sync).

Chaque utilisateur connecté a un « espace » :
  • une base SQLite dédiée : <FINTRACK_DATA_DIR>/users/<user_id>/finance_tracker.db
  • en mode supabase, un SupabaseSync lié à SA session Supabase Auth.

Cycle de vie :
  1. Connexion : pull depuis Supabase si le distant est plus récent, puis
     ouverture de la base (même séquence que main.py côté desktop).
  2. Chaque modification programme un push différé (FINTRACK_SYNC_DELAY) :
     plusieurs saisies rapprochées ne donnent qu'un seul envoi.
  3. Déconnexion, inactivité prolongée ou arrêt du pod : push final bloquant,
     puis fermeture de la base.

Concurrence : `Database` partage une seule connexion SQLite. Toutes les
requêtes HTTP d'un même utilisateur passent donc par `ws.lock` (RLock).
Le push lit la base via sa propre connexion SQLite (WAL) : pas de blocage.

Limite assumée : l'espace (et la session Supabase) vit en mémoire du pod.
Le déploiement Kubernetes tourne donc en 1 réplica (stratégie Recreate) ;
après un redémarrage, l'utilisateur se reconnecte simplement.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Callable, Optional

from database import Database
from logger import log

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _user_db_path(users_dir: str, user_id: str) -> str:
    # user_id vient de Supabase (UUID) ou vaut "local" — validé quand même
    # pour qu'aucune valeur ne puisse sortir du dossier users/.
    if not _USER_ID_RE.match(user_id):
        raise ValueError(f"Identifiant utilisateur invalide : {user_id!r}")
    return os.path.join(users_dir, user_id, "finance_tracker.db")


class Workspace:
    def __init__(self, user_id: str, email: str, db_path: str,
                 sync=None, client=None, sync_delay: int = 20):
        self.user_id = user_id
        self.email = email
        self.db_path = db_path
        self.sync = sync
        self.client = client
        self.sync_delay = sync_delay
        self.lock = threading.RLock()
        self.last_access = time.monotonic()
        self.last_sync_msg = ""
        self._timer: Optional[threading.Timer] = None
        self._timer_lock = threading.Lock()
        self.db = Database(db_path)

    # ── Accès ────────────────────────────────────────────────
    def touch(self) -> None:
        self.last_access = time.monotonic()

    # ── Synchronisation ──────────────────────────────────────
    def mark_dirty(self) -> None:
        """Programme un push différé (regroupe les saisies rapprochées)."""
        if not self.sync:
            return
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.sync_delay, self._push_now)
            self._timer.daemon = True
            self._timer.start()

    def _push_now(self) -> None:
        with self._timer_lock:
            self._timer = None
        self._push(blocking=True)

    def _push(self, blocking: bool) -> None:
        if not self.sync:
            return

        def _done(msg: str) -> None:
            self.last_sync_msg = msg
            if msg.startswith("⚠️"):
                log.warning("[Web sync %s] %s", self.user_id, msg)
            else:
                log.info("[Web sync %s] %s", self.user_id, msg)

        self.sync.push(blocking=blocking, on_done=_done)

    def flush(self) -> None:
        """Push final bloquant si une modification est en attente."""
        with self._timer_lock:
            pending = self._timer is not None
            if pending:
                self._timer.cancel()
                self._timer = None
        if pending:
            self._push(blocking=True)

    def close(self) -> None:
        self.flush()
        with self.lock:
            try:
                self.db.close()
            except Exception:
                log.warning("Fermeture de la base %s échouée", self.db_path, exc_info=True)
        if self.client is not None:
            try:
                import cloud_auth
                cloud_auth.sign_out(self.client)
            except Exception:
                pass


class WorkspaceManager:
    """Registre thread-safe des espaces ouverts, indexés par user_id."""

    def __init__(self, users_dir: str, sync_delay: int, idle_timeout: int):
        self.users_dir = users_dir
        self.sync_delay = sync_delay
        self.idle_timeout = idle_timeout
        self._spaces: dict[str, Workspace] = {}
        self._lock = threading.Lock()
        self._open_lock = threading.Lock()
        self._stop = threading.Event()
        self._reaper: Optional[threading.Thread] = None

    # ── Ouverture ────────────────────────────────────────────
    def open_local(self, user_id: str = "local", email: str = "") -> Workspace:
        return self._open(user_id, email, lambda path: (None, None, ""))

    def open_supabase(self, client, user_id: str, email: str) -> Workspace:
        def _prepare(path: str):
            from sync_supabase import SupabaseSync
            # Créer le schéma local avant le pull (le pull lit app_settings).
            Database(path).close()
            sync = SupabaseSync.from_session(client, path, user_id)
            pulled, msg = sync.pull_if_newer()
            log.info("[Web sync %s] %s", user_id, msg)
            return sync, client, msg
        return self._open(user_id, email, _prepare)

    def _open(self, user_id: str, email: str,
              prepare: Callable[[str], tuple]) -> Workspace:
        path = _user_db_path(self.users_dir, user_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._lock:
            existing = self._spaces.get(user_id)
            if existing is not None:
                # Déjà ouvert (autre navigateur) : on garde la session en place
                # pour ne pas fermer la base sous les pieds d'une requête.
                existing.touch()
                return existing
        # Ouvertures sérialisées : deux connexions simultanées du même compte
        # ne doivent pas faire deux pulls concurrents dans le même fichier.
        with self._open_lock:
            with self._lock:
                existing = self._spaces.get(user_id)
            if existing is not None:
                existing.touch()
                return existing
            sync, client, msg = prepare(path)
            ws = Workspace(user_id, email, path, sync=sync, client=client,
                           sync_delay=self.sync_delay)
            ws.last_sync_msg = msg
            with self._lock:
                self._spaces[user_id] = ws
            return ws

    # ── Accès / fermeture ────────────────────────────────────
    def get(self, user_id: str) -> Optional[Workspace]:
        with self._lock:
            ws = self._spaces.get(user_id)
        if ws is not None:
            ws.touch()
        return ws

    def close(self, user_id: str) -> None:
        with self._lock:
            ws = self._spaces.pop(user_id, None)
        if ws is not None:
            ws.close()

    def close_all(self) -> None:
        self._stop.set()
        with self._lock:
            spaces = list(self._spaces.values())
            self._spaces.clear()
        for ws in spaces:
            ws.close()

    def count(self) -> int:
        with self._lock:
            return len(self._spaces)

    # ── Fermeture des espaces inactifs ───────────────────────
    def start_reaper(self, interval: int = 60) -> None:
        def _loop():
            while not self._stop.wait(interval):
                self.reap_idle()
        self._reaper = threading.Thread(target=_loop, name="ws-reaper", daemon=True)
        self._reaper.start()

    def reap_idle(self) -> None:
        now = time.monotonic()
        with self._lock:
            idle = [uid for uid, ws in self._spaces.items()
                    if now - ws.last_access > self.idle_timeout]
        for uid in idle:
            log.info("[Web] Espace %s inactif — synchronisation et fermeture.", uid)
            self.close(uid)
