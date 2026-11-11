"""
sync_supabase.py — Synchronisation SQLite ↔ Supabase PostgreSQL (tables)

Stratégie :
  • L'app utilise TOUJOURS SQLite local comme source principale.
  • Au démarrage : pull depuis Supabase si la version distante diffère de
    celle connue localement.
  • À la fermeture : push de toutes les tables en UNE transaction
    (fonction SQL fintrack_replace_snapshot : tout ou rien).
  • La version `last_supabase_sync` (jeton opaque attribué par le serveur)
    pilote la direction. Elle est comparée par ÉGALITÉ, jamais par ordre :
    les horloges du PC et du serveur ne sont jamais comparées entre elles.
  • Les clés sensibles (URL, mode DB, identité) ne sont jamais synchronisées.

Mode cloud (multi-utilisateur) :
  • Le client Supabase est authentifié via Supabase Auth (clé anon + session
    utilisateur, voir cloud_auth.py) — plus de clé service_role dans l'app.
    RLS (Row Level Security) impose côté serveur que chaque utilisateur ne
    voit/modifie que ses propres lignes.
  • Chaque ligne poussée est taguée `user_id` ; chaque lecture/suppression
    est filtrée par `user_id` (défense en profondeur, en plus de RLS).
  • Les tables locales SQLite n'ont PAS de colonne `user_id` (une base locale
    ne sert qu'un seul compte à la fois) : elle est ajoutée à l'upload,
    retirée au téléchargement.
"""
import os
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from logger import log

# ── Ordre d'insertion (respecte les FK) ─────────────────────
# "recurring_transactions" doit rester après "categories" (FK category_id).
PUSH_ORDER = [
    "categories",
    "months",
    "expenses",
    "revenues",
    "savings",
    "assets",
    "asset_transactions",
    "liabilities",
    "budgets",
    "savings_goals",
    "recurring_transactions",
]

# ── Ordre de suppression (inverse FK) ───────────────────────
DELETE_ORDER = list(reversed(PUSH_ORDER))

# ── Clés app_settings à ne jamais synchroniser ──────────────
# RÈGLE : toute clé contenant un secret, une PII locale, ou une config
# propre à une machine/session doit être listée ici. Pas de wildcards.
SETTINGS_EXCLUDE = {
    # ── Connexion Supabase / identité cloud ──────────────────
    "supabase_url",             # config locale
    "supabase_anon_key",        # config locale (pas secrète, mais pas une donnée financière)
    "supabase_refresh_token",   # CRITIQUE — vit dans le trousseau OS, jamais en DB
    "supabase_user_id",         # identité de session, propre à la machine connectée
    "supabase_user_email",      # idem
    "db_mode",                  # config locale machine

    # ── Préférences locales (non partagées entre machines) ──
    "dark_mode",

    # ── SMTP — toutes les clés (les vraies clés utilisées) ──
    "smtp_host",              # config locale
    "smtp_port",              # config locale
    "smtp_user",              # identifiant email
    "smtp_pass",              # CRITIQUE — mot de passe email
    "smtp_to",                # adresse destinataire (PII)
    "smtp_tls",               # config locale
    # Ancien nom — conservé pour rétrocompat d'éventuelles vieilles DB
    "smtp_password",
    "email_address",

    # ── IA ───────────────────────────────────────────────────
    "ai_api_key",             # CRITIQUE — clé API Gemini/IA
    "ai_provider",            # lié à la clé, exclu par cohérence

    # ── Cache IA local (volumeux, propre à chaque machine) ──
    "ai_cache_1m_result", "ai_cache_1m_ts",
    "ai_cache_3m_result", "ai_cache_3m_ts",
    "ai_cache_6m_result", "ai_cache_6m_ts",

    # ── Auth locale (mode offline) ───────────────────────────
    # Les clés auth ne sont pas dans les tables sync,
    # mais on les exclut par précaution si elles apparaissent
    "auth_password_hash",
    "auth_password_salt",
    "auth_secret_answer_hash",
    "auth_secret_answer_salt",
    "auth_session_token",
    "auth_session_expiry",
}

SYNC_TS_KEY = "last_supabase_sync"
CONFLICT_MSG = (
    "⚠️  Les données Supabase ont été modifiées ailleurs (interface web ou "
    "autre PC) depuis votre dernière synchronisation. Envoi annulé pour ne "
    "pas les écraser : récupérez d'abord les données depuis Supabase "
    "(Paramètres → Synchronisation), puis ressaisissez vos modifications "
    "locales récentes si besoin."
)
BATCH_SIZE  = 500

# Ensemble des noms de tables autorisés dans les requêtes dynamiques.
# Toute table hors de cet ensemble provoque une ValueError, ce qui protège
# contre une injection SQL si PUSH_ORDER était modifié par erreur.
_ALLOWED_TABLES: frozenset[str] = frozenset(PUSH_ORDER)

# Si le local a moins de la moitié du total distant, on refuse un push
# destructeur sans confirmation explicite (voir check_push_safety).
_PUSH_SAFETY_RATIO = 0.5


def _push_error_message(exc: Exception) -> str:
    """Message utilisateur d'un envoi refusé, d'après le CODE d'erreur
    PostgREST/PostgreSQL (jamais d'après le texte, qui peut citer le nom de
    la fonction pour une toute autre erreur)."""
    code = str(getattr(exc, "code", "") or "")
    message = str(getattr(exc, "message", "") or exc)
    if "fintrack:sync_conflict" in message:
        log.warning("[Sync] Push refusé par le serveur : version distante modifiée.")
        return CONFLICT_MSG
    if code == "PGRST202":                  # fonction RPC introuvable
        return ("⚠️  Push échoué : base Supabase non migrée — exécutez "
                "supabase/migration_v2_3_atomic.sql.")
    if code == "57014":                     # statement_timeout dépassé
        return ("⚠️  Push échoué : délai dépassé côté Supabase (base volumineuse). "
                "Rien n'a été modifié. Voir docs/MIGRATION_V2_3.md, « Délai d'envoi ».")
    return f"⚠️  Push échoué : {exc}"


def _safe_table(table: str) -> str:
    """Valide que `table` est un nom autorisé — lève ValueError sinon."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Nom de table non autorisé : '{table}'")
    return table


class SupabaseSync:
    """Gère la synchronisation SQLite ↔ Supabase PostgreSQL table par table,
    pour l'utilisateur Supabase Auth actuellement connecté."""

    def __init__(self, client, db_path: str, user_id: str):
        """
        client  : supabase-py Client déjà authentifié (clé anon + session
                  Supabase Auth active — voir cloud_auth.build_client /
                  sign_in / try_silent_refresh).
        user_id : UUID (str) de l'utilisateur Supabase Auth connecté.
        """
        self._client    = client
        self._db_path   = db_path
        self._user_id   = user_id
        self._lock      = threading.Lock()
        # Event mis à True dès qu'aucun push async n'est en cours.
        # push(blocking=True) attend ce signal avant de démarrer.
        self._idle      = threading.Event()
        self._idle.set()          # au démarrage : aucun push en cours

    # ─────────────────────────────────────────────────────────
    #  Pull — téléchargement si Supabase plus récent
    # ─────────────────────────────────────────────────────────
    def pull_if_newer(self) -> tuple[bool, str]:
        """Télécharge si la version distante diffère de la version locale."""
        try:
            # Y a-t-il des données distantes pour CET utilisateur ?
            chk = (
                self._client.table("months").select("id")
                .eq("user_id", self._user_id).limit(1).execute()
            )
            if not chk.data:
                return False, "Aucune donnée distante — premier lancement."

            # Version distante — son absence ne doit JAMAIS empêcher un pull
            # nécessaire : elle ne sert qu'à éviter un pull redondant quand on
            # peut prouver que le local est déjà à jour (même version).
            remote_v = self._remote_version()
            if remote_v is not None and remote_v == self._local_version():
                return False, "Base locale déjà à jour."

            self._do_pull()
            return True, "✅  Données synchronisées depuis Supabase."

        except Exception as e:
            return False, f"⚠️  Pull échoué : {e}"

    def _do_pull(self):
        # ── 1. Backup local AVANT tout écrasement ───────────────
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

        try:
            # ── 2. Sauvegarder les clés sensibles ───────────────
            saved = {}
            for key in SETTINGS_EXCLUDE:
                row = con.execute(
                    "SELECT value FROM app_settings WHERE key=?", (key,)
                ).fetchone()
                if row:
                    saved[key] = row[0]

            # ── 3. Vider les tables locales (ordre inverse FK) ──
            for table in DELETE_ORDER:
                try:
                    con.execute(f"DELETE FROM {_safe_table(table)}")  # noqa: S608
                except sqlite3.OperationalError as e:
                    log.warning("Pull — impossible de vider la table %s : %s", table, e)
            con.execute("DELETE FROM app_settings")

            # ── 4. Restaurer les clés sensibles ─────────────────
            for key, value in saved.items():
                con.execute(
                    "INSERT INTO app_settings(key,value) VALUES(?,?)", (key, value)
                )
            con.commit()

            # ── 5. Version distante lue AVANT les données ───────
            # Si une saisie web arrive pendant le téléchargement, la version
            # locale reste l'ANCIENNE : le prochain envoi sera refusé (version
            # différente) au lieu d'écraser une saisie absente du local.
            # Lue après les données, elle pouvait être plus récente qu'elles.
            version = self._remote_version()

            # ── 6. Remplir depuis Supabase (ordre FK), filtré par user_id ──
            # Une table illisible annule TOUTE la récupération (sauvegarde
            # restaurée) : une base locale partielle marquée « à jour »
            # écraserait ensuite les données distantes au prochain envoi.
            for table in PUSH_ORDER:
                all_rows = self._fetch_all(table)
                if not all_rows:
                    continue
                # La table locale n'a pas de colonne user_id — la retirer.
                all_rows = [
                    {k: v for k, v in row.items() if k != "user_id"}
                    for row in all_rows
                ]
                cols         = list(all_rows[0].keys())
                col_names    = ",".join(cols)
                placeholders = ",".join(["?" for _ in cols])
                for row in all_rows:
                    con.execute(
                        f"INSERT OR REPLACE INTO {_safe_table(table)} ({col_names}) VALUES ({placeholders})",  # noqa: S608
                        [row[c] for c in cols],
                    )

            # ── 7. Sync app_settings distants (hors clés sensibles) ──
            # Échec = récupération annulée, comme pour les tables : marquée à
            # jour sans ses réglages, la base locale les effacerait sur le
            # serveur au prochain envoi.
            res = (
                self._client.table("app_settings").select("*")
                .eq("user_id", self._user_id).execute()
            )
            for row in res.data:
                if row["key"] not in SETTINGS_EXCLUDE and row["key"] != SYNC_TS_KEY:
                    con.execute(
                        "INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)",
                        (row["key"], row["value"]),
                    )
            # Version locale = celle lue AVANT les données (voir étape 5)
            if version is not None:
                con.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)",
                            (SYNC_TS_KEY, version))

            con.execute("PRAGMA foreign_keys=ON")
            con.commit()
            con.close()

        except Exception:
            # ── Rollback : restaurer le backup local ────────────
            con.close()
            if os.path.exists(bak_path):
                try:
                    shutil.copy2(bak_path, self._db_path)
                    log.warning("Pull échoué — backup restauré depuis %s", bak_path)
                except Exception as restore_exc:
                    log.error(
                        "Pull échoué ET restauration du backup impossible : %s",
                        restore_exc,
                    )
            raise

    def _fetch_all(self, table: str) -> list[dict]:
        """Télécharge toutes les lignes d'une table (pour cet utilisateur), en paginant."""
        all_rows: list[dict] = []
        offset = 0
        while True:
            res = (
                self._client.table(table)
                .select("*")
                .eq("user_id", self._user_id)
                .range(offset, offset + BATCH_SIZE - 1)
                .execute()
            )
            all_rows.extend(res.data)
            if len(res.data) < BATCH_SIZE:
                break
            offset += BATCH_SIZE
        return all_rows

    # ─────────────────────────────────────────────────────────
    #  Garde-fou anti-écrasement (incident du 06/09/2026)
    # ─────────────────────────────────────────────────────────
    def _remote_row_counts(self) -> dict[str, int]:
        """Comptage par table — en parallèle (10+ requêtes HTTP sinon
        exécutées séquentiellement, ~150-200ms chacune)."""
        def _count_one(table: str) -> int:
            try:
                res = (
                    self._client.table(table)
                    .select("id", count="exact")
                    .eq("user_id", self._user_id)
                    .limit(1)
                    .execute()
                )
                return res.count or 0
            except Exception:
                log.warning("check_push_safety — comptage distant échoué pour %s", table, exc_info=True)
                return 0

        with ThreadPoolExecutor(max_workers=len(PUSH_ORDER)) as pool:
            results = pool.map(_count_one, PUSH_ORDER)
        return dict(zip(PUSH_ORDER, results, strict=False))

    def _local_row_counts(self) -> dict[str, int]:
        con = sqlite3.connect(self._db_path)
        try:
            counts = {
                t: con.execute(f"SELECT COUNT(*) FROM {_safe_table(t)}").fetchone()[0]  # noqa: S608
                for t in PUSH_ORDER
            }
        finally:
            con.close()
        return counts

    def check_push_safety(self) -> tuple[bool, str, dict, dict]:
        """Compare comptages local vs distant avant un push destructeur.
        Retourne (safe, message, remote_counts, local_counts)."""
        remote = self._remote_row_counts()
        local  = self._local_row_counts()
        remote_total, local_total = sum(remote.values()), sum(local.values())
        if remote_total > 0 and local_total < remote_total * _PUSH_SAFETY_RATIO:
            msg = (
                f"⚠️  Supabase contient {remote_total} lignes au total, "
                f"la base locale seulement {local_total}. Un envoi écraserait "
                f"des données distantes plus complètes. Récupérez d'abord "
                f"depuis Supabase, ou confirmez explicitement l'envoi."
            )
            return False, msg, remote, local
        return True, "", remote, local

    # ─────────────────────────────────────────────────────────
    #  Push — upload vers Supabase
    # ─────────────────────────────────────────────────────────
    def push(self, blocking: bool = False, on_done=None, force: bool = False):
        """Upload toutes les tables vers Supabase.

        blocking=True : attend la fin d'un éventuel push async en cours,
        puis exécute le push dans le thread appelant (fermeture propre).
        blocking=False : lance un thread daemon (auto-sync périodique).
        force=True : ignore le garde-fou check_push_safety (à n'utiliser
        qu'après confirmation explicite de l'utilisateur, comptages affichés).
        """
        if blocking:
            # Attendre max 30 s qu'un push async en cours se termine
            if not self._idle.wait(timeout=30):
                log.warning("[Sync] Timeout en attendant la fin du push async.")
            msg = self._do_push(force=force)
            if on_done:
                on_done(msg)
        else:
            def _run():
                self._idle.clear()   # signale qu'un push est en cours
                try:
                    msg = self._do_push(force=force)
                    if on_done:
                        on_done(msg)
                finally:
                    self._idle.set() # redevient disponible
            threading.Thread(target=_run, daemon=True).start()

    def _remote_version(self) -> str | None:
        res = (
            self._client.table("app_settings").select("value")
            .eq("key", SYNC_TS_KEY).eq("user_id", self._user_id).execute()
        )
        return res.data[0]["value"] if res.data else None

    def _local_version(self) -> str | None:
        con = sqlite3.connect(self._db_path)
        try:
            row = con.execute("SELECT value FROM app_settings WHERE key=?",
                              (SYNC_TS_KEY,)).fetchone()
        finally:
            con.close()
        return row[0] if row and row[0] else None

    def _set_local_version(self, version: str) -> None:
        con = sqlite3.connect(self._db_path)
        try:
            con.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)",
                        (SYNC_TS_KEY, version))
            con.commit()
        finally:
            con.close()

    def check_remote_newer(self) -> tuple[bool, str]:
        """Verrou optimiste : les données distantes ont-elles changé depuis
        la dernière synchronisation de CETTE base (saisie depuis l'interface
        web, ou depuis un autre PC) ? Le push remplace tout : pousser
        par-dessus effacerait ces modifications.

        Comparaison par ÉGALITÉ de la version (et non « plus récent que ») :
        un PC dont l'horloge avance ne peut plus faire passer une saisie web
        pour plus ancienne. Retourne (modifiées_ailleurs, message)."""
        remote_v = self._remote_version()
        if remote_v is None or remote_v == self._local_version():
            return False, ""
        return True, CONFLICT_MSG

    def _snapshot(self) -> tuple[dict, dict]:
        """Toutes les tables locales + réglages non sensibles."""
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        try:
            tables = {t: [dict(r) for r in con.execute(f"SELECT * FROM {_safe_table(t)}")]  # noqa: S608
                      for t in PUSH_ORDER}
            settings = {r["key"]: r["value"]
                        for r in con.execute("SELECT key, value FROM app_settings")
                        if r["key"] not in SETTINGS_EXCLUDE and r["key"] != SYNC_TS_KEY}
        finally:
            con.close()
        return tables, settings

    def _do_push(self, force: bool = False) -> str:
        with self._lock:
            if not force:
                safe, msg, _, _ = self.check_push_safety()
                if not safe:
                    log.warning("[Sync] Push refusé par le garde-fou : %s", msg)
                    return msg  # abandon — rien n'est envoyé
                try:
                    newer, msg = self.check_remote_newer()
                except Exception as exc:
                    return f"⚠️  Push annulé : vérification impossible ({exc})"
                if newer:
                    log.warning("[Sync] Push refusé : données distantes modifiées ailleurs.")
                    return msg

            try:
                tables, settings = self._snapshot()
                # UNE transaction côté serveur : suppression + réinsertion +
                # nouvelle version, ou rien du tout. La version attendue est
                # revérifiée SOUS VERROU (pas de fenêtre entre contrôle et envoi).
                res = self._client.rpc("fintrack_replace_snapshot", {
                    "p_tables": tables,
                    "p_settings": settings,
                    "p_exclude": sorted(SETTINGS_EXCLUDE),
                    "p_expected": self._local_version(),
                    "p_force": bool(force),
                }).execute()
                version = res.data
                if not isinstance(version, str) or not version:
                    return "⚠️  Push échoué : réponse inattendue du serveur."
                self._set_local_version(version)
                return "✅  Synchronisation Supabase OK"

            except Exception as e:
                return _push_error_message(e)

    # ─────────────────────────────────────────────────────────
    #  Construction
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def from_session(client, db_path: str, user_id: str) -> "SupabaseSync":
        """Construit un SupabaseSync depuis un client Supabase Auth déjà
        authentifié (voir cloud_auth.try_silent_refresh / sign_in)."""
        return SupabaseSync(client, db_path, user_id)
