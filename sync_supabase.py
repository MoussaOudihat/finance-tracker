"""
sync_supabase.py — Synchronisation SQLite ↔ Supabase PostgreSQL (tables)

Stratégie :
  • L'app utilise TOUJOURS SQLite local comme source principale.
  • Au démarrage : pull depuis Supabase si le timestamp distant est plus récent.
  • À la fermeture : push (upsert) toutes les tables vers Supabase.
  • Un timestamp `last_supabase_sync` dans app_settings pilote la direction.
  • Les clés sensibles (URL, clé API, mode DB) ne sont jamais synchronisées.
"""
import os
import shutil
import sqlite3
import threading
import datetime
from typing import Optional
from logger import log

# ── Ordre d'insertion (respecte les FK) ─────────────────────
PUSH_ORDER = [
    "categories",
    "months",
    "expenses",
    "revenues",
    "savings",
    "assets",
    "asset_transactions",
    "budgets",
    "savings_goals",
]

# ── Ordre de suppression (inverse FK) ───────────────────────
DELETE_ORDER = list(reversed(PUSH_ORDER))

# ── Clés app_settings à ne jamais synchroniser ──────────────
SETTINGS_EXCLUDE = {
    "supabase_url",
    "supabase_service_key",
    "db_mode",
    "dark_mode",
    "email_address",
    "smtp_password",
    "ai_api_key",    # clé API IA — jamais synchronisée (sensible)
    "ai_provider",   # lié à la clé, exclu par cohérence
    # cache IA local (volumeux, propre à chaque machine)
    "ai_cache_1m_result", "ai_cache_1m_ts",
    "ai_cache_3m_result", "ai_cache_3m_ts",
    "ai_cache_6m_result", "ai_cache_6m_ts",
}

SYNC_TS_KEY = "last_supabase_sync"
BATCH_SIZE  = 500


class SupabaseSync:
    """Gère la synchronisation SQLite ↔ Supabase PostgreSQL table par table."""

    def __init__(self, url: str, key: str, db_path: str):
        from supabase import create_client
        self._client   = create_client(url.strip(), key.strip())
        self._db_path  = db_path
        self._lock     = threading.Lock()
        self._last_push: Optional[datetime.datetime] = None

    # ─────────────────────────────────────────────────────────
    #  Test de connexion
    # ─────────────────────────────────────────────────────────
    def test_connection(self) -> tuple[bool, str]:
        """Vérifie la connexion ET l'existence des tables."""
        try:
            self._client.table("categories").select("id").limit(1).execute()
            return True, "✅  Connexion Supabase OK — tables trouvées"
        except Exception as e:
            err = str(e)
            if any(kw in err for kw in ("does not exist", "relation", "42P01", "undefined")):
                return False, (
                    "⚠️  Connexion OK mais tables absentes.\n"
                    "Exécutez le script SQL fourni dans l'éditeur Supabase."
                )
            return False, f"❌  {e}"

    # ─────────────────────────────────────────────────────────
    #  Pull — téléchargement si Supabase plus récent
    # ─────────────────────────────────────────────────────────
    def pull_if_newer(self) -> tuple[bool, str]:
        """Compare les timestamps et télécharge si le distant est plus récent."""
        try:
            # Y a-t-il des données distantes ?
            chk = self._client.table("months").select("id").limit(1).execute()
            if not chk.data:
                return False, "Aucune donnée distante — premier lancement."

            # Timestamp distant
            res_ts = (
                self._client.table("app_settings")
                .select("value")
                .eq("key", SYNC_TS_KEY)
                .execute()
            )
            if not res_ts.data:
                return False, "Pas de timestamp distant — skip pull."

            remote_ts = datetime.datetime.fromisoformat(res_ts.data[0]["value"])

            # Timestamp local
            con = sqlite3.connect(self._db_path)
            local_row = con.execute(
                "SELECT value FROM app_settings WHERE key=?", (SYNC_TS_KEY,)
            ).fetchone()
            con.close()

            if local_row:
                local_ts = datetime.datetime.fromisoformat(local_row[0])
                if local_ts >= remote_ts:
                    return False, "Base locale déjà à jour."

            self._do_pull()
            return True, "✅  Données synchronisées depuis Supabase."

        except Exception as e:
            return False, f"⚠️  Pull échoué : {e}"

    def _do_pull(self):
        # Backup local AVANT tout écrasement.
        # On vérifie que la copie a réussi avant de toucher aux données locales.
        bak_path = self._db_path + ".bak"
        if self._db_path and os.path.exists(self._db_path):
            try:
                shutil.copy2(self._db_path, bak_path)
                if not os.path.exists(bak_path):
                    raise OSError("fichier .bak introuvable après copie")
            except Exception as exc:
                raise RuntimeError(
                    f"Backup échoué — pull annulé pour protéger vos données locales. "
                    f"Cause : {exc}"
                ) from exc

        con = sqlite3.connect(self._db_path)
        con.execute("PRAGMA foreign_keys=OFF")

        # Sauvegarder les clés locales sensibles avant de vider
        saved = {}
        for key in SETTINGS_EXCLUDE:
            row = con.execute(
                "SELECT value FROM app_settings WHERE key=?", (key,)
            ).fetchone()
            if row:
                saved[key] = row[0]

        # Vider les tables locales (ordre inverse FK)
        for table in DELETE_ORDER:
            try:
                con.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError as e:
                log.warning("Pull — impossible de vider la table %s : %s", table, e)
        con.execute("DELETE FROM app_settings")

        # Remettre les clés sensibles
        for key, value in saved.items():
            con.execute(
                "INSERT INTO app_settings(key,value) VALUES(?,?)", (key, value)
            )
        con.commit()

        # Remplir depuis Supabase (ordre FK)
        for table in PUSH_ORDER:
            try:
                all_rows = self._fetch_all(table)
                if not all_rows:
                    continue
                cols         = list(all_rows[0].keys())
                col_names    = ",".join(cols)
                placeholders = ",".join(["?" for _ in cols])
                for row in all_rows:
                    con.execute(
                        f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
                        [row[c] for c in cols],
                    )
            except Exception:
                log.warning("Pull — erreur lors du remplissage de la table %s", table, exc_info=True)

        # Sync app_settings distants (hors clés sensibles)
        try:
            res = self._client.table("app_settings").select("*").execute()
            for row in res.data:
                if row["key"] not in SETTINGS_EXCLUDE:
                    con.execute(
                        "INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)",
                        (row["key"], row["value"]),
                    )
        except Exception:
            log.warning("Pull — erreur sync app_settings distants", exc_info=True)

        con.execute("PRAGMA foreign_keys=ON")
        con.commit()
        con.close()

    def _fetch_all(self, table: str) -> list[dict]:
        """Télécharge toutes les lignes d'une table en paginant."""
        all_rows: list[dict] = []
        offset = 0
        while True:
            res = (
                self._client.table(table)
                .select("*")
                .range(offset, offset + BATCH_SIZE - 1)
                .execute()
            )
            all_rows.extend(res.data)
            if len(res.data) < BATCH_SIZE:
                break
            offset += BATCH_SIZE
        return all_rows

    # ─────────────────────────────────────────────────────────
    #  Push — upload vers Supabase
    # ─────────────────────────────────────────────────────────
    def push(self, blocking: bool = False, on_done=None):
        """Upload toutes les tables vers Supabase.
        blocking=True pour l'appel à la fermeture."""
        if blocking:
            msg = self._do_push()
            if on_done:
                on_done(msg)
        else:
            def _run():
                msg = self._do_push()
                if on_done:
                    on_done(msg)
            threading.Thread(target=_run, daemon=True).start()

    def _do_push(self) -> str:
        with self._lock:
            try:
                con = sqlite3.connect(self._db_path)
                con.row_factory = sqlite3.Row

                # ── 1. Supprimer les données distantes (ordre inverse FK) ──
                for table in DELETE_ORDER:
                    try:
                        self._client.table(table).delete().gt("id", 0).execute()
                    except Exception:
                        log.warning("Push — impossible de vider la table distante %s", table, exc_info=True)

                # app_settings : supprimer uniquement les clés non-sensibles
                try:
                    existing = (
                        self._client.table("app_settings").select("key").execute()
                    )
                    for row in existing.data:
                        if row["key"] not in SETTINGS_EXCLUDE:
                            (
                                self._client.table("app_settings")
                                .delete()
                                .eq("key", row["key"])
                                .execute()
                            )
                except Exception:
                    log.warning("Push — erreur nettoyage app_settings distants", exc_info=True)

                # ── 2. Insérer les données locales (ordre FK) ──────────────
                for table in PUSH_ORDER:
                    rows = con.execute(f"SELECT * FROM {table}").fetchall()
                    if not rows:
                        continue
                    data = [dict(r) for r in rows]
                    for i in range(0, len(data), BATCH_SIZE):
                        self._client.table(table).upsert(
                            data[i : i + BATCH_SIZE]
                        ).execute()

                # ── 3. app_settings non-sensibles ─────────────────────────
                settings = con.execute(
                    "SELECT key, value FROM app_settings"
                ).fetchall()
                for row in settings:
                    if row["key"] not in SETTINGS_EXCLUDE:
                        self._client.table("app_settings").upsert(
                            {"key": row["key"], "value": row["value"]}
                        ).execute()

                # ── 4. Timestamp de sync ───────────────────────────────────
                ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
                self._client.table("app_settings").upsert(
                    {"key": SYNC_TS_KEY, "value": ts}
                ).execute()
                con.execute(
                    "INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)",
                    (SYNC_TS_KEY, ts),
                )
                con.commit()
                con.close()

                self._last_push = datetime.datetime.now(datetime.timezone.utc)
                return "✅  Synchronisation Supabase OK"

            except Exception as e:
                return f"⚠️  Push échoué : {e}"

    # ─────────────────────────────────────────────────────────
    #  Informations
    # ─────────────────────────────────────────────────────────
    @property
    def last_push_str(self) -> str:
        if not self._last_push:
            return "—"
        return self._last_push.strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def from_db(db) -> "SupabaseSync | None":
        """Construit un SupabaseSync depuis les settings DB."""
        if db.get_setting("db_mode", "local") != "online":
            return None
        url = db.get_setting("supabase_url", "")
        key = db.get_setting("supabase_service_key", "")
        if not url or not key:
            return None
        try:
            from config import DB_PATH
            return SupabaseSync(url, key, DB_PATH)
        except Exception:
            return None
