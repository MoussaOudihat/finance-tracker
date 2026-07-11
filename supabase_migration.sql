-- ============================================================
-- Finance Tracker — Script de MIGRATION Supabase
-- À exécuter dans : Supabase → SQL Editor
--
-- Ce script est IDEMPOTENT : tu peux le relancer sans risque,
-- il ne touche pas aux données existantes.
-- Il ajoute uniquement ce qui manque (nouvelles tables / colonnes).
-- ============================================================


-- ── 1. Nouvelles tables manquantes ───────────────────────────

-- Transactions récurrentes (ajoutées en v1.1)
CREATE TABLE IF NOT EXISTS recurring_transactions (
    id                 BIGINT PRIMARY KEY,
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
ALTER TABLE recurring_transactions DISABLE ROW LEVEL SECURITY;

-- Passifs / Dettes (ajoutés en v1.1)
CREATE TABLE IF NOT EXISTS liabilities (
    id                BIGINT  PRIMARY KEY,
    year              INTEGER NOT NULL,
    month             INTEGER NOT NULL,
    liability_type    TEXT    NOT NULL DEFAULT 'autre',
    liability_name    TEXT    NOT NULL,
    remaining_capital REAL    NOT NULL DEFAULT 0,
    monthly_payment   REAL    NOT NULL DEFAULT 0,
    end_date          TEXT    DEFAULT '',
    notes             TEXT    DEFAULT ''
);
ALTER TABLE liabilities DISABLE ROW LEVEL SECURITY;


-- ── 2. Nouvelles colonnes sur tables existantes ──────────────

-- months.closed (mois verrouillé)
ALTER TABLE months ADD COLUMN IF NOT EXISTS closed INTEGER DEFAULT 0;

-- assets.cost_basis (prix de revient)
ALTER TABLE assets ADD COLUMN IF NOT EXISTS cost_basis REAL DEFAULT 0;

-- asset_transactions : réinvestissement
ALTER TABLE asset_transactions ADD COLUMN IF NOT EXISTS reinvested      INTEGER DEFAULT 0;
ALTER TABLE asset_transactions ADD COLUMN IF NOT EXISTS reinvested_into TEXT    DEFAULT '';

-- expenses.payee (bénéficiaire)
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS payee TEXT DEFAULT '';


-- ── 3. Index manquants ───────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_expenses_payee       ON expenses(payee);
CREATE INDEX IF NOT EXISTS idx_expenses_month_cat   ON expenses(month_id, category_id);
CREATE INDEX IF NOT EXISTS idx_expenses_month_payee ON expenses(month_id, payee);
CREATE INDEX IF NOT EXISTS idx_assets_name_type     ON assets(asset_name, asset_type);
CREATE INDEX IF NOT EXISTS idx_assets_type_period   ON assets(asset_type, year, month);
CREATE INDEX IF NOT EXISTS idx_asset_tx_name        ON asset_transactions(asset_name);


-- ── 4. Vérification finale ───────────────────────────────────
-- Après exécution, tu devrais voir ces tables dans ton projet :
--   categories, months, expenses, revenues, savings,
--   assets, asset_transactions, budgets, savings_goals,
--   app_settings, recurring_transactions, liabilities
