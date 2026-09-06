-- ============================================================
-- Finance Tracker — Schéma Supabase PostgreSQL (COMPLET, multi-utilisateur)
-- À exécuter UNE SEULE FOIS lors d'une toute NOUVELLE installation
-- (nouveau projet Supabase, jamais utilisé par Fintrack).
--
-- Pour migrer un projet EXISTANT (schéma mono-utilisateur créé avant la
-- v1.3) vers ce schéma : utiliser supabase_migration_multiuser.sql,
-- qui préserve les données déjà présentes. Ne PAS lancer ce fichier-ci
-- sur un projet qui contient déjà des données.
--
-- Chaque ligne appartient à un utilisateur Supabase Auth (colonne
-- user_id). Row Level Security garantit qu'un utilisateur ne peut
-- jamais lire ni écrire les lignes d'un autre. L'app se connecte avec
-- la clé "anon" (publique) + une session Supabase Auth — jamais avec
-- la clé service_role.
-- ============================================================

CREATE TABLE IF NOT EXISTS categories (
    id         BIGINT NOT NULL,
    user_id    UUID   NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name       TEXT   NOT NULL,
    is_default INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS months (
    id      BIGINT  NOT NULL,
    user_id UUID    NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    year    INTEGER NOT NULL,
    month   INTEGER NOT NULL,
    closed  INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, year, month)
);

CREATE TABLE IF NOT EXISTS expenses (
    id          BIGINT NOT NULL,
    user_id     UUID   NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    month_id    BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    amount      REAL   NOT NULL,
    label       TEXT   DEFAULT '',
    payee       TEXT   DEFAULT '',
    PRIMARY KEY (user_id, id),
    FOREIGN KEY (user_id, month_id)    REFERENCES months(user_id, id),
    FOREIGN KEY (user_id, category_id) REFERENCES categories(user_id, id)
);

CREATE TABLE IF NOT EXISTS revenues (
    id       BIGINT NOT NULL,
    user_id  UUID   NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    month_id BIGINT NOT NULL,
    source   TEXT   NOT NULL,
    amount   REAL   NOT NULL,
    label    TEXT   DEFAULT '',
    PRIMARY KEY (user_id, id),
    FOREIGN KEY (user_id, month_id) REFERENCES months(user_id, id)
);

CREATE TABLE IF NOT EXISTS savings (
    id                BIGINT NOT NULL,
    user_id           UUID   NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    month_id          BIGINT NOT NULL,
    account           TEXT   DEFAULT '',
    amount            REAL   NOT NULL,
    label             TEXT   DEFAULT '',
    linked_asset_name TEXT   DEFAULT '',
    PRIMARY KEY (user_id, id),
    FOREIGN KEY (user_id, month_id) REFERENCES months(user_id, id)
);

CREATE TABLE IF NOT EXISTS assets (
    id         BIGINT  NOT NULL,
    user_id    UUID    NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    year       INTEGER NOT NULL,
    month      INTEGER NOT NULL,
    asset_type TEXT    NOT NULL,
    asset_name TEXT    NOT NULL,
    value      REAL    NOT NULL,
    cost_basis REAL    DEFAULT 0,
    notes      TEXT    DEFAULT '',
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, year, month, asset_type, asset_name)
);

CREATE TABLE IF NOT EXISTS asset_transactions (
    id              BIGINT  NOT NULL,
    user_id         UUID    NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
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
    reinvested_into TEXT    DEFAULT '',
    PRIMARY KEY (user_id, id)
);

CREATE TABLE IF NOT EXISTS budgets (
    id       BIGINT  NOT NULL,
    user_id  UUID    NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    year     INTEGER NOT NULL,
    month    INTEGER NOT NULL,
    category TEXT    NOT NULL,
    amount   REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, year, month, category)
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id             BIGINT NOT NULL,
    user_id        UUID   NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name           TEXT   NOT NULL,
    target_amount  REAL   NOT NULL,
    target_date    TEXT   NOT NULL,
    current_amount REAL   DEFAULT 0,
    notes          TEXT   DEFAULT '',
    created_at     TEXT   DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD'),
    PRIMARY KEY (user_id, id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key     TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    value   TEXT DEFAULT '',
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS recurring_transactions (
    id                 BIGINT  NOT NULL,
    user_id            UUID    NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    label              TEXT    NOT NULL DEFAULT '',
    amount             REAL    NOT NULL DEFAULT 0,
    type               TEXT    NOT NULL DEFAULT 'expense',
    category_id        BIGINT,
    source             TEXT    DEFAULT '',
    payee              TEXT    DEFAULT '',
    active             INTEGER DEFAULT 1,
    last_applied_year  INTEGER DEFAULT 0,
    last_applied_month INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, id),
    FOREIGN KEY (user_id, category_id) REFERENCES categories(user_id, id)
);

CREATE TABLE IF NOT EXISTS liabilities (
    id                BIGINT  NOT NULL,
    user_id           UUID    NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    year              INTEGER NOT NULL,
    month             INTEGER NOT NULL,
    liability_type    TEXT    NOT NULL DEFAULT 'autre',
    liability_name    TEXT    NOT NULL,
    remaining_capital REAL    NOT NULL DEFAULT 0,
    monthly_payment   REAL    NOT NULL DEFAULT 0,
    end_date          TEXT    DEFAULT '',
    notes             TEXT    DEFAULT '',
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, year, month, liability_name)
);

-- ── Row Level Security : chacun ne voit/modifie que ses propres lignes ──
ALTER TABLE categories             ENABLE ROW LEVEL SECURITY;
ALTER TABLE months                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE expenses               ENABLE ROW LEVEL SECURITY;
ALTER TABLE revenues               ENABLE ROW LEVEL SECURITY;
ALTER TABLE savings                ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_transactions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE budgets                ENABLE ROW LEVEL SECURITY;
ALTER TABLE savings_goals          ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings           ENABLE ROW LEVEL SECURITY;
ALTER TABLE recurring_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE liabilities            ENABLE ROW LEVEL SECURITY;

CREATE POLICY categories_owner    ON categories             FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY months_owner        ON months                 FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY expenses_owner      ON expenses               FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY revenues_owner      ON revenues               FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY savings_owner       ON savings                FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY assets_owner        ON assets                 FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY asset_tx_owner      ON asset_transactions     FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY budgets_owner       ON budgets                FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY savings_goals_owner ON savings_goals          FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY app_settings_owner  ON app_settings           FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY recurring_owner     ON recurring_transactions FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY liabilities_owner   ON liabilities            FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

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
