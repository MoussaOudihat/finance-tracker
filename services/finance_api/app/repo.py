"""
repo.py — Accès aux données Supabase via PostgREST, AU NOM de l'utilisateur.

Chaque requête porte le jeton d'accès de l'utilisateur (Authorization:
Bearer) : PostgreSQL applique alors la Row Level Security (user_id =
auth.uid()). Le filtre user_id=eq.<uid> est ajouté en plus (défense en
profondeur). La clé service_role n'est jamais utilisée.

Lectures : PostgREST (select paginé). Écritures : UNE transaction par
opération métier, via la fonction SQL `fintrack_apply` (migration
supabase/migration_v2_3_atomic.sql) :
  • tout ou rien (récurrentes, épargne → patrimoine, saisie groupée…) ;
  • identifiants attribués en SQL sous un verrou par utilisateur (plus de
    max(id)+1 côté client ni de réessais) ;
  • « mois clôturé ? » vérifié dans la même transaction que l'écriture ;
  • la version de synchronisation (`last_supabase_sync`) avance dans cette
    même transaction : l'app desktop sait toujours qu'elle doit récupérer
    les données avant d'envoyer les siennes.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

import httpx
from fastapi import HTTPException

from fintrack_common.auth import User

log = logging.getLogger(__name__)

PAGE = 1000
SYNC_TS_KEY = "last_supabase_sync"
CLOSED_MSG = "Ce mois est clôturé : saisie verrouillée."

# Erreurs levées par fintrack_apply (RAISE EXCEPTION 'fintrack:…')
_RPC_ERRORS = {
    "fintrack:month_closed": (409, CLOSED_MSG),
    "fintrack:not_found": (404, "Élément introuvable."),
    "fintrack:conflict": (409, "Modifié entre-temps par une autre requête — rechargez la page "
                               "et réessayez."),
}


def ref(index: int, field: str = "id") -> dict:
    """Référence au résultat d'une opération précédente du même lot
    (ex. l'id du mois créé par l'opération 0)."""
    return {"$ref": [index, field]}


class Repo:
    def __init__(self, http: httpx.Client, anon_key: str, user: User):
        self.http = http
        self.user = user
        self.headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {user.token}",
            "Accept": "application/json",
        }
        self._cache: dict[str, Any] = {}

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

    def apply(self, ops: list[dict]) -> list[Any]:
        """Exécute `ops` en UNE transaction (fonction SQL fintrack_apply) et
        renvoie le résultat de chaque opération."""
        r = self.http.post("/rest/v1/rpc/fintrack_apply", json={"ops": ops},
                           headers=self.headers)
        self._cache.clear()                 # données modifiées : relire
        if r.status_code >= 400 and r.status_code not in (401, 403):
            try:
                err = r.json()
            except ValueError:
                err = {}
            msg, code = str(err.get("message", "")), str(err.get("code", ""))
            if msg in _RPC_ERRORS:
                raise HTTPException(*_RPC_ERRORS[msg])
            if code == "23503":             # clé étrangère : catégorie, mois…
                raise HTTPException(422, "Référence inconnue (catégorie ou mois).")
            if code == "23505":
                raise HTTPException(409, "Conflit d'écriture — réessayez.")
            if code == "PGRST202":          # fonction absente
                log.error("fintrack_apply introuvable : appliquez supabase/migration_v2_3_atomic.sql")
                raise HTTPException(503, "Base de données non migrée (v2.3).")
        return self._check(r).json()["results"]

    def cached(self, key: str, load: Callable[[], Any]) -> Any:
        """Mémoïsation pour la durée de la requête (un Repo par requête) ;
        vidée à chaque écriture."""
        if key not in self._cache:
            self._cache[key] = load()
        return self._cache[key]

    # ── Mois ─────────────────────────────────────────────────
    def month(self, year: int, month: int) -> dict | None:
        """Lecture seule. La création d'un mois se fait dans la transaction
        de l'écriture (opération « month » de fintrack_apply)."""
        rows = self.select("months", {"year": f"eq.{year}", "month": f"eq.{month}"})
        return rows[0] if rows else None

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
