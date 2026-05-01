-- ============================================================
-- Finance Tracker — Schéma Supabase PostgreSQL
-- À exécuter UNE SEULE FOIS dans : Supabase → SQL Editor
-- ============================================================

-- Catégories de dépenses
CREATE TABLE IF NOT EXISTS categories (
    id         BIGINT PRIMARY KEY,
    name       TEXT    NOT NULL UNIQUE,
    is_default INTEGER DEFAULT 0
);

-- Mois (pivot pour expenses / revenues / savings)
CREATE TABLE IF NOT EXISTS months (
    id    BIGINT PRIMARY KEY,
    year  INTEGER NOT NULL,
    month INTEGER NOT NULL,
    UNIQUE(year, month)
);

-- Dépenses
CREATE TABLE IF NOT EXISTS expenses (
    id          BIGINT PRIMARY KEY,
    month_id    BIGINT NOT NULL REFERENCES months(id),
    category_id BIGINT NOT NULL REFERENCES categories(id),
    amount      REAL   NOT NULL,
    label       TEXT   DEFAULT '',
    payee       TEXT   DEFAULT ''
);

-- Revenus
CREATE TABLE IF NOT EXISTS revenues (
    id       BIGINT PRIMARY KEY,
    month_id BIGINT NOT NULL REFERENCES months(id),
    source   TEXT   NOT NULL,
    amount   REAL   NOT NULL,
    label    TEXT   DEFAULT ''
);

-- Épargne
CREATE TABLE IF NOT EXISTS savings (
    id       BIGINT PRIMARY KEY,
    month_id BIGINT NOT NULL REFERENCES months(id),
    account  TEXT   DEFAULT '',
    amount   REAL   NOT NULL,
    label    TEXT   DEFAULT ''
);

-- Actifs / Patrimoine
CREATE TABLE IF NOT EXISTS assets (
    id         BIGINT PRIMARY KEY,
    year       INTEGER NOT NULL,
    month      INTEGER NOT NULL,
    asset_type TEXT    NOT NULL,
    asset_name TEXT    NOT NULL,
    value      REAL    NOT NULL,
    cost_basis REAL    DEFAULT 0,
    notes      TEXT    DEFAULT ''
);

-- Transactions sur actifs
CREATE TABLE IF NOT EXISTS asset_transactions (
    id              BIGINT PRIMARY KEY,
    asset_name      TEXT    NOT NULL,
    asset_type      TEXT    NOT NULL,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    trans_type      TEXT    NOT NULL,
    quantity        REAL    NOT NULL DEFAULT 0,
    unit_price      REAL    NOT NULL DEFAULT 0,
    fees            REAL    NOT NULL DEFAULT 0,
    notes           TEXT    DEFAULT '',
    reinvested      INTEGER DEFAULT 0,
    reinvested_into TEXT    DEFAULT ''
);

-- Budgets mensuels
CREATE TABLE IF NOT EXISTS budgets (
    id       BIGINT PRIMARY KEY,
    year     INTEGER NOT NULL,
    month    INTEGER NOT NULL,
    category TEXT    NOT NULL,
    amount   REAL    NOT NULL DEFAULT 0
);

-- Objectifs d'épargne
CREATE TABLE IF NOT EXISTS savings_goals (
    id             BIGINT PRIMARY KEY,
    name           TEXT   NOT NULL,
    target_amount  REAL   NOT NULL,
    target_date    TEXT   NOT NULL,
    current_amount REAL   DEFAULT 0,
    notes          TEXT   DEFAULT '',
    created_at     TEXT   DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD')
);

-- Paramètres de l'application
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

-- ── Désactiver RLS (app privée, accès via service key) ───────
ALTER TABLE categories       DISABLE ROW LEVEL SECURITY;
ALTER TABLE months           DISABLE ROW LEVEL SECURITY;
ALTER TABLE expenses         DISABLE ROW LEVEL SECURITY;
ALTER TABLE revenues         DISABLE ROW LEVEL SECURITY;
ALTER TABLE savings          DISABLE ROW LEVEL SECURITY;
ALTER TABLE assets           DISABLE ROW LEVEL SECURITY;
ALTER TABLE asset_transactions DISABLE ROW LEVEL SECURITY;
ALTER TABLE budgets          DISABLE ROW LEVEL SECURITY;
ALTER TABLE savings_goals    DISABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings     DISABLE ROW LEVEL SECURITY;

-- ── Index de performance ─────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_expenses_month  ON expenses(month_id);
CREATE INDEX IF NOT EXISTS idx_expenses_cat    ON expenses(category_id);
CREATE INDEX IF NOT EXISTS idx_revenues_month  ON revenues(month_id);
CREATE INDEX IF NOT EXISTS idx_savings_month   ON savings(month_id);
CREATE INDEX IF NOT EXISTS idx_assets_period   ON assets(year, month);
CREATE INDEX IF NOT EXISTS idx_asset_tx_period ON asset_transactions(year, month);
CREATE INDEX IF NOT EXISTS idx_budgets_period  ON budgets(year, month);
