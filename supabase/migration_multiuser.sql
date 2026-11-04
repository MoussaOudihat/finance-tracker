-- ============================================================
-- Finance Tracker — Migration vers le schéma multi-utilisateur (v1.3)
-- À exécuter dans : Supabase → SQL Editor, sur le projet EXISTANT
-- qui contient déjà vos données (mono-utilisateur, RLS désactivée).
--
-- ⚠️  AVANT DE LANCER CE SCRIPT :
--   1. Prenez une sauvegarde du projet (Dashboard → Database → Backups,
--      ou "Database → Backups → Download" selon votre plan).
--   2. Créez le compte Supabase Auth réel (Dashboard → Authentication →
--      Users → "Add user", cochez "Auto Confirm User") et remplacez TOUTES
--      les occurrences de <REAL_USER_ID> ci-dessous par son UID.
--   3. Fermez l'application Fintrack pendant toute la migration (pas de
--      push/pull concurrent).
--
-- Ce script est sûr : aucune ligne n'est supprimée, seulement des
-- colonnes/contraintes ajoutées. RLS n'a aucun effet tant que l'app
-- utilise encore la clé service_role (qui la contourne) — le vrai
-- point de bascule est le jour où vous reconfigurez l'app avec la
-- clé "anon" + connexion Supabase Auth (écran "Compte cloud").
-- ============================================================


-- ════════════════════════════════════════════════════════════
--  ÉTAPE 1 — Ajouter user_id, backfiller sur le compte réel,
--  verrouiller NOT NULL + FK vers auth.users
-- ════════════════════════════════════════════════════════════

ALTER TABLE categories ADD COLUMN user_id uuid;
UPDATE categories SET user_id = '<REAL_USER_ID>';
ALTER TABLE categories ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE categories ADD CONSTRAINT categories_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE months ADD COLUMN user_id uuid;
UPDATE months SET user_id = '<REAL_USER_ID>';
ALTER TABLE months ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE months ADD CONSTRAINT months_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE expenses ADD COLUMN user_id uuid;
UPDATE expenses SET user_id = '<REAL_USER_ID>';
ALTER TABLE expenses ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE expenses ADD CONSTRAINT expenses_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE revenues ADD COLUMN user_id uuid;
UPDATE revenues SET user_id = '<REAL_USER_ID>';
ALTER TABLE revenues ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE revenues ADD CONSTRAINT revenues_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE savings ADD COLUMN user_id uuid;
UPDATE savings SET user_id = '<REAL_USER_ID>';
ALTER TABLE savings ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE savings ADD CONSTRAINT savings_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE assets ADD COLUMN user_id uuid;
UPDATE assets SET user_id = '<REAL_USER_ID>';
ALTER TABLE assets ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE assets ADD CONSTRAINT assets_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE asset_transactions ADD COLUMN user_id uuid;
UPDATE asset_transactions SET user_id = '<REAL_USER_ID>';
ALTER TABLE asset_transactions ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE asset_transactions ADD CONSTRAINT asset_transactions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE budgets ADD COLUMN user_id uuid;
UPDATE budgets SET user_id = '<REAL_USER_ID>';
ALTER TABLE budgets ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE budgets ADD CONSTRAINT budgets_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE savings_goals ADD COLUMN user_id uuid;
UPDATE savings_goals SET user_id = '<REAL_USER_ID>';
ALTER TABLE savings_goals ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE savings_goals ADD CONSTRAINT savings_goals_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE app_settings ADD COLUMN user_id uuid;
UPDATE app_settings SET user_id = '<REAL_USER_ID>';
ALTER TABLE app_settings ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE app_settings ADD CONSTRAINT app_settings_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE recurring_transactions ADD COLUMN user_id uuid;
UPDATE recurring_transactions SET user_id = '<REAL_USER_ID>';
ALTER TABLE recurring_transactions ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE recurring_transactions ADD CONSTRAINT recurring_transactions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE liabilities ADD COLUMN user_id uuid;
UPDATE liabilities SET user_id = '<REAL_USER_ID>';
ALTER TABLE liabilities ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE liabilities ADD CONSTRAINT liabilities_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- ── Vérification avant de continuer ──────────────────────────
-- Chaque ligne doit renvoyer un compte égal au total de la table
-- (aucune ligne user_id IS NULL ne doit rester).
--   SELECT 'categories', count(*) FROM categories WHERE user_id = '<REAL_USER_ID>'
--   UNION ALL SELECT 'months', count(*) FROM months WHERE user_id = '<REAL_USER_ID>'
--   UNION ALL SELECT 'expenses', count(*) FROM expenses WHERE user_id = '<REAL_USER_ID>'
--   UNION ALL SELECT 'revenues', count(*) FROM revenues WHERE user_id = '<REAL_USER_ID>'
--   UNION ALL SELECT 'savings', count(*) FROM savings WHERE user_id = '<REAL_USER_ID>'
--   UNION ALL SELECT 'assets', count(*) FROM assets WHERE user_id = '<REAL_USER_ID>';


-- ════════════════════════════════════════════════════════════
--  ÉTAPE 2 — (optionnel mais recommandé) Vérifier les noms de
--  contraintes réels avant de les supprimer à l'étape 3.
-- ════════════════════════════════════════════════════════════
-- SELECT conrelid::regclass AS table_name, conname, contype
-- FROM pg_constraint
-- WHERE conrelid::regclass::text IN (
--   'categories','months','expenses','revenues','savings','assets',
--   'asset_transactions','budgets','savings_goals','app_settings',
--   'recurring_transactions','liabilities')
-- ORDER BY table_name, contype;
-- Si un nom ci-dessous ne correspond pas à ce que retourne cette requête,
-- corrigez-le avant d'exécuter l'étape 3 (Postgres nomme automatiquement
-- <table>_pkey / <table>_<colonnes>_key / <table>_<col>_fkey par défaut,
-- ce qui est le nommage attendu ici pour un schéma jamais renommé).


-- ════════════════════════════════════════════════════════════
--  ÉTAPE 3 — Clés composites (user_id, id) + contraintes user-scopées
--  Transaction unique : tout ou rien.
-- ════════════════════════════════════════════════════════════
BEGIN;

-- 1) FK enfants qui référencent months(id) / categories(id)
ALTER TABLE expenses  DROP CONSTRAINT expenses_month_id_fkey;
ALTER TABLE expenses  DROP CONSTRAINT expenses_category_id_fkey;
ALTER TABLE revenues  DROP CONSTRAINT revenues_month_id_fkey;
ALTER TABLE savings   DROP CONSTRAINT savings_month_id_fkey;
ALTER TABLE recurring_transactions DROP CONSTRAINT recurring_transactions_category_id_fkey;

-- 2) Anciennes PK simples
ALTER TABLE categories             DROP CONSTRAINT categories_pkey;
ALTER TABLE months                 DROP CONSTRAINT months_pkey;
ALTER TABLE expenses               DROP CONSTRAINT expenses_pkey;
ALTER TABLE revenues               DROP CONSTRAINT revenues_pkey;
ALTER TABLE savings                DROP CONSTRAINT savings_pkey;
ALTER TABLE assets                 DROP CONSTRAINT assets_pkey;
ALTER TABLE asset_transactions     DROP CONSTRAINT asset_transactions_pkey;
ALTER TABLE budgets                DROP CONSTRAINT budgets_pkey;
ALTER TABLE savings_goals          DROP CONSTRAINT savings_goals_pkey;
ALTER TABLE app_settings           DROP CONSTRAINT app_settings_pkey;
ALTER TABLE recurring_transactions DROP CONSTRAINT recurring_transactions_pkey;
ALTER TABLE liabilities            DROP CONSTRAINT liabilities_pkey;

-- 3) Anciens UNIQUE (doivent devenir scopés par utilisateur)
-- NOTE : vérifié via pg_constraint sur ce projet — assets/budgets/liabilities
-- n'ont en réalité jamais eu de contrainte UNIQUE en base (seulement dans le
-- schéma de référence), donc rien à supprimer pour ces trois tables.
ALTER TABLE categories    DROP CONSTRAINT categories_name_key;
ALTER TABLE months        DROP CONSTRAINT months_year_month_key;

-- 4) Nouvelles PK composites (user_id en premier : colonne de filtre RLS,
--    meilleure localité d'index)
ALTER TABLE categories             ADD CONSTRAINT categories_pkey             PRIMARY KEY (user_id, id);
ALTER TABLE months                 ADD CONSTRAINT months_pkey                 PRIMARY KEY (user_id, id);
ALTER TABLE expenses               ADD CONSTRAINT expenses_pkey               PRIMARY KEY (user_id, id);
ALTER TABLE revenues               ADD CONSTRAINT revenues_pkey               PRIMARY KEY (user_id, id);
ALTER TABLE savings                ADD CONSTRAINT savings_pkey                PRIMARY KEY (user_id, id);
ALTER TABLE assets                 ADD CONSTRAINT assets_pkey                 PRIMARY KEY (user_id, id);
ALTER TABLE asset_transactions     ADD CONSTRAINT asset_transactions_pkey     PRIMARY KEY (user_id, id);
ALTER TABLE budgets                ADD CONSTRAINT budgets_pkey                PRIMARY KEY (user_id, id);
ALTER TABLE savings_goals          ADD CONSTRAINT savings_goals_pkey          PRIMARY KEY (user_id, id);
ALTER TABLE app_settings           ADD CONSTRAINT app_settings_pkey           PRIMARY KEY (user_id, key);
ALTER TABLE recurring_transactions ADD CONSTRAINT recurring_transactions_pkey PRIMARY KEY (user_id, id);
ALTER TABLE liabilities            ADD CONSTRAINT liabilities_pkey            PRIMARY KEY (user_id, id);

-- 5) FK composites reconstruites (child.user_id doit == parent.user_id)
ALTER TABLE expenses ADD CONSTRAINT expenses_month_id_fkey
    FOREIGN KEY (user_id, month_id) REFERENCES months(user_id, id);
ALTER TABLE expenses ADD CONSTRAINT expenses_category_id_fkey
    FOREIGN KEY (user_id, category_id) REFERENCES categories(user_id, id);
ALTER TABLE revenues ADD CONSTRAINT revenues_month_id_fkey
    FOREIGN KEY (user_id, month_id) REFERENCES months(user_id, id);
ALTER TABLE savings ADD CONSTRAINT savings_month_id_fkey
    FOREIGN KEY (user_id, month_id) REFERENCES months(user_id, id);
ALTER TABLE recurring_transactions ADD CONSTRAINT recurring_transactions_category_id_fkey
    FOREIGN KEY (user_id, category_id) REFERENCES categories(user_id, id);

-- 6) UNIQUE reconstruits, scopés utilisateur
ALTER TABLE categories  ADD CONSTRAINT categories_user_name_key    UNIQUE (user_id, name);
ALTER TABLE months      ADD CONSTRAINT months_user_year_month_key  UNIQUE (user_id, year, month);
ALTER TABLE assets      ADD CONSTRAINT assets_user_period_asset_key UNIQUE (user_id, year, month, asset_type, asset_name);
ALTER TABLE budgets     ADD CONSTRAINT budgets_user_period_cat_key UNIQUE (user_id, year, month, category);
ALTER TABLE liabilities ADD CONSTRAINT liabilities_user_period_name_key UNIQUE (user_id, year, month, liability_name);

COMMIT;


-- ════════════════════════════════════════════════════════════
--  ÉTAPE 4 — Row Level Security
--  Sans danger : tant que l'app utilise encore service_role, RLS est
--  contournée. Le vrai changement de comportement n'aura lieu que
--  lorsque l'app basculera sur la clé "anon" (étape applicative,
--  écran "Compte cloud" → Se connecter avec le compte créé plus haut).
-- ════════════════════════════════════════════════════════════
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


-- ════════════════════════════════════════════════════════════
--  APRÈS CE SCRIPT
-- ════════════════════════════════════════════════════════════
-- 1. Dans l'app Fintrack (nouvelle version), écran de connexion →
--    "Compte cloud" → "Se connecter" avec l'email/mot de passe créés
--    à l'étape 1, l'URL du projet, et la clé "anon" (Dashboard →
--    Project Settings → API → "anon public").
-- 2. Vérifier que toutes les données apparaissent normalement.
-- 3. Seulement après vérification complète : régénérer/révoquer la
--    clé service_role (Dashboard → Project Settings → API →
--    "Reset service_role key") — elle n'est plus utilisée par l'app.
