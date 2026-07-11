-- ============================================================
-- Finance Tracker — Schéma Supabase PostgreSQL (COMPLET)
-- À exécuter UNE SEULE FOIS lors d'une nouvelle installation.
-- Pour mettre à jour un projet existant : utiliser supabase_migration.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS categories (
    id         BIGINT PRIMARY KEY,
    name       TEXT    NOT NULL UNIQUE,
    is_default INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS months (
    id     BIGINT  PRIMARY KEY,
    year   INTEGER NOT NULL,
    month  INTEGER NOT NULL,
    closed INTEGER DEFAULT 0,
    UNIQUE(year, month)
);

CREATE TABLE IF NOT EXISTS expenses (
    id          BIGINT PRIMARY KEY,
    month_id    BIGINT NOT NULL REFERENCES months(id),
    category_id BIGINT NOT NULL REFERENCES categories(id),
    amount      REAL   NOT NULL,
    label       TEXT   DEFAULT '',
    payee       TEXT   DEFAULT ''
);

CREATE TABLE IF NOT EXISTS revenues (
    id       BIGINT PRIMARY KEY,
    month_id BIGINT NOT NULL REFERENCES months(id),
    source   TEXT   NOT NULL,
    amount   REAL   NOT NULL,
    label    TEXT   DEFAULT ''
);

CREATE TABLE IF NOT EXISTS savings (
    id       BIGINT PRIMARY KEY,
    month_id BIGINT NOT NULL REFERENCES months(id),
    account  TEXT   DEFAULT '',
    amount   REAL   NOT NULL,
    label    TEXT   DEFAULT ''
);

CREATE TABLE IF NOT EXISTS assets (
    id         BIGINT  PRIMARY KEY,
    year       INTEGER NOT NULL,
    month      INTEGER NOT NULL,
    asset_type TEXT    NOT NULL,
    asset_name TEXT    NOT NULL,
    value      REAL    NOT NULL,
    cost_basis REAL    DEFAULT 0,
    notes      TEXT    DEFAULT '',
    UNIQUE(year, month, asset_type, asset_name)
);

CREATE TABLE IF NOT EXISTS asset_transactions (
    id              BIGINT  PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS budgets (
    id       BIGINT  PRIMARY KEY,
    year     INTEGER NOT NULL,
    month    INTEGER NOT NULL,
    category TEXT    NOT NULL,
    amount   REAL    NOT NULL DEFAULT 0,
    UNIQUE(year, month, category)
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id             BIGINT PRIMARY KEY,
    name           TEXT   NOT NULL,
    target_amount  REAL   NOT NULL,
    target_date    TEXT   NOT NULL,
    current_amount REAL   DEFAULT 0,
    notes          TEXT   DEFAULT '',
    created_at     TEXT   DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD')
);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS recurring_transactions (
    id                 BIGINT  PRIMARY KEY,
    label              TEXT    NOT NULL DEFAULT '',
    amount             REAL    NOT NULL DEFAULT 0,
    type               TEXT    NOT NULL DEFAULT 'expense',
    category_id        BIGINT  REFERENCES categories(id),
    source             TEXT    DEFAULT '',
    payee              TEXT    DEFAULT '',
    active             INTEGER DEFAULT 1,
    last_applied_year  INTEGER DEFAULT 0,
    last_applied_month INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS liabilities (
    id                BIGINT  PRIMARY KEY,
    year              INTEGER NOT NULL,
    month             INTEGER NOT NULL,
    liability_type    TEXT    NOT NULL DEFAULT 'autre',
    liability_name    TEXT    NOT NULL,
    remaining_capital REAL    NOT NULL DEFAULT 0,
    monthly_payment   REAL    NOT NULL DEFAULT 0,
    end_date          TEXT    DEFAULT '',
    notes             TEXT    DEFAULT '',
    UNIQUE(year, month, liability_name)
);

-- Désactiver RLS (app privée, accès via service key)
ALTER TABLE categories             DISABLE ROW LEVEL SECURITY;
ALTER TABLE months                 DISABLE ROW LEVEL SECURITY;
ALTER TABLE expenses               DISABLE ROW LEVEL SECURITY;
ALTER TABLE revenues               DISABLE ROW LEVEL SECURITY;
ALTER TABLE savings                DISABLE ROW LEVEL SECURITY;
ALTER TABLE assets                 DISABLE ROW LEVEL SECURITY;
ALTER TABLE asset_transactions     DISABLE ROW LEVEL SECURITY;
ALTER TABLE budgets                DISABLE ROW LEVEL SECURITY;
ALTER TABLE savings_goals          DISABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings           DISABLE ROW LEVEL SECURITY;
ALTER TABLE recurring_transactions DISABLE ROW LEVEL SECURITY;
ALTER TABLE liabilities            DISABLE ROW LEVEL SECURITY;

-- Index de performance
CREATE INDEX IF NOT EXISTS idx_expenses_month       ON expenses(month_id);
CREATE INDEX IF NOT EXISTS idx_expenses_cat         ON expenses(category_id);
CREATE INDEX IF NOT EXISTS idx_expenses_payee       ON expenses(payee);
CREATE INDEX IF NOT EXISTS idx_expenses_month_cat   ON expenses(month_id, category_id);
CREATE INDEX IF NOT EXISTS idx_expenses_month_payee ON expenses(month_id, payee);
CREATE INDEX IF NOT EXISTS idx_revenues_month       ON revenues(month_id);
CREATE INDEX IF NOT EXISTS idx_savings_month        ON savings(month_id);
CREATE INDEX IF NOT EXISTS idx_assets_period        ON assets(year, month);
CREATE INDEX IF NOT EXISTS idx_assets_name_type     ON assets(asset_name, asset_type);
CREATE INDEX IF NOT EXISTS idx_assets_type_period   ON assets(asset_type, year, month);
CREATE INDEX IF NOT EXISTS idx_asset_tx_period      ON asset_transactions(year, month);
CREATE INDEX IF NOT EXISTS idx_asset_tx_name        ON asset_transactions(asset_name);
CREATE INDEX IF NOT EXISTS idx_budgets_period       ON budgets(year, month);
