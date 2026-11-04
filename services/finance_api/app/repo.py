"""
repo.py — Accès aux données Supabase via PostgREST, AU NOM de l'utilisateur.

Chaque requête porte le jeton d'accès de l'utilisateur (Authorization:
Bearer) : PostgreSQL applique alors la Row Level Security (user_id =
auth.uid()). Le filtre user_id=eq.<uid> est ajouté en plus (défense en
profondeur). La clé service_role n'est jamais utilisée.

Écritures LIGNE PAR LIGNE (et non plus « tout supprimer puis tout
réinsérer » comme la synchro desktop) : une saisie web ne peut plus effacer
les données d'un autre appareil. Chaque écriture fait avancer l'horodatage
`last_supabase_sync` : l'app desktop sait ainsi qu'elle doit récupérer les
données avant d'envoyer les siennes (voir sync_supabase.check_remote_newer).

Identifiants : le schéma (partagé avec l'app desktop/SQLite) utilise des
id BIGINT attribués par le client, uniques par (user_id, id). On prend
max(id)+1 et on réessaie en cas de conflit (HTTP 409).
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any
from collections.abc import Iterable

import httpx
from fastapi import HTTPException

from fintrack_common.auth import User

log = logging.getLogger(__name__)

PAGE = 1000
SYNC_TS_KEY = "last_supabase_sync"


class Repo:
    def __init__(self, http: httpx.Client, anon_key: str, user: User):
        self.http = http
        self.user = user
        self.headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {user.token}",
            "Accept": "application/json",
        }

    # ── Bas niveau ───────────────────────────────────────────
    def _check(self, r: httpx.Response) -> httpx.Response:
        if r.status_code == 401:            # jeton refusé par PostgREST
            raise HTTPException(401, "Session Supabase expirée — reconnectez-vous.")
        if r.status_code == 403:            # RLS / droits : erreur de données, pas de session
            log.warning("PostgREST 403 sur %s %s", r.request.method, r.request.url.path)
            raise HTTPException(403, "Opération refusée par la base de données.")
        if r.status_code >= 400:
            log.warning("PostgREST %s %s -> %s", r.request.method,
                        r.request.url.path, r.status_code)
            raise HTTPException(502, "Erreur de la base de données.")
        return r

    def _params(self, filters: dict | None) -> dict:
        p = {"user_id": f"eq.{self.user.id}"}
        p.update(filters or {})
        return p

    def select(self, table: str, filters: dict | None = None, *, columns: str = "*",
               order: str | None = None, limit: int | None = None) -> list[dict]:
        params = self._params(filters)
        params["select"] = columns
        # Ordre TOUJOURS déterminé : sans ORDER BY, Postgres peut renvoyer une
        # ligne deux fois (ou jamais) d'une page à l'autre.
        params["order"] = order or ("key.asc" if table == "app_settings" else "id.asc")
        rows: list[dict] = []
        offset = 0
        while True:
            page = min(PAGE, limit - len(rows)) if limit else PAGE
            params.update(limit=str(page), offset=str(offset))
            r = self._check(self.http.get(f"/rest/v1/{table}", params=params,
                                          headers=self.headers))
            batch = r.json()
            rows.extend(batch)
            if len(batch) < page or (limit and len(rows) >= limit):
                return rows
            offset += page

    def _next_id(self, table: str) -> int:
        rows = self.select(table, columns="id", order="id.desc", limit=1)
        return (rows[0]["id"] + 1) if rows else 1

    def insert(self, table: str, row: dict, *, attempts: int = 5) -> dict:
        for _ in range(attempts):
            payload = {**row, "id": self._next_id(table), "user_id": self.user.id}
            r = self.http.post(f"/rest/v1/{table}", json=payload, headers={
                **self.headers, "Prefer": "return=representation"})
            if r.status_code == 409:      # id pris entre-temps : on réessaie
                continue
            return self._check(r).json()[0]
        raise HTTPException(409, "Conflit d'écriture — réessayez.")

    def update(self, table: str, filters: dict, values: dict) -> list[dict]:
        r = self.http.patch(f"/rest/v1/{table}", params=self._params(filters), json=values,
                            headers={**self.headers, "Prefer": "return=representation"})
        return self._check(r).json()

    def delete(self, table: str, filters: dict) -> list[dict]:
        r = self.http.delete(f"/rest/v1/{table}", params=self._params(filters),
                             headers={**self.headers, "Prefer": "return=representation"})
        return self._check(r).json()

    def upsert(self, table: str, row: dict, on_conflict: str) -> None:
        r = self.http.post(
            f"/rest/v1/{table}", params={"on_conflict": on_conflict},
            json={**row, "user_id": self.user.id},
            headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        self._check(r)

    def touch_sync_ts(self) -> None:
        """Signale aux autres appareils (desktop) que les données distantes
        ont changé : leur prochain envoi sera refusé tant qu'ils n'ont pas
        récupéré ces modifications."""
        ts = dt.datetime.now(dt.UTC).isoformat()
        self.upsert("app_settings", {"key": SYNC_TS_KEY, "value": ts}, "user_id,key")

    # ── Mois ─────────────────────────────────────────────────
    def month(self, year: int, month: int, *, create: bool) -> dict | None:
        rows = self.select("months", {"year": f"eq.{year}", "month": f"eq.{month}"})
        if rows:
            return rows[0]
        if not create:
            return None
        try:
            return self.insert("months", {"year": year, "month": month, "closed": 0})
        except HTTPException:
            # Créé en parallèle (contrainte unique user_id/year/month) : relire.
            rows = self.select("months", {"year": f"eq.{year}", "month": f"eq.{month}"})
            if rows:
                return rows[0]
            raise

    def months_by_id(self, ids: Iterable[int]) -> dict[int, dict]:
        ids = sorted(set(ids))
        if not ids:
            return {}
        rows = self.select("months", {"id": f"in.({','.join(map(str, ids))})"})
        return {r["id"]: r for r in rows}

    def rows_for_months(self, table: str, month_ids: list[int], columns: str = "*") -> list[dict]:
        if not month_ids:
            return []
        return self.select(table, {"month_id": f"in.({','.join(map(str, month_ids))})"},
                           columns=columns)

    def get_one(self, table: str, entry_id: int) -> dict | None:
        rows = self.select(table, {"id": f"eq.{entry_id}"}, limit=1)
        return rows[0] if rows else None


def in_filter(values: Iterable[Any]) -> str:
    """Filtre PostgREST `in.(...)` pour des chaînes (guillemets échappés)."""
    quoted = []
    for v in values:
        s = str(v).replace("\\", "\\\\").replace('"', '\\"')
        quoted.append(f'"{s}"')
    return f"in.({','.join(quoted)})"
