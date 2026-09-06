"""
database.py — Couche d'accès aux données (SQLite)
"""
import os
import csv
import contextlib
import sqlite3
import zipfile
import io
import threading

from config import DEFAULT_CATEGORIES, MONTHS_FR, FILTER_ALL_CATS, FILTER_ALL_PAYEES
from logger import log
from utils import parse_notion_month, parse_amount


class Database:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db_path = path
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        # PRAGMAs de performance — WAL pour écritures non bloquantes,
        # synchronous=NORMAL pour vitesse, foreign_keys pour intégrité.
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("PRAGMA temp_store=MEMORY")
        self._init_schema()
        self._migrate()
        self._seed_categories()
        self._load_seed_sql_if_empty()
        self._cache: dict = {}
        self._cache_lock = threading.Lock()
        self._batch_depth = 0

    # ──────────────────────────────────────────
    #  FERMETURE PROPRE
    # ──────────────────────────────────────────
    def close(self):
        """Ferme la connexion SQLite proprement.
        Exécute un WAL checkpoint pour consolider le journal avant fermeture,
        évitant les fichiers .wal/-shm orphelins après un arrêt."""
        try:
            self.con.execute("PRAGMA wal_checkpoint(RESTART)")
        except Exception:
            pass
        self.con.close()

    # ──────────────────────────────────────────
    #  CACHE
    # ──────────────────────────────────────────
    @contextlib.contextmanager
    def batch_mode(self):
        """
        Diffère l'invalidation du cache jusqu'à la sortie du bloc, au lieu de
        vider tout le cache + réécrire les clés ai_cache_* à CHAQUE écriture
        individuelle (utile pour les imports/boucles de N écritures).
        Les commits SQLite individuels ne sont PAS différés — seul le cache
        mémoire + le cache IA en DB le sont. Aucun risque de perte de données.
        ATTENTION : ne pas utiliser autour d'un code qui relit une valeur
        cachée par _q()/get_categories() qu'une écriture précédente DANS LA
        MÊME boucle est censée avoir invalidée entre-temps.
        """
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._invalidate()

    def _invalidate(self):
        """Vide le cache des requêtes et invalide le cache IA (appelé après chaque écriture)."""
        if self._batch_depth > 0:
            return
        with self._cache_lock:
            self._cache.clear()
        # Invalider le cache IA stocké en base (analyse potentiellement obsolète)
        try:
            for nb in (1, 3, 6):
                self.con.execute(
                    "INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)",
                    (f"ai_cache_{nb}m_result", ""),
                )
                self.con.execute(
                    "INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)",
                    (f"ai_cache_{nb}m_ts", ""),
                )
            self.con.commit()
        except Exception:
            pass  # La DB peut être fermée lors d'un _on_close — non critique

    def _q(self, key: str, fn):
        """Retourne le résultat depuis le cache ou exécute fn() et le met en cache.
        Thread-safe : le lock protège lecture et écriture du dict.
        Retourne une copie de liste pour éviter la mutation du cache par l'appelant."""
        with self._cache_lock:
            if key not in self._cache:
                self._cache[key] = fn()
            result = self._cache[key]
        # Copie superficielle : les sqlite3.Row sont immuables, la liste est neuve
        return list(result) if isinstance(result, list) else result

    # ──────────────────────────────────────────
    #  SCHEMA
    # ──────────────────────────────────────────
    def _init_schema(self):
        self.con.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                is_default INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS months (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                year  INTEGER NOT NULL,
                month INTEGER NOT NULL,
                UNIQUE(year, month)
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                month_id    INTEGER NOT NULL REFERENCES months(id),
                category_id INTEGER NOT NULL REFERENCES categories(id),
                amount      REAL    NOT NULL,
                label       TEXT    DEFAULT '',
                payee       TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS revenues (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                month_id INTEGER NOT NULL REFERENCES months(id),
                source   TEXT    NOT NULL,
                amount   REAL    NOT NULL,
                label    TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS savings (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                month_id INTEGER NOT NULL REFERENCES months(id),
                account  TEXT    DEFAULT '',
                amount   REAL    NOT NULL,
                label    TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS assets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                year         INTEGER NOT NULL,
                month        INTEGER NOT NULL,
                asset_type   TEXT    NOT NULL,
                asset_name   TEXT    NOT NULL,
                value        REAL    NOT NULL,
                cost_basis   REAL    DEFAULT 0,
                notes        TEXT    DEFAULT '',
                UNIQUE(year, month, asset_type, asset_name)
            );
            CREATE TABLE IF NOT EXISTS asset_transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_name  TEXT    NOT NULL,
                asset_type  TEXT    NOT NULL,
                year        INTEGER NOT NULL,
                month       INTEGER NOT NULL,
                trans_type  TEXT    NOT NULL,
                quantity    REAL    NOT NULL DEFAULT 0,
                unit_price  REAL    NOT NULL DEFAULT 0,
                fees        REAL    NOT NULL DEFAULT 0,
                notes       TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS budgets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                year        INTEGER NOT NULL,
                month       INTEGER NOT NULL,
                category    TEXT NOT NULL,
                amount      REAL NOT NULL DEFAULT 0,
                UNIQUE(year, month, category)
            );
            CREATE TABLE IF NOT EXISTS savings_goals (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                target_amount  REAL NOT NULL,
                target_date    TEXT NOT NULL,
                current_amount REAL DEFAULT 0,
                notes          TEXT DEFAULT '',
                created_at     TEXT DEFAULT (date('now'))
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS recurring_transactions (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                label              TEXT    NOT NULL DEFAULT '',
                amount             REAL    NOT NULL DEFAULT 0,
                type               TEXT    NOT NULL DEFAULT 'expense',
                category_id        INTEGER REFERENCES categories(id),
                source             TEXT    DEFAULT '',
                payee              TEXT    DEFAULT '',
                active             INTEGER DEFAULT 1,
                last_applied_year  INTEGER DEFAULT 0,
                last_applied_month INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS liabilities (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                year             INTEGER NOT NULL,
                month            INTEGER NOT NULL,
                liability_type   TEXT    NOT NULL DEFAULT 'autre',
                liability_name   TEXT    NOT NULL,
                remaining_capital REAL   NOT NULL DEFAULT 0,
                monthly_payment  REAL    NOT NULL DEFAULT 0,
                end_date         TEXT    DEFAULT '',
                notes            TEXT    DEFAULT '',
                UNIQUE(year, month, liability_name)
            );

            -- Index simples
            CREATE INDEX IF NOT EXISTS idx_expenses_month       ON expenses(month_id);
            CREATE INDEX IF NOT EXISTS idx_expenses_cat         ON expenses(category_id);
            CREATE INDEX IF NOT EXISTS idx_expenses_payee       ON expenses(payee);
            CREATE INDEX IF NOT EXISTS idx_revenues_month       ON revenues(month_id);
            CREATE INDEX IF NOT EXISTS idx_savings_month        ON savings(month_id);
            CREATE INDEX IF NOT EXISTS idx_assets_period        ON assets(year, month);
            CREATE INDEX IF NOT EXISTS idx_assets_name_type     ON assets(asset_name, asset_type);
            CREATE INDEX IF NOT EXISTS idx_asset_tx_period      ON asset_transactions(year, month);
            CREATE INDEX IF NOT EXISTS idx_asset_tx_name        ON asset_transactions(asset_name);
            CREATE INDEX IF NOT EXISTS idx_budgets_period       ON budgets(year, month);
            -- Index composites (couvrent les filtres les plus fréquents en un seul scan)
            CREATE INDEX IF NOT EXISTS idx_expenses_month_cat   ON expenses(month_id, category_id);
            CREATE INDEX IF NOT EXISTS idx_expenses_month_payee ON expenses(month_id, payee);
            CREATE INDEX IF NOT EXISTS idx_assets_type_period   ON assets(asset_type, year, month);
        """)
        self.con.commit()

    def _migrate(self):
        """Migrations non-destructives — ajout de colonnes."""
        migrations = [
            "ALTER TABLE expenses ADD COLUMN payee TEXT DEFAULT ''",
            "ALTER TABLE assets   ADD COLUMN cost_basis REAL DEFAULT 0",
            # Flag de réinvestissement sur les ventes :
            # 0 = cash en attente (compté dans le patrimoine)
            # 1 = cash réinvesti (sorti du compteur "Cash en attente")
            "ALTER TABLE asset_transactions ADD COLUMN reinvested INTEGER DEFAULT 0",
            # Optionnel : référence vers l'actif dans lequel le cash a été réinvesti
            "ALTER TABLE asset_transactions ADD COLUMN reinvested_into TEXT DEFAULT ''",
            # Clôture de mois : 0 = ouvert, 1 = clôturé (saisie verrouillée)
            "ALTER TABLE months ADD COLUMN closed INTEGER DEFAULT 0",
            # Nom de l'actif Patrimoine (type 'compte') auto-synchronisé avec
            # cette épargne, si une correspondance a été trouvée à la saisie.
            "ALTER TABLE savings ADD COLUMN linked_asset_name TEXT DEFAULT ''",
        ]
        for stmt in migrations:
            try:
                self.con.execute(stmt)
                self.con.commit()
            except sqlite3.OperationalError:
                # Colonne déjà existante — comportement normal, pas de log
                pass
            except Exception:
                log.warning("Migration inattendue : %s", stmt, exc_info=True)
        # Normaliser toutes les enseignes existantes en MAJUSCULES
        self.con.execute(
            "UPDATE expenses SET payee = UPPER(TRIM(payee))"
            " WHERE payee IS NOT NULL AND payee != ''"
        )
        # Normaliser toutes les catégories existantes en MAJUSCULES
        self.con.execute(
            "UPDATE categories SET name = UPPER(TRIM(name))"
            " WHERE name IS NOT NULL AND name != ''"
        )
        self.con.commit()

    def _seed_categories(self):
        if self.con.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            for name in DEFAULT_CATEGORIES:
                self.con.execute(
                    "INSERT OR IGNORE INTO categories(name, is_default) VALUES(?, 1)", (name,)
                )
            self.con.commit()

    def _load_seed_sql_if_empty(self):
        """
        Si la base ne contient ni revenus ni dépenses, charge automatiquement
        data/seed_data.sql s'il existe (données pré-importées depuis Notion).
        """
        has_data = (
            self.con.execute("SELECT COUNT(*) FROM revenues").fetchone()[0] > 0
            or self.con.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] > 0
        )
        if has_data:
            return  # données déjà présentes, rien à faire

        seed_path = os.path.join(os.path.dirname(self.db_path), "seed_data.sql")
        if not os.path.exists(seed_path):
            return  # pas de fichier seed, on laisse vide

        with open(seed_path, "r", encoding="utf-8") as f:
            sql = f.read()

        # Exécuter chaque INSERT séparément pour éviter les erreurs partielles
        for stmt in sql.splitlines():
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                try:
                    self.con.execute(stmt)
                except sqlite3.IntegrityError as e:
                    log.debug("Seed SQL — contrainte ignorée (doublon probable) : %s", e)
                except Exception as e:
                    log.warning("Seed SQL — erreur inattendue sur : %.80s | %s", stmt, e)
        self.con.commit()

    # ──────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────
    def month_id(self, year: int, month: int, create: bool = True) -> int | None:
        row = self.con.execute(
            "SELECT id FROM months WHERE year=? AND month=?", (year, month)
        ).fetchone()
        if row:
            return row["id"]
        if create:
            cur = self.con.execute(
                "INSERT INTO months(year, month) VALUES(?, ?)", (year, month)
            )
            self.con.commit()
            return cur.lastrowid
        return None

    def get_last_month_with_data(self) -> tuple[int, int] | None:
        """Retourne (year, month) du dernier mois qui a des revenus ou dépenses."""
        row = self.con.execute("""
            SELECT m.year, m.month FROM months m
            WHERE EXISTS (SELECT 1 FROM revenues WHERE month_id = m.id)
               OR EXISTS (SELECT 1 FROM expenses WHERE month_id = m.id)
            ORDER BY m.year DESC, m.month DESC
            LIMIT 1
        """).fetchone()
        if row:
            return row["year"], row["month"]
        return None

    # ──────────────────────────────────────────
    #  CATEGORIES
    # ──────────────────────────────────────────
    def get_categories(self) -> list:
        return self._q("cats", lambda: self.con.execute(
            "SELECT * FROM categories ORDER BY name"
        ).fetchall())

    def add_category(self, name: str):
        name = name.strip().upper() if name else ""
        if not name:
            return
        self.con.execute(
            "INSERT OR IGNORE INTO categories(name, is_default) VALUES(?, 0)", (name,)
        )
        self.con.commit()
        self._invalidate()

    def delete_category(self, cat_id: int):
        self.con.execute(
            "DELETE FROM categories WHERE id=? AND is_default=0", (cat_id,)
        )
        self.con.commit()
        self._invalidate()

    def reset_categories(self):
        """Supprime les catégories custom et réinsère les défauts."""
        self.con.execute("DELETE FROM categories WHERE is_default=0")
        for name in DEFAULT_CATEGORIES:
            self.con.execute(
                "INSERT OR IGNORE INTO categories(name, is_default) VALUES(?, 1)", (name,)
            )
        self.con.commit()
        self._invalidate()

    def setup_categories(self, names: list):
        """
        Remplace toutes les catégories par la sélection de l'onboarding.
        Appelé une seule fois à la création du compte.
        names : liste de noms (str) choisis par l'utilisateur.
        """
        self.con.execute("DELETE FROM categories")
        for name in names:
            name = name.strip().upper()
            if name:
                is_def = 1 if name in DEFAULT_CATEGORIES else 0
                self.con.execute(
                    "INSERT OR IGNORE INTO categories(name, is_default) VALUES(?, ?)",
                    (name, is_def),
                )
        self.con.commit()
        self._invalidate()

    # ──────────────────────────────────────────
    #  EXPENSES
    # ──────────────────────────────────────────
    def add_expense(self, year, month, cat_id, amount, label="", payee=""):
        if amount is None or float(amount) <= 0:
            raise ValueError(f"Montant dépense invalide : {amount!r} (doit être > 0)")
        mid    = self.month_id(year, month)
        payee  = payee.strip().upper() if payee else ""
        self.con.execute(
            "INSERT INTO expenses(month_id, category_id, amount, label, payee) VALUES(?,?,?,?,?)",
            (mid, cat_id, float(amount), label, payee),
        )
        self.con.commit()
        self._invalidate()

    def update_expense(self, exp_id, cat_id, amount, label, payee):
        payee = payee.strip().upper() if payee else ""
        self.con.execute(
            "UPDATE expenses SET category_id=?, amount=?, label=?, payee=? WHERE id=?",
            (cat_id, amount, label, payee, exp_id),
        )
        self.con.commit()
        self._invalidate()

    def delete_expense(self, exp_id: int):
        self.con.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
        self.con.commit()
        self._invalidate()

    def get_expenses(self, year, month, cat_filter=None, payee_filter=None) -> list:
        mid = self.month_id(year, month, create=False)
        if not mid:
            return []
        q = """
            SELECT e.id, c.name AS cat, c.id AS cat_id,
                   e.amount, e.label, e.payee
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.month_id = ?
        """
        params = [mid]
        if cat_filter and cat_filter not in ("Toutes", FILTER_ALL_CATS):
            q += " AND c.name = ?"
            params.append(cat_filter)
        if payee_filter and payee_filter not in ("Tous", FILTER_ALL_PAYEES):
            q += " AND e.payee = ?"
            params.append(payee_filter)
        q += " ORDER BY c.name, e.payee, e.amount DESC"
        return self.con.execute(q, params).fetchall()

    def get_expenses_by_category(self, year, month, payee_filter=None) -> list:
        ck = f"ebc_{year}_{month}_{payee_filter}"
        if ck in self._cache:
            return self._cache[ck]
        mid = self.month_id(year, month, create=False)
        if not mid:
            return []
        q = """
            SELECT c.name, SUM(e.amount) AS total
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.month_id = ?
        """
        params = [mid]
        if payee_filter and payee_filter not in ("Tous", FILTER_ALL_PAYEES):
            q += " AND e.payee = ?"
            params.append(payee_filter)
        q += " GROUP BY c.id ORDER BY total DESC"
        result = self.con.execute(q, params).fetchall()
        self._cache[ck] = result
        return result

    def get_expenses_by_category_range(self, months: list[tuple[int, int]]) -> list:
        """
        Retourne le total des dépenses par catégorie sur une liste de (year, month).
        1 seule requête SQL au lieu de N — supprime le problème N+1 de build_financial_summary.
        """
        if not months:
            return []
        ck = f"ebc_range_{'_'.join(f'{y}{m}' for y, m in months)}"
        with self._cache_lock:
            if ck in self._cache:
                return self._cache[ck]
        placeholders = ",".join("(?,?)" for _ in months)
        params = [val for pair in months for val in pair]
        q = f"""
            SELECT c.name, SUM(e.amount) AS total
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            JOIN months mo ON e.month_id = mo.id
            WHERE (mo.year, mo.month) IN ({placeholders})
            GROUP BY c.id ORDER BY total DESC
        """
        result = [dict(r) for r in self.con.execute(q, params).fetchall()]
        with self._cache_lock:
            self._cache[ck] = result
        return result

    def get_expenses_by_category_range_per_month(self, months: list[tuple[int, int]]) -> list:
        """
        Comme get_expenses_by_category_range, mais groupé PAR MOIS ET catégorie
        (1 seule requête SQL) — pour les séries temporelles par catégorie
        (analyses.py), qui bouclaient auparavant sur get_expenses_by_category()
        une ou deux fois par mois (N+1).
        """
        if not months:
            return []
        ck = f"ebc_range_pm_{'_'.join(f'{y}{m}' for y, m in months)}"
        with self._cache_lock:
            if ck in self._cache:
                return self._cache[ck]
        placeholders = ",".join("(?,?)" for _ in months)
        params = [val for pair in months for val in pair]
        q = f"""
            SELECT mo.year, mo.month, c.name, SUM(e.amount) AS total
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            JOIN months mo ON e.month_id = mo.id
            WHERE (mo.year, mo.month) IN ({placeholders})
            GROUP BY mo.year, mo.month, c.id
            ORDER BY mo.year, mo.month
        """
        result = [dict(r) for r in self.con.execute(q, params).fetchall()]
        with self._cache_lock:
            self._cache[ck] = result
        return result

    def get_expenses_by_year(self, year: int) -> list:
        """
        Retourne TOUTES les dépenses de l'année avec cat + mois.
        1 seule requête SQL — élimine le N+1 de utils_taxes.py.
        """
        ck = f"eby_{year}"
        with self._cache_lock:
            if ck in self._cache:
                return list(self._cache[ck])
        result = self.con.execute("""
            SELECT e.id, c.name AS cat, c.id AS cat_id,
                   e.amount, e.label, e.payee,
                   mo.month AS month, mo.year AS year
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            JOIN months mo ON e.month_id = mo.id
            WHERE mo.year = ?
            ORDER BY mo.month, c.name
        """, (year,)).fetchall()
        with self._cache_lock:
            self._cache[ck] = result
        return list(result)

    def get_expenses_by_payee(self, year, month, cat_filter=None) -> list:
        ck = f"ebp_{year}_{month}_{cat_filter}"
        if ck in self._cache:
            return self._cache[ck]
        mid = self.month_id(year, month, create=False)
        if not mid:
            return []
        q = """
            SELECT e.payee, SUM(e.amount) AS total
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.month_id = ? AND e.payee != ''
        """
        params = [mid]
        if cat_filter and cat_filter not in ("Toutes", FILTER_ALL_CATS):
            q += " AND c.name = ?"
            params.append(cat_filter)
        q += " GROUP BY e.payee ORDER BY total DESC LIMIT 20"
        result = self.con.execute(q, params).fetchall()
        self._cache[ck] = result
        return result

    def get_payees(self, year=None, month=None) -> list[str]:
        if year and month:
            mid = self.month_id(year, month, create=False)
            if not mid:
                return []
            rows = self.con.execute(
                "SELECT DISTINCT payee FROM expenses WHERE month_id=? AND payee!='' ORDER BY payee",
                (mid,),
            ).fetchall()
        else:
            rows = self.con.execute(
                "SELECT DISTINCT payee FROM expenses WHERE payee!='' ORDER BY payee"
            ).fetchall()
        return [r["payee"] for r in rows]

    # ──────────────────────────────────────────
    #  REVENUES
    # ──────────────────────────────────────────
    def add_revenue(self, year, month, source, amount, label=""):
        if amount is None or float(amount) <= 0:
            raise ValueError(f"Montant revenu invalide : {amount!r} (doit être > 0)")
        mid = self.month_id(year, month)
        self.con.execute(
            "INSERT INTO revenues(month_id, source, amount, label) VALUES(?,?,?,?)",
            (mid, source, float(amount), label),
        )
        self.con.commit()
        self._invalidate()

    def update_revenue(self, rev_id, source, amount, label):
        self.con.execute(
            "UPDATE revenues SET source=?, amount=?, label=? WHERE id=?",
            (source, amount, label, rev_id),
        )
        self.con.commit()
        self._invalidate()

    def delete_revenue(self, rev_id: int):
        self.con.execute("DELETE FROM revenues WHERE id=?", (rev_id,))
        self.con.commit()
        self._invalidate()

    def get_revenues(self, year, month) -> list:
        mid = self.month_id(year, month, create=False)
        if not mid:
            return []
        return self.con.execute(
            "SELECT * FROM revenues WHERE month_id=? ORDER BY source", (mid,)
        ).fetchall()

    # ──────────────────────────────────────────
    #  SAVINGS
    # ──────────────────────────────────────────
    @staticmethod
    def _normalize_account_name(name: str) -> str:
        return "".join(ch for ch in (name or "").lower() if ch.isalnum())

    # Longueur minimale du nom normalisé pour tenter une correspondance —
    # évite qu'un nom de compte trop court/générique ("CB", "A") matche
    # accidentellement un actif sans rapport.
    _MIN_MATCH_LEN = 3

    def _match_compte_asset(self, account_name: str, assets_current: list = None):
        """
        Cherche un actif Patrimoine de type 'compte' dont le nom correspond
        (partiellement, insensible casse/ponctuation) au compte saisi en
        épargne — ex. "bourso" ou "boursobank" correspondent à "Bourso+".
        Ne renvoie une correspondance que si elle est UNIQUE : en cas
        d'ambiguïté (0 ou plusieurs candidats), on ne synchronise pas,
        pour éviter d'ajuster le mauvais compte silencieusement.

        assets_current : liste optionnelle déjà chargée (évite de refaire
        get_assets_current() si l'appelant l'a déjà en main).
        """
        norm_input = self._normalize_account_name(account_name)
        if len(norm_input) < self._MIN_MATCH_LEN:
            return None
        match = None
        for a in (assets_current if assets_current is not None else self.get_assets_current()):
            if a["asset_type"] != "compte":
                continue
            norm_asset = self._normalize_account_name(a["asset_name"])
            if norm_asset and (norm_input in norm_asset or norm_asset in norm_input):
                if match is not None:
                    return None  # 2e candidat -> ambigu, on arrête tout de suite
                match = a
        return match

    def _apply_saving_to_asset(self, year, month, asset_name: str, delta: float,
                               asset: dict = None):
        """
        Ajuste le solde ET le total versé d'un compte Patrimoine du montant
        delta (positif = dépôt, négatif = retrait/annulation) pour le mois
        de l'épargne concernée.

        asset : dict optionnel déjà résolu (évite de refaire get_assets_current()).

        Ne fait rien (silencieusement, sauf log) si l'actif n'est plus
        trouvable (ex. renommé depuis le lien d'origine) — mieux vaut ne pas
        toucher au patrimoine que d'ajuster le mauvais compte.

        Ne synchronise pas non plus si (year, month) est STRICTEMENT avant
        le dernier instantané connu de l'actif : appliquer le delta "valeur
        actuelle ± montant" sur un mois passé écraserait l'historique avec
        un chiffre qui n'a jamais existé à cette date.
        """
        current = asset or next(
            (a for a in self.get_assets_current()
             if a["asset_type"] == "compte" and a["asset_name"] == asset_name),
            None,
        )
        if not current:
            log.warning(
                "Épargne liée à un compte introuvable (renommé/supprimé ?) : %s — "
                "ajustement ignoré.", asset_name,
            )
            return
        if (year, month) < (current["year"], current["month"]):
            log.info(
                "Épargne pour %s/%s antérieure au dernier instantané connu de %s "
                "(%s/%s) — synchronisation ignorée pour ne pas corrompre l'historique.",
                year, month, asset_name, current["year"], current["month"],
            )
            return
        new_value = max(0.0, (current["value"] or 0.0) + delta)
        new_cost  = max(0.0, (current["cost_basis"] or 0.0) + delta)
        self.upsert_asset(year, month, "compte", asset_name,
                          new_value, new_cost, current["notes"] or "")

    def add_saving(self, year, month, account, amount, label=""):
        if amount is None or float(amount) <= 0:
            raise ValueError(f"Montant épargne invalide : {amount!r} (doit être > 0)")
        amount = float(amount)
        mid = self.month_id(year, month)
        assets_current = self.get_assets_current()
        matched = self._match_compte_asset(account, assets_current)
        linked_name = matched["asset_name"] if matched else ""
        self.con.execute(
            "INSERT INTO savings(month_id, account, amount, label, linked_asset_name) "
            "VALUES(?,?,?,?,?)",
            (mid, account, amount, label, linked_name),
        )
        self.con.commit()
        if matched:
            self._apply_saving_to_asset(year, month, matched["asset_name"], amount, asset=matched)
        self._invalidate()
        return linked_name or None

    def update_saving(self, sav_id, account, amount, label):
        if amount is None or float(amount) <= 0:
            raise ValueError(f"Montant épargne invalide : {amount!r} (doit être > 0)")
        amount = float(amount)
        old = self.con.execute(
            "SELECT s.account, s.amount, s.linked_asset_name, m.year, m.month "
            "FROM savings s JOIN months m ON s.month_id = m.id WHERE s.id=?",
            (sav_id,),
        ).fetchone()

        # Rien à faire si ni le compte ni le montant n'ont changé (évite deux
        # écritures Patrimoine superflues pour une simple correction de libellé).
        if old and old["account"] == account and old["amount"] == amount:
            self.con.execute(
                "UPDATE savings SET label=? WHERE id=?", (label, sav_id))
            self.con.commit()
            self._invalidate()
            return old["linked_asset_name"] or None

        assets_current = self.get_assets_current()
        if old and old["linked_asset_name"]:
            self._apply_saving_to_asset(
                old["year"], old["month"], old["linked_asset_name"], -old["amount"],
            )
            assets_current = self.get_assets_current()  # la valeur vient de changer

        matched = self._match_compte_asset(account, assets_current)
        linked_name = matched["asset_name"] if matched else ""
        self.con.execute(
            "UPDATE savings SET account=?, amount=?, label=?, linked_asset_name=? WHERE id=?",
            (account, amount, label, linked_name, sav_id),
        )
        self.con.commit()
        if matched and old:
            self._apply_saving_to_asset(old["year"], old["month"], matched["asset_name"], amount)
        self._invalidate()
        return linked_name or None

    def delete_saving(self, sav_id: int):
        old = self.con.execute(
            "SELECT s.amount, s.linked_asset_name, m.year, m.month "
            "FROM savings s JOIN months m ON s.month_id = m.id WHERE s.id=?",
            (sav_id,),
        ).fetchone()
        self.con.execute("DELETE FROM savings WHERE id=?", (sav_id,))
        self.con.commit()
        if old and old["linked_asset_name"]:
            self._apply_saving_to_asset(
                old["year"], old["month"], old["linked_asset_name"], -old["amount"])
        self._invalidate()

    def get_savings(self, year, month) -> list:
        mid = self.month_id(year, month, create=False)
        if not mid:
            return []
        return self.con.execute(
            "SELECT * FROM savings WHERE month_id=? ORDER BY account", (mid,)
        ).fetchall()

    # ──────────────────────────────────────────
    #  ASSETS / PATRIMOINE
    # ──────────────────────────────────────────
    def upsert_asset(self, year, month, asset_type, name, value, cost_basis=0.0, notes=""):
        self.con.execute(
            """
            INSERT INTO assets(year, month, asset_type, asset_name, value, cost_basis, notes)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(year, month, asset_type, asset_name)
            DO UPDATE SET value=excluded.value, cost_basis=excluded.cost_basis, notes=excluded.notes
            """,
            (year, month, asset_type, name, value, cost_basis, notes),
        )
        self.con.commit()
        self._invalidate()

    def update_asset(self, asset_id: int, asset_type: str, name: str,
                     value: float, cost_basis: float = 0.0, notes: str = ""):
        """Mise à jour d'un actif existant par son id (évite les doublons au renommage)."""
        self.con.execute(
            "UPDATE assets SET asset_type=?, asset_name=?, value=?, cost_basis=?, notes=? WHERE id=?",
            (asset_type, name, value, cost_basis, notes, asset_id),
        )
        self.con.commit()
        self._invalidate()

    def update_asset_value(self, asset_id: int, value: float):
        """
        Enregistre une nouvelle valeur pour le mois courant (préserve l'historique).
        Si l'actif a déjà un enregistrement ce mois-ci, le met à jour ; sinon crée
        un nouveau record pour ce mois, ce qui alimente le graphique d'évolution.
        """
        import datetime
        today = datetime.date.today()
        y, m  = today.year, today.month
        asset = self.con.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        if not asset:
            return
        self.con.execute(
            """
            INSERT INTO assets (year, month, asset_type, asset_name, value, cost_basis, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(year, month, asset_type, asset_name)
            DO UPDATE SET value=excluded.value
            """,
            (y, m, asset["asset_type"], asset["asset_name"],
             value, asset["cost_basis"], asset["notes"]),
        )
        self.con.commit()
        self._invalidate()

    def delete_asset(self, asset_id: int):
        self.con.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        self.con.commit()
        self._invalidate()

    def get_assets(self, year, month) -> list:
        return self.con.execute(
            "SELECT * FROM assets WHERE year=? AND month=? ORDER BY asset_type, asset_name",
            (year, month),
        ).fetchall()

    def get_asset_previous_value(self, year, month, asset_type, asset_name) -> float | None:
        """Retourne la valeur du mois précédent pour un actif donné (mis en cache
        via _q — évite de refaire la requête à chaque ligne rendue sur Patrimoine)."""
        ck = f"asset_prev_{year}_{month}_{asset_type}_{asset_name}"
        return self._q(ck, lambda: self._fetch_asset_previous_value(year, month, asset_type, asset_name))

    def _fetch_asset_previous_value(self, year, month, asset_type, asset_name) -> float | None:
        row = self.con.execute(
            """
            SELECT value FROM assets
            WHERE asset_name=? AND asset_type=?
              AND (year < ? OR (year=? AND month < ?))
            ORDER BY year DESC, month DESC
            LIMIT 1
            """,
            (asset_name, asset_type, year, year, month),
        ).fetchone()
        return row["value"] if row else None

    def get_asset_history_by_name(self, asset_name: str) -> list:
        """Historique complet d'un actif (pour le graphique d'évolution)."""
        return self.con.execute(
            """
            SELECT year, month, value, cost_basis
            FROM assets WHERE asset_name=?
            ORDER BY year, month
            """,
            (asset_name,),
        ).fetchall()

    # ──────────────────────────────────────────
    #  ASSET TRANSACTIONS
    # ──────────────────────────────────────────
    def add_asset_transaction(self, asset_name: str, asset_type: str,
                               year: int, month: int, trans_type: str,
                               quantity: float, unit_price: float,
                               fees: float = 0.0, notes: str = "") -> int:
        """Enregistre un achat ou une vente."""
        cur = self.con.execute(
            """INSERT INTO asset_transactions
               (asset_name, asset_type, year, month, trans_type, quantity, unit_price, fees, notes)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (asset_name, asset_type, year, month, trans_type,
             quantity, unit_price, fees, notes),
        )
        self.con.commit()
        self._invalidate()
        return cur.lastrowid

    def get_asset_transactions(self, asset_name: str) -> list:
        """Retourne toutes les transactions d'un actif, du plus ancien au plus récent."""
        return self.con.execute(
            "SELECT * FROM asset_transactions WHERE asset_name=? ORDER BY year, month, id",
            (asset_name,),
        ).fetchall()

    def delete_asset_transaction(self, trans_id: int):
        self.con.execute("DELETE FROM asset_transactions WHERE id=?", (trans_id,))
        self.con.commit()
        self._invalidate()

    def compute_asset_position(self, asset_name: str) -> dict:
        """
        Calcule la position actuelle par méthode CMUP (coût moyen pondéré).
        Retourne:
          qty          : quantité détenue actuellement
          avg_price    : prix de revient moyen unitaire
          total_cost   : valeur totale investie dans la position courante
          realized_pnl : plus-value réalisée sur les ventes passées
          total_fees   : somme de tous les frais
        """
        transactions = self.get_asset_transactions(asset_name)
        qty          = 0.0
        total_cost   = 0.0
        realized_pnl = 0.0
        total_fees   = 0.0

        for t in transactions:
            fees        = float(t["fees"] or 0)
            total_fees += fees

            if t["trans_type"] == "achat":
                cost        = float(t["quantity"]) * float(t["unit_price"]) + fees
                total_cost += cost
                qty        += float(t["quantity"])

            elif t["trans_type"] == "vente":
                if qty > 0:
                    avg_price    = total_cost / qty
                    sold_cost    = float(t["quantity"]) * avg_price
                    proceeds     = float(t["quantity"]) * float(t["unit_price"]) - fees
                    realized_pnl += proceeds - sold_cost
                    total_cost   -= sold_cost
                    qty          -= float(t["quantity"])
                    if qty < 1e-9:      # sécurité virgule flottante
                        qty        = 0.0
                        total_cost = 0.0

        avg_price = total_cost / qty if qty > 1e-9 else 0.0
        return {
            "qty":          qty,
            "avg_price":    avg_price,
            "total_cost":   max(total_cost, 0.0),
            "realized_pnl": realized_pnl,
            "total_fees":   total_fees,
        }

    # ──────────────────────────────────────────
    #  POSITION STATUS (détenu / partiel / vendu)
    # ──────────────────────────────────────────
    def get_position_status(self, asset_name: str) -> dict:
        """
        Calcule le statut d'une position à partir de ses transactions.
        Mis en cache via _q() : évite les appels dupliqués (vue d'ensemble +
        ligne détaillée de patrimoine.py, + get_closed_positions()).
        Retourne :
          status         : "detenu" (aucune vente) | "partiel" (qty>0 + ventes) | "vendu" (qty=0)
          qty            : quantité encore détenue
          realized_pnl   : plus-value réalisée totale
          sale_proceeds  : produit total des ventes (qty * prix_unit - frais), brut
          sale_qty       : quantité totale vendue (cumul)
          avg_sale_price : prix de vente moyen pondéré
          last_sale_ym   : (year, month) de la dernière vente, ou None
          has_sales      : bool — y a-t-il au moins une vente ?
          all_reinvested : bool — toutes les ventes sont-elles marquées réinvesties ?
          cash_pending   : produit des ventes NON réinvesties (cash en attente)
        """
        return self._q(f"pos_status_{asset_name}", lambda: self._compute_position_status(asset_name))

    def _compute_position_status(self, asset_name: str) -> dict:
        pos = self.compute_asset_position(asset_name)
        sales = self.con.execute(
            """
            SELECT id, year, month, quantity, unit_price, fees, reinvested
            FROM asset_transactions
            WHERE asset_name=? AND trans_type='vente'
            ORDER BY year, month, id
            """,
            (asset_name,),
        ).fetchall()

        sale_qty       = sum(float(s["quantity"]) for s in sales)
        sale_proceeds  = sum(float(s["quantity"]) * float(s["unit_price"]) - float(s["fees"] or 0)
                             for s in sales)
        avg_sale_price = (
            sum(float(s["quantity"]) * float(s["unit_price"]) for s in sales) / sale_qty
            if sale_qty > 0 else 0.0
        )
        cash_pending = sum(
            float(s["quantity"]) * float(s["unit_price"]) - float(s["fees"] or 0)
            for s in sales if not s["reinvested"]
        )
        all_reinvested = bool(sales) and all(s["reinvested"] for s in sales)
        last_sale_ym   = (sales[-1]["year"], sales[-1]["month"]) if sales else None

        if pos["qty"] <= 1e-9 and sales:
            status = "vendu"
        elif sales:
            status = "partiel"
        else:
            status = "detenu"

        return {
            "status":         status,
            "qty":            pos["qty"],
            "avg_price":      pos["avg_price"],
            "total_cost":     pos["total_cost"],
            "realized_pnl":   pos["realized_pnl"],
            "total_fees":     pos["total_fees"],
            "sale_qty":       sale_qty,
            "sale_proceeds":  sale_proceeds,
            "avg_sale_price": avg_sale_price,
            "last_sale_ym":   last_sale_ym,
            "has_sales":      bool(sales),
            "all_reinvested": all_reinvested,
            "cash_pending":   cash_pending,
        }

    def get_cash_pending_total(self) -> float:
        """
        Somme du cash issu des ventes non encore marquées comme réinvesties.
        Représente le 'cash en attente' dans le patrimoine.
        """
        row = self.con.execute(
            """
            SELECT COALESCE(SUM(quantity * unit_price - COALESCE(fees, 0)), 0) AS cash
            FROM asset_transactions
            WHERE trans_type='vente' AND (reinvested IS NULL OR reinvested = 0)
            """
        ).fetchone()
        return float(row["cash"] or 0.0)

    def get_closed_positions(self) -> list[dict]:
        """
        Retourne toutes les positions clôturées (qty=0) avec leur statut détaillé.
        Triées par date de dernière vente DESC (plus récentes en haut).
        """
        # Tous les actifs ayant au moins une transaction de vente
        rows = self.con.execute(
            """
            SELECT DISTINCT asset_name, asset_type
            FROM asset_transactions
            WHERE trans_type='vente'
            """
        ).fetchall()
        result = []
        for r in rows:
            st = self.get_position_status(r["asset_name"])
            if st["status"] == "vendu":
                result.append({
                    "asset_name": r["asset_name"],
                    "asset_type": r["asset_type"],
                    **st,
                })
        # Tri par date de dernière vente, plus récente d'abord
        result.sort(
            key=lambda x: (x["last_sale_ym"] or (0, 0)),
            reverse=True,
        )
        return result

    def mark_sales_reinvested(self, asset_name: str, reinvested: bool = True,
                               reinvested_into: str = ""):
        """
        Marque toutes les ventes d'un actif comme réinvesties (ou inverse).
        Utilisé sur les positions clôturées pour sortir le cash du compteur.
        """
        self.con.execute(
            """
            UPDATE asset_transactions
            SET reinvested = ?, reinvested_into = ?
            WHERE asset_name = ? AND trans_type = 'vente'
            """,
            (1 if reinvested else 0, reinvested_into if reinvested else "", asset_name),
        )
        self.con.commit()
        self._invalidate()

    def get_assets_current(self) -> list:
        """
        Retourne la valeur la plus récente de chaque actif (toutes périodes confondues).
        C'est la vue principale du patrimoine : pas de filtre par mois.
        """
        return self.con.execute(
            """
            SELECT a.*
            FROM assets a
            INNER JOIN (
                SELECT asset_type, asset_name, MAX(year * 100 + month) AS latest
                FROM assets
                GROUP BY asset_type, asset_name
            ) m ON a.asset_type = m.asset_type
               AND a.asset_name = m.asset_name
               AND (a.year * 100 + a.month) = m.latest
            ORDER BY a.asset_type, a.asset_name
            """
        ).fetchall()

    def get_assets_by_type_current(self) -> list:
        """Répartition par type d'actif sur les valeurs actuelles (dernières connues)."""
        rows = self.get_assets_current()
        totals: dict = {}
        for r in rows:
            t = r["asset_type"]
            if t not in totals:
                totals[t] = {"asset_type": t, "total": 0.0, "total_basis": 0.0}
            totals[t]["total"]       += r["value"]
            totals[t]["total_basis"] += r["cost_basis"] or 0.0
        return sorted(totals.values(), key=lambda x: -x["total"])

    def get_asset_names(self) -> list[str]:
        rows = self.con.execute(
            "SELECT DISTINCT asset_name FROM assets ORDER BY asset_name"
        ).fetchall()
        return [r["asset_name"] for r in rows]

    def get_assets_by_type(self, year, month) -> list:
        return self._q(f"abt_{year}_{month}", lambda: self.con.execute(
            """
            SELECT asset_type, SUM(value) AS total, SUM(cost_basis) AS total_basis
            FROM assets WHERE year=? AND month=?
            GROUP BY asset_type ORDER BY total DESC
            """,
            (year, month),
        ).fetchall())

    def get_patrimoine_history(self) -> list:
        """
        Historique du patrimoine total par mois.

        Pour chaque mois présent dans la base, calcule la SOMME des
        dernières valeurs connues de CHAQUE actif jusqu'à ce mois.
        Cela évite les totaux incomplets quand seulement certains actifs
        ont été mis à jour ce mois-là.
        """
        def _compute():
            # 1. Tous les mois distincts triés
            months = self.con.execute(
                "SELECT DISTINCT year, month FROM assets ORDER BY year, month"
            ).fetchall()
            # 2. Tous les actifs distincts
            asset_keys = self.con.execute(
                "SELECT DISTINCT asset_type, asset_name FROM assets"
            ).fetchall()

            if not months or not asset_keys:
                return []

            result = []
            for m in months:
                y, mo = m["year"], m["month"]
                total_value = 0.0
                total_basis = 0.0
                for ak in asset_keys:
                    row = self.con.execute(
                        """
                        SELECT value, cost_basis FROM assets
                        WHERE asset_type=? AND asset_name=?
                          AND (year < ? OR (year=? AND month <= ?))
                        ORDER BY year DESC, month DESC
                        LIMIT 1
                        """,
                        (ak["asset_type"], ak["asset_name"], y, y, mo),
                    ).fetchone()
                    if row:
                        total_value += row["value"] or 0.0
                        total_basis += row["cost_basis"] or 0.0
                result.append({
                    "year":        y,
                    "month":       mo,
                    "total_value": total_value,
                    "total_basis": total_basis,
                })
            return result

        return self._q("pat_hist", _compute)

    def get_patrimoine_history_by_type(self, asset_type: str) -> list:
        """
        Historique mensuel pour un type d'actif donné.
        Pour chaque mois, retourne le total de ce type + le détail par actif.
        """
        def _compute():
            months = self.con.execute(
                "SELECT DISTINCT year, month FROM assets ORDER BY year, month"
            ).fetchall()
            asset_keys = self.con.execute(
                "SELECT DISTINCT asset_name FROM assets WHERE asset_type=?",
                (asset_type,),
            ).fetchall()

            if not months or not asset_keys:
                return []

            result = []
            for m in months:
                y, mo = m["year"], m["month"]
                total_value = 0.0
                per_asset   = {}
                for ak in asset_keys:
                    name = ak["asset_name"]
                    row  = self.con.execute(
                        """
                        SELECT value FROM assets
                        WHERE asset_type=? AND asset_name=?
                          AND (year < ? OR (year=? AND month <= ?))
                        ORDER BY year DESC, month DESC
                        LIMIT 1
                        """,
                        (asset_type, name, y, y, mo),
                    ).fetchone()
                    v = row["value"] if row else 0.0
                    total_value          += v
                    per_asset[name]       = v
                result.append({
                    "year":       y,
                    "month":      mo,
                    "total_value": total_value,
                    "per_asset":   per_asset,
                })
            return result

        return self._q(f"pat_hist_type_{asset_type}", _compute)

    def get_asset_history_all(self) -> dict:
        """
        Retourne l'historique complet de chaque actif (toutes entrées).
        dict: asset_name -> list of {year, month, value}
        """
        rows = self.con.execute(
            "SELECT asset_name, asset_type, year, month, value FROM assets "
            "ORDER BY asset_name, year, month"
        ).fetchall()
        result: dict = {}
        for r in rows:
            n = r["asset_name"]
            if n not in result:
                result[n] = {"asset_type": r["asset_type"], "entries": []}
            result[n]["entries"].append({
                "year": r["year"], "month": r["month"], "value": r["value"]
            })
        return result

    # ──────────────────────────────────────────
    #  SUMMARY
    # ──────────────────────────────────────────
    def monthly_summary(self, limit: int = 24) -> list:
        return self._q(f"sum_{limit}", lambda: self.con.execute(
            """
            SELECT m.year, m.month,
                COALESCE((SELECT SUM(amount) FROM revenues WHERE month_id=m.id), 0) AS rev,
                COALESCE((SELECT SUM(amount) FROM expenses WHERE month_id=m.id), 0) AS exp,
                COALESCE((SELECT SUM(amount) FROM savings  WHERE month_id=m.id), 0) AS sav
            FROM months m
            ORDER BY m.year DESC, m.month DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall())

    # ──────────────────────────────────────────
    #  EXPORT CSV
    # ──────────────────────────────────────────
    def export_csv(self, path: str):
        rows = self.monthly_summary(120)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Année", "Mois", "Revenus (€)", "Dépenses (€)", "Épargne (€)", "Bilan (€)"])
            for r in reversed(rows):
                w.writerow([
                    r["year"], MONTHS_FR[r["month"] - 1],
                    f"{r['rev']:.2f}", f"{r['exp']:.2f}",
                    f"{r['sav']:.2f}", f"{r['rev'] - r['exp']:.2f}",
                ])

    # ──────────────────────────────────────────
    #  IMPORT NOTION ZIP
    # ──────────────────────────────────────────
    def import_notion_zip(self, zip_path: str) -> tuple[int, int, int]:
        """
        Importe un export ZIP Notion (revenus, dépenses ou épargnes).
        Retourne (nb_revenus, nb_dépenses, nb_épargnes) importés.

        Restructuré en deux passes sous batch_mode() : les catégories sont
        toutes résolues en amont (au lieu d'un add_category()+get_categories()
        par ligne), ce qui évite une rafale de vidages de cache complets sur
        un import de N lignes ET rend la résolution de catégories inédites
        indépendante de l'ordre d'invalidation (plus robuste qu'avant, où une
        catégorie ajoutée en cours de boucle dépendait d'une invalidation
        immédiate pour être vue par les lignes suivantes).
        """
        rev_count = exp_count = sav_count = 0

        with self.batch_mode():
            parsed_rows: list[tuple[bool, bool, dict]] = []
            needed_cats: set[str] = set()

            for fname, content in self._iter_csv_from_zip(zip_path):
                reader     = csv.DictReader(content.splitlines())
                fieldnames = [k.strip() for k in (reader.fieldnames or [])]
                is_expense = "Category" in fieldnames or "à qui" in fieldnames
                is_saving  = "Compte" in fieldnames and not is_expense

                for raw_row in reader:
                    row = {k.strip(): (v or "").strip() for k, v in raw_row.items()}
                    parsed_rows.append((is_expense, is_saving, row))
                    if is_expense:
                        needed_cats.add(row.get("Category", "Autres").strip() or "Autres")

            for cat_name in needed_cats:
                self.add_category(cat_name)
            cats = {c["name"]: c["id"] for c in self.get_categories()}

            for is_expense, is_saving, row in parsed_rows:
                mois_raw = row.get("Mois", "")
                if not mois_raw:
                    continue
                year, month = parse_notion_month(mois_raw)
                if not year or not month:
                    continue
                amount = parse_amount(row.get("Montant", ""))
                if amount <= 0:
                    continue

                if is_expense:
                    cat_name = row.get("Category", "Autres").strip() or "Autres"
                    payee    = row.get("à qui", "").strip().upper()
                    label    = row.get("Nom", "").strip()
                    cat_id = cats.get(cat_name) or cats.get("Autres")
                    if cat_id:
                        self.add_expense(year, month, cat_id, amount, label, payee)
                        exp_count += 1
                elif is_saving:
                    account = row.get("Compte", "").strip()
                    label   = row.get("Nom", row.get("Notes", "")).strip()
                    self.add_saving(year, month, account, amount, label)
                    sav_count += 1
                else:
                    source = row.get("Nom", "Revenu").strip()
                    label  = row.get("Notes", "").strip()
                    self.add_revenue(year, month, source, amount, label)
                    rev_count += 1

        return rev_count, exp_count, sav_count

    def _iter_csv_from_zip(self, zip_path: str):
        """Itère sur les fichiers *_all.csv dans un ZIP (potentiellement imbriqué)."""
        with zipfile.ZipFile(zip_path) as oz:
            for name in oz.namelist():
                data = oz.read(name)
                if name.lower().endswith(".zip"):
                    with zipfile.ZipFile(io.BytesIO(data)) as iz:
                        for iname in iz.namelist():
                            if iname.lower().endswith("_all.csv"):
                                yield iname, iz.read(iname).decode("utf-8-sig")
                elif name.lower().endswith("_all.csv"):
                    yield name, data.decode("utf-8-sig")

    # ──────────────────────────────────────────
    #  BUDGETS
    # ──────────────────────────────────────────
    def set_budget(self, year: int, month: int, category: str, amount: float):
        """Insère ou met à jour un budget pour une catégorie un mois donné."""
        self.con.execute(
            """
            INSERT INTO budgets(year, month, category, amount)
            VALUES(?,?,?,?)
            ON CONFLICT(year, month, category)
            DO UPDATE SET amount=excluded.amount
            """,
            (year, month, category, amount),
        )
        self.con.commit()
        self._invalidate()

    def get_budgets(self, year: int, month: int) -> list:
        """Retourne tous les budgets d'un mois donné."""
        return self.con.execute(
            "SELECT * FROM budgets WHERE year=? AND month=? ORDER BY category",
            (year, month),
        ).fetchall()

    def get_category_budget_status(self, year: int, month: int, category_name: str):
        """Retourne (budget, actual) pour une catégorie, ou None si pas de budget."""
        row = self.con.execute(
            "SELECT amount FROM budgets WHERE year=? AND month=? AND category=?",
            (year, month, category_name)
        ).fetchone()
        if not row:
            return None
        mid = self.month_id(year, month, create=False)
        if not mid:
            return (row["amount"], 0.0)
        actual = self.con.execute(
            """SELECT COALESCE(SUM(e.amount),0) as total
               FROM expenses e JOIN categories c ON e.category_id=c.id
               WHERE e.month_id=? AND c.name=?""",
            (mid, category_name)
        ).fetchone()["total"]
        return (row["amount"], actual)

    def get_budget_vs_actual(self, year: int, month: int) -> list:
        """
        Retourne une liste de dicts comparant budget et réalisé par catégorie.
        Format: {category, budget, actual, diff, pct, has_budget, has_expenses}
        Triée par actual DESC.
        """
        mid = self.month_id(year, month, create=False)
        
        # 1. Récupérer les budgets
        budgets = {}
        for row in self.con.execute(
            "SELECT category, amount FROM budgets WHERE year=? AND month=?",
            (year, month),
        ).fetchall():
            budgets[row["category"]] = row["amount"]
        
        # 2. Récupérer les dépenses réelles
        actual_by_cat = {}
        if mid:
            for row in self.con.execute(
                """
                SELECT c.name, SUM(e.amount) AS total
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE e.month_id = ?
                GROUP BY c.id
                """,
                (mid,),
            ).fetchall():
                actual_by_cat[row["name"]] = row["total"]
        
        # 3. Construire la liste pour chaque catégorie avec budget OU dépenses
        all_cats = set(budgets.keys()) | set(actual_by_cat.keys())
        result = []
        
        for cat in all_cats:
            budget = budgets.get(cat, 0.0)
            actual = actual_by_cat.get(cat, 0.0)
            diff = budget - actual
            pct = (actual / budget * 100) if budget > 0 else 0
            
            result.append({
                "category": cat,
                "budget": budget,
                "actual": actual,
                "diff": diff,
                "pct": pct,
                "has_budget": budget > 0,
                "has_expenses": actual > 0,
            })
        
        # Trier par actual DESC
        result.sort(key=lambda x: -x["actual"])
        return result

    def copy_budgets_from_month(self, from_year: int, from_month: int,
                                 to_year: int, to_month: int):
        """Copie tous les budgets d'un mois source vers un mois cible."""
        source_budgets = self.get_budgets(from_year, from_month)
        for row in source_budgets:
            self.set_budget(to_year, to_month, row["category"], row["amount"])

    # ──────────────────────────────────────────
    #  SAVINGS GOALS
    # ──────────────────────────────────────────
    def add_savings_goal(self, name: str, target_amount: float,
                        target_date: str, current_amount: float = 0.0,
                        notes: str = "") -> int:
        """
        Ajoute un nouvel objectif d'épargne.
        Retourne l'ID du nouvel objectif.
        """
        cur = self.con.execute(
            """
            INSERT INTO savings_goals(name, target_amount, target_date, current_amount, notes)
            VALUES(?,?,?,?,?)
            """,
            (name, target_amount, target_date, current_amount, notes),
        )
        self.con.commit()
        self._invalidate()
        return cur.lastrowid

    def update_savings_goal(self, goal_id: int, name: str, target_amount: float,
                           target_date: str, current_amount: float, notes: str):
        """Met à jour un objectif d'épargne existant."""
        self.con.execute(
            """
            UPDATE savings_goals
            SET name=?, target_amount=?, target_date=?, current_amount=?, notes=?
            WHERE id=?
            """,
            (name, target_amount, target_date, current_amount, notes, goal_id),
        )
        self.con.commit()
        self._invalidate()

    def update_goal_progress(self, goal_id: int, current_amount: float):
        """Mise à jour rapide du montant actuel d'un objectif."""
        self.con.execute(
            "UPDATE savings_goals SET current_amount=? WHERE id=?",
            (current_amount, goal_id),
        )
        self.con.commit()
        self._invalidate()

    def delete_savings_goal(self, goal_id: int):
        """Supprime un objectif d'épargne."""
        self.con.execute("DELETE FROM savings_goals WHERE id=?", (goal_id,))
        self.con.commit()
        self._invalidate()

    def get_savings_goals(self) -> list:
        """Retourne tous les objectifs d'épargne, triés par date cible."""
        return self.con.execute(
            "SELECT * FROM savings_goals ORDER BY target_date ASC"
        ).fetchall()

    # ──────────────────────────────────────────
    #  APP SETTINGS
    # ──────────────────────────────────────────
    def get_setting(self, key: str, default: str = "") -> str:
        """Récupère un paramètre d'application."""
        row = self.con.execute(
            "SELECT value FROM app_settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        """Enregistre un paramètre d'application."""
        self.con.execute(
            """
            INSERT INTO app_settings(key, value)
            VALUES(?,?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        self.con.commit()
        # Ne pas invalider le cache IA quand c'est justement lui qu'on écrit,
        # sinon save_cached_result() efface sa propre valeur juste après l'avoir écrite.
        if not key.startswith("ai_cache_") and not key.startswith("ui_"):
            self._invalidate()
        else:
            with self._cache_lock:
                self._cache.clear()

    def get_all_payees(self) -> list:
        """Retourne tous les enseignes distincts triés par fréquence d'utilisation."""
        rows = self.con.execute(
            "SELECT payee FROM expenses "
            "WHERE payee IS NOT NULL AND payee != '' "
            "GROUP BY UPPER(payee) ORDER BY COUNT(*) DESC"
        ).fetchall()
        return [r["payee"] for r in rows]

    # ──────────────────────────────────────────
    #  TRANSACTIONS RÉCURRENTES
    # ──────────────────────────────────────────

    def get_recurring_transactions(self) -> list:
        """Retourne toutes les transactions récurrentes (actives + inactives)."""
        return self.con.execute(
            """
            SELECT r.id, r.label, r.amount, r.type,
                   r.category_id, c.name AS cat_name,
                   r.source, r.payee, r.active,
                   r.last_applied_year, r.last_applied_month
            FROM recurring_transactions r
            LEFT JOIN categories c ON r.category_id = c.id
            ORDER BY r.type, r.label
            """
        ).fetchall()

    def add_recurring(self, label: str, amount: float, rtype: str,
                      category_id: int | None, source: str = "",
                      payee: str = "") -> int:
        """
        Crée une transaction récurrente.
        rtype : 'expense' | 'revenue'
        """
        payee = payee.strip().upper() if payee else ""
        cur = self.con.execute(
            """
            INSERT INTO recurring_transactions
                (label, amount, type, category_id, source, payee, active)
            VALUES (?,?,?,?,?,?,1)
            """,
            (label, amount, rtype, category_id, source, payee),
        )
        self.con.commit()
        self._invalidate()
        return cur.lastrowid

    def update_recurring(self, rec_id: int, label: str, amount: float,
                         rtype: str, category_id: int | None,
                         source: str, payee: str, active: int):
        """Met à jour une transaction récurrente existante."""
        payee = payee.strip().upper() if payee else ""
        self.con.execute(
            """
            UPDATE recurring_transactions
            SET label=?, amount=?, type=?, category_id=?,
                source=?, payee=?, active=?
            WHERE id=?
            """,
            (label, amount, rtype, category_id, source, payee, active, rec_id),
        )
        self.con.commit()
        self._invalidate()

    def delete_recurring(self, rec_id: int):
        """Supprime une transaction récurrente."""
        self.con.execute(
            "DELETE FROM recurring_transactions WHERE id=?", (rec_id,)
        )
        self.con.commit()
        self._invalidate()

    # ──────────────────────────────────────────
    #  PASSIFS / DETTES
    # ──────────────────────────────────────────
    def get_liabilities_current(self) -> list:
        """Retourne le dernier snapshot de chaque passif (toutes périodes confondues)."""
        return self.con.execute("""
            SELECT l.*
            FROM liabilities l
            INNER JOIN (
                SELECT liability_name, MAX(year * 12 + month) AS maxym
                FROM liabilities
                GROUP BY liability_name
            ) latest ON l.liability_name = latest.liability_name
                     AND l.year * 12 + l.month = latest.maxym
            ORDER BY l.liability_type, l.liability_name
        """).fetchall()

    def get_liabilities(self, year: int, month: int) -> list:
        """Retourne les passifs pour un mois donné."""
        return self.con.execute(
            "SELECT * FROM liabilities WHERE year=? AND month=? ORDER BY liability_type, liability_name",
            (year, month)
        ).fetchall()

    def add_or_update_liability(self, year: int, month: int,
                                liability_type: str, liability_name: str,
                                remaining_capital: float, monthly_payment: float,
                                end_date: str = "", notes: str = "") -> int:
        """Insère ou met à jour un passif pour un mois donné."""
        cur = self.con.execute("""
            INSERT INTO liabilities
                (year, month, liability_type, liability_name,
                 remaining_capital, monthly_payment, end_date, notes)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(year, month, liability_name) DO UPDATE SET
                liability_type    = excluded.liability_type,
                remaining_capital = excluded.remaining_capital,
                monthly_payment   = excluded.monthly_payment,
                end_date          = excluded.end_date,
                notes             = excluded.notes
        """, (year, month, liability_type, liability_name,
              remaining_capital, monthly_payment, end_date, notes))
        self.con.commit()
        self._invalidate()
        return cur.lastrowid

    def update_liability_capital(self, liability_name: str, year: int, month: int,
                                  remaining_capital: float):
        """Met à jour uniquement le capital restant dû pour un passif au mois courant.
        Copie d'abord le dernier snapshot si le mois n'existe pas encore."""
        existing = self.con.execute(
            "SELECT * FROM liabilities WHERE liability_name=? AND year=? AND month=?",
            (liability_name, year, month)
        ).fetchone()
        if existing:
            self.con.execute(
                "UPDATE liabilities SET remaining_capital=? WHERE liability_name=? AND year=? AND month=?",
                (remaining_capital, liability_name, year, month)
            )
        else:
            # Copier le dernier snapshot et créer une nouvelle entrée pour ce mois
            last = self.con.execute("""
                SELECT * FROM liabilities WHERE liability_name=?
                ORDER BY year DESC, month DESC LIMIT 1
            """, (liability_name,)).fetchone()
            if last:
                self.con.execute("""
                    INSERT OR IGNORE INTO liabilities
                        (year, month, liability_type, liability_name,
                         remaining_capital, monthly_payment, end_date, notes)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (year, month, last["liability_type"], liability_name,
                      remaining_capital, last["monthly_payment"],
                      last["end_date"], last["notes"]))
        self.con.commit()
        self._invalidate()

    def delete_liability(self, liability_name: str):
        """Supprime tous les snapshots d'un passif (suppression définitive)."""
        self.con.execute(
            "DELETE FROM liabilities WHERE liability_name=?", (liability_name,)
        )
        self.con.commit()
        self._invalidate()

    def get_total_liabilities(self) -> float:
        """Somme du capital restant dû sur tous les passifs (snapshot courant)."""
        rows = self.get_liabilities_current()
        return sum(r["remaining_capital"] for r in rows)

    # ──────────────────────────────────────────
    #  CLÔTURE DE MOIS
    # ──────────────────────────────────────────
    def is_month_closed(self, year: int, month: int) -> bool:
        """Retourne True si le mois (year, month) a été clôturé."""
        row = self.con.execute(
            "SELECT closed FROM months WHERE year=? AND month=?", (year, month)
        ).fetchone()
        return bool(row and row["closed"])

    def close_month(self, year: int, month: int):
        """
        Clôture le mois : crée l'entrée si elle n'existe pas,
        puis positionne closed=1.
        """
        self.con.execute(
            "INSERT OR IGNORE INTO months(year, month, closed) VALUES(?,?,0)",
            (year, month),
        )
        self.con.execute(
            "UPDATE months SET closed=1 WHERE year=? AND month=?",
            (year, month),
        )
        self.con.commit()
        self._invalidate()

    def reopen_month(self, year: int, month: int):
        """Ré-ouvre un mois clôturé (utile depuis les Paramètres ou en cas d'erreur)."""
        self.con.execute(
            "UPDATE months SET closed=0 WHERE year=? AND month=?",
            (year, month),
        )
        self.con.commit()
        self._invalidate()

    def get_pending_recurring(self, year: int, month: int) -> list:
        """
        Retourne les transactions récurrentes actives qui n'ont pas encore
        été appliquées pour le mois (year, month) donné.
        """
        return self.con.execute(
            """
            SELECT r.id, r.label, r.amount, r.type,
                   r.category_id, c.name AS cat_name,
                   r.source, r.payee,
                   r.last_applied_year, r.last_applied_month
            FROM recurring_transactions r
            LEFT JOIN categories c ON r.category_id = c.id
            WHERE r.active = 1
              AND NOT (r.last_applied_year = ? AND r.last_applied_month = ?)
            ORDER BY r.type, r.label
            """,
            (year, month),
        ).fetchall()

    def apply_recurring(self, rec_id: int, year: int, month: int,
                        amount: float):
        """
        Applique une transaction récurrente pour le mois donné :
        - Crée la dépense ou le revenu correspondant
        - Met à jour last_applied_year / last_applied_month
        """
        row = self.con.execute(
            "SELECT * FROM recurring_transactions WHERE id=?", (rec_id,)
        ).fetchone()
        if not row:
            return

        if row["type"] == "expense" and row["category_id"]:
            self.add_expense(
                year, month, row["category_id"], amount,
                row["label"], row["payee"],
            )
        elif row["type"] == "revenue":
            self.add_revenue(
                year, month,
                row["source"] or row["label"],
                amount,
                row["label"],
            )

        # Marquer comme appliquée ce mois-ci
        self.con.execute(
            """
            UPDATE recurring_transactions
            SET last_applied_year=?, last_applied_month=?
            WHERE id=?
            """,
            (year, month, rec_id),
        )
        self.con.commit()
        self._invalidate()
