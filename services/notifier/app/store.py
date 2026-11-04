"""
store.py — Données propres à notifier (SQLite sur volume persistant) :
préférences, jetons TickTick et URLs de webhook CHIFFRÉS (Fernet),
états OAuth à usage unique, journal anti-doublon des alertes envoyées.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field

from cryptography.fernet import Fernet, InvalidToken

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prefs (
    user_id          TEXT PRIMARY KEY,
    email            TEXT DEFAULT '',
    budget_alerts    INTEGER DEFAULT 1,
    reminder_enabled INTEGER DEFAULT 0,
    reminder_day     INTEGER DEFAULT 1,
    ticktick_token   TEXT DEFAULT '',
    ticktick_project TEXT DEFAULT '',
    ntfy_url         TEXT DEFAULT '',
    webhook_url      TEXT DEFAULT '',
    updated_at       REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS oauth_states (
    state      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sent (
    dedupe_key TEXT PRIMARY KEY,
    sent_at    REAL NOT NULL
);
"""

_ENCRYPTED = ("ticktick_token", "ntfy_url", "webhook_url")


@dataclass
class Prefs:
    user_id: str
    email: str = ""
    budget_alerts: bool = True
    reminder_enabled: bool = False
    reminder_day: int = 1
    ticktick_token: str = ""
    ticktick_project: str = ""
    ntfy_url: str = ""
    webhook_url: str = ""
    extra: dict = field(default_factory=dict)

    def public(self) -> dict:
        """Vue sans secret, renvoyée au navigateur."""
        return {
            "budget_alerts": self.budget_alerts,
            "reminder_enabled": self.reminder_enabled,
            "reminder_day": self.reminder_day,
            "ticktick_connected": bool(self.ticktick_token),
            "ticktick_project": self.ticktick_project,
            "ntfy_configured": bool(self.ntfy_url),
            "webhook_configured": bool(self.webhook_url),
        }


class Store:
    def __init__(self, path: str, encryption_key: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._fernet = Fernet(encryption_key.encode())
        self._con = sqlite3.connect(path, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def _enc(self, v: str) -> str:
        return self._fernet.encrypt(v.encode()).decode() if v else ""

    def _dec(self, v: str) -> str:
        if not v:
            return ""
        try:
            return self._fernet.decrypt(v.encode()).decode()
        except InvalidToken:
            return ""     # clé changée : secret illisible, l'utilisateur reconnecte

    def ping(self) -> bool:
        with self._lock:
            self._con.execute("SELECT 1")
        return True

    # ── Préférences ──────────────────────────────────────────
    def get(self, user_id: str) -> Prefs:
        with self._lock:
            row = self._con.execute("SELECT * FROM prefs WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return Prefs(user_id=user_id)
        d = dict(row)
        for k in _ENCRYPTED:
            d[k] = self._dec(d[k])
        d.pop("updated_at", None)
        d["budget_alerts"] = bool(d["budget_alerts"])
        d["reminder_enabled"] = bool(d["reminder_enabled"])
        return Prefs(**d)

    def save(self, p: Prefs) -> None:
        with self._lock:
            self._con.execute(
                """INSERT INTO prefs(user_id,email,budget_alerts,reminder_enabled,reminder_day,
                       ticktick_token,ticktick_project,ntfy_url,webhook_url,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET email=excluded.email,
                       budget_alerts=excluded.budget_alerts,
                       reminder_enabled=excluded.reminder_enabled,
                       reminder_day=excluded.reminder_day,
                       ticktick_token=excluded.ticktick_token,
                       ticktick_project=excluded.ticktick_project,
                       ntfy_url=excluded.ntfy_url, webhook_url=excluded.webhook_url,
                       updated_at=excluded.updated_at""",
                (p.user_id, p.email, int(p.budget_alerts), int(p.reminder_enabled),
                 p.reminder_day, self._enc(p.ticktick_token), p.ticktick_project,
                 self._enc(p.ntfy_url), self._enc(p.webhook_url), time.time()))
            self._con.commit()

    def reminder_candidates(self, day: int) -> list[Prefs]:
        with self._lock:
            ids = [r["user_id"] for r in self._con.execute(
                "SELECT user_id FROM prefs WHERE reminder_enabled=1 AND reminder_day=?", (day,))]
        return [self.get(uid) for uid in ids]

    # ── États OAuth (usage unique, 10 min) ───────────────────
    def new_state(self, user_id: str) -> str:
        state = secrets.token_urlsafe(32)
        with self._lock:
            self._con.execute("DELETE FROM oauth_states WHERE expires_at < ?", (time.time(),))
            self._con.execute("INSERT INTO oauth_states VALUES(?,?,?)",
                              (state, user_id, time.time() + 600))
            self._con.commit()
        return state

    def consume_state(self, state: str, user_id: str) -> bool:
        with self._lock:
            row = self._con.execute("SELECT * FROM oauth_states WHERE state=?", (state,)).fetchone()
            self._con.execute("DELETE FROM oauth_states WHERE state=?", (state,))
            self._con.commit()
        return bool(row and row["user_id"] == user_id and row["expires_at"] > time.time())

    # ── Anti-doublon ─────────────────────────────────────────
    def mark_once(self, key: str) -> bool:
        """True la première fois pour cette clé, False ensuite."""
        with self._lock:
            cur = self._con.execute("INSERT OR IGNORE INTO sent VALUES(?,?)", (key, time.time()))
            self._con.execute("DELETE FROM sent WHERE sent_at < ?", (time.time() - 400 * 86400,))
            self._con.commit()
            return cur.rowcount == 1

    def close(self) -> None:
        with self._lock:
            self._con.close()
