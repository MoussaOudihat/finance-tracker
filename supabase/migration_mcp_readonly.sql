-- ============================================================
-- Fintrack v2.3 — Accès MCP en LECTURE SEULE garanti par la base
-- À exécuter dans : Supabase → SQL Editor (idempotent, sans perte de
-- données). Nouvelle installation : à exécuter APRÈS schema.sql et
-- migration_v2_3_atomic.sql — schema.sql ne contient PAS ces politiques.
-- ⚠️  Ne pas activer le serveur MCP (mcp.enabled) tant que ce fichier n'a
-- pas été exécuté : sans lui, un jeton OAuth a les mêmes droits d'écriture
-- qu'une session web. Vérification : requête en fin de fichier.
--
-- Contexte : le serveur MCP (services/mcp_server) reçoit des jetons émis
-- par le serveur OAuth 2.1 de Supabase Auth pour un client MCP (Claude
-- Code, claude.ai, opencode…). Ces jetons portent un claim `client_id` ;
-- les sessions web et desktop (connexion par mot de passe) n'en ont pas.
--
-- Les politiques RESTRICTIVE ci-dessous s'ajoutent (ET logique) aux
-- politiques *_owner existantes : un jeton OAuth peut LIRE les lignes de
-- son utilisateur, jamais en insérer, modifier ou supprimer — même si le
-- serveur MCP était compromis ou appelait PostgREST directement.
--
-- Pour ouvrir plus tard l'écriture à un client précis, remplacer la
-- condition par : (SELECT auth.jwt() ->> 'client_id') IS NULL
--                 OR (SELECT auth.jwt() ->> 'client_id') = '<client_id>'
--
-- Les politiques *_owner sont aussi réécrites avec (SELECT auth.uid()) :
-- évaluée une seule fois par requête au lieu d'une fois par ligne
-- (recommandation Supabase « auth_rls_initplan »). Même règle d'accès.
-- ============================================================

DO $$
DECLARE
    t      text;
    owner  text;
    owners CONSTANT text[][] := ARRAY[
        ['categories',             'categories_owner'],
        ['months',                 'months_owner'],
        ['expenses',               'expenses_owner'],
        ['revenues',               'revenues_owner'],
        ['savings',                'savings_owner'],
        ['assets',                 'assets_owner'],
        ['asset_transactions',     'asset_tx_owner'],
        ['budgets',                'budgets_owner'],
        ['savings_goals',          'savings_goals_owner'],
        ['app_settings',           'app_settings_owner'],
        ['recurring_transactions', 'recurring_owner'],
        ['liabilities',            'liabilities_owner']
    ];
    no_oauth CONSTANT text := '((SELECT auth.jwt() ->> ''client_id'') IS NULL)';
    i int;
BEGIN
    FOR i IN 1 .. array_length(owners, 1) LOOP
        t := owners[i][1];
        owner := owners[i][2];

        -- Propriétaire (même règle, évaluation unique par requête)
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', owner, t);
        EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO authenticated '
                       'USING (user_id = (SELECT auth.uid())) '
                       'WITH CHECK (user_id = (SELECT auth.uid()))', owner, t);

        -- Jetons OAuth (clients MCP) : aucune écriture
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_oauth_no_insert', t);
        EXECUTE format('CREATE POLICY %I ON %I AS RESTRICTIVE FOR INSERT TO authenticated '
                       'WITH CHECK %s', t || '_oauth_no_insert', t, no_oauth);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_oauth_no_update', t);
        EXECUTE format('CREATE POLICY %I ON %I AS RESTRICTIVE FOR UPDATE TO authenticated '
                       'USING %s WITH CHECK %s', t || '_oauth_no_update', t, no_oauth, no_oauth);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_oauth_no_delete', t);
        EXECUTE format('CREATE POLICY %I ON %I AS RESTRICTIVE FOR DELETE TO authenticated '
                       'USING %s', t || '_oauth_no_delete', t, no_oauth);
    END LOOP;
END $$;

-- Vérification : 4 politiques par table (owner + 3 restrictives)
-- SELECT tablename, policyname, permissive, cmd FROM pg_policies
--  WHERE schemaname = 'public' ORDER BY tablename, policyname;
