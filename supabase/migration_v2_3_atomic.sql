-- ============================================================
-- Fintrack v2.3 — Écritures ATOMIQUES et synchronisation fiable
-- À exécuter dans : Supabase → SQL Editor, AVANT de déployer la v2.3
-- (finance-api et l'app desktop v2.3 appellent ces fonctions).
-- Idempotent, sans perte de données. Inclus aussi pour une nouvelle
-- installation (exécuter après schema.sql).
--
-- Corrige (revue de code v2.2) :
--  1. Envoi desktop « tout supprimer puis réinsérer » non atomique : une
--     panne au milieu laissait Supabase à moitié vide. → fintrack_replace_snapshot
--     fait tout dans UNE transaction (tout ou rien).
--  2. Verrou optimiste fondé sur la comparaison de deux horloges (serveur
--     web vs PC) : un PC en avance pouvait écraser une saisie web. → la
--     version de synchro est un jeton opaque comparé par ÉGALITÉ, vérifié
--     et remplacé dans la même transaction que l'envoi.
--  3. Écritures multi-étapes de finance-api sans transaction (récurrentes,
--     épargne → patrimoine, horodatage de synchro écrit après coup).
--     → fintrack_apply exécute une liste d'opérations en UNE transaction
--     et fait avancer la version de synchro dans cette même transaction.
--  4. Identifiants max(id)+1 calculés côté client avec réessais sur
--     conflit. → attribués en SQL sous un verrou par utilisateur
--     (pg_advisory_xact_lock) qui sérialise aussi toutes ses écritures :
--     plus de course entre « mois ouvert ? » et l'insertion.
--
-- Sécurité : SECURITY INVOKER partout — la RLS de l'appelant s'applique
-- (y compris l'interdiction d'écrire pour les jetons OAuth/MCP). Le
-- user_id est toujours celui du jeton (auth.uid()), jamais celui du client.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS fintrack_private;
REVOKE ALL ON SCHEMA fintrack_private FROM PUBLIC;
GRANT USAGE ON SCHEMA fintrack_private TO authenticated;

-- ── Version de synchronisation (jeton opaque, au format ISO 8601) ──
CREATE OR REPLACE FUNCTION fintrack_private.bump_version(uid uuid)
RETURNS text
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v text := to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00';
BEGIN
    INSERT INTO app_settings (user_id, key, value) VALUES (uid, 'last_supabase_sync', v)
    ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value;
    RETURN v;
END
$$;

-- ── Verrou transactionnel par utilisateur ──
CREATE OR REPLACE FUNCTION fintrack_private.lock_user(uid uuid)
RETURNS void
LANGUAGE sql
AS $$ SELECT pg_advisory_xact_lock(hashtextextended('fintrack:' || uid::text, 0)) $$;

-- ── Références entre opérations : {"$ref": [index, "champ"]} ──
-- Objet JSON (jamais une chaîne) : un libellé saisi par l'utilisateur ne
-- peut pas être pris pour une référence.
CREATE OR REPLACE FUNCTION fintrack_private.resolve(r jsonb, results jsonb)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT coalesce(jsonb_object_agg(e.key,
               CASE WHEN jsonb_typeof(e.value) = 'object' AND e.value ? '$ref'
                    THEN results -> ((e.value -> '$ref' ->> 0)::int) -> (e.value -> '$ref' ->> 1)
                    ELSE e.value END), '{}'::jsonb)
      FROM jsonb_each(coalesce(r, '{}'::jsonb) - 'user_id') AS e
$$;

-- ── Unité de travail de finance-api ──
-- ops : tableau d'opérations exécutées dans l'ordre, en une transaction.
--   {"op":"month", "year":Y, "month":M, "require_open":bool}
--        crée le mois s'il n'existe pas ; erreur si clôturé et require_open
--   {"op":"assert_open", "month_id":N}
--   {"op":"insert", "table":T, "row":{…}}            (ou "rows":[…])
--   {"op":"upsert", "table":T, "row":{…}, "conflict":["col",…]}
--   {"op":"update", "table":T, "where":{…}, "set":{…}, "require":bool}
--   {"op":"delete", "table":T, "where":{…}, "require":bool}
--        require : erreur si aucune ligne touchée ; "on_missing":"conflict"
--        la signale comme un conflit (garde optimiste) et non une absence
--   {"op":"adjust_asset", "asset_name":N, "year":Y, "month":M, "delta":D}
--        épargne → compte lié : valeur et montant investi du DERNIER
--        instantané du compte + D, lus DANS la transaction (deux versements
--        simultanés s'additionnent au lieu de s'écraser). Ignoré si le compte
--        n'existe pas ou si (Y, M) précède son dernier instantané.
-- id absent d'une ligne insérée : max(id)+1 de l'utilisateur (sous verrou).
-- Retour : {"results":[…], "version": nouvelle version de synchro | null}
CREATE OR REPLACE FUNCTION public.fintrack_apply(ops jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    uid      uuid := auth.uid();
    allowed  CONSTANT text[] := ARRAY['months', 'expenses', 'revenues', 'savings', 'assets',
                                      'liabilities', 'budgets', 'recurring_transactions'];
    op       jsonb;
    kind     text;
    tbl      text;
    results  jsonb := '[]'::jsonb;
    res      jsonb;
    item     jsonb;
    one      jsonb;
    cols     text;
    upd      text;
    cond     text;
    nid      bigint;
    n        int;
    wrote    boolean := false;
    mo       months%ROWTYPE;
    cur      assets%ROWTYPE;
    y        int;
    m        int;
    delta    double precision;
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'fintrack:unauthenticated' USING ERRCODE = '42501';
    END IF;
    IF jsonb_typeof(ops) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'fintrack:bad_request' USING ERRCODE = '22023';
    END IF;
    PERFORM fintrack_private.lock_user(uid);

    FOR op IN SELECT value FROM jsonb_array_elements(ops) LOOP
        kind := op ->> 'op';
        tbl  := op ->> 'table';
        res  := NULL;

        IF kind IN ('insert', 'upsert', 'update', 'delete') AND NOT (tbl = ANY (allowed)) THEN
            RAISE EXCEPTION 'fintrack:bad_table' USING ERRCODE = '22023';
        END IF;

        IF kind = 'month' THEN
            INSERT INTO months (user_id, id, year, month, closed)
            VALUES (uid, (SELECT coalesce(max(id), 0) + 1 FROM months WHERE user_id = uid),
                    (op ->> 'year')::int, (op ->> 'month')::int, 0)
            ON CONFLICT (user_id, year, month) DO NOTHING;
            GET DIAGNOSTICS n = ROW_COUNT;
            wrote := wrote OR n > 0;
            SELECT * INTO mo FROM months
             WHERE user_id = uid AND year = (op ->> 'year')::int AND month = (op ->> 'month')::int;
            IF coalesce((op ->> 'require_open')::boolean, false) AND coalesce(mo.closed, 0) <> 0 THEN
                RAISE EXCEPTION 'fintrack:month_closed' USING ERRCODE = 'P0001';
            END IF;
            res := to_jsonb(mo) - 'user_id';

        ELSIF kind = 'adjust_asset' THEN
            y := (op ->> 'year')::int;
            m := (op ->> 'month')::int;
            delta := (op ->> 'delta')::double precision;
            SELECT * INTO cur FROM assets
             WHERE user_id = uid AND asset_type = 'compte' AND asset_name = op ->> 'asset_name'
             ORDER BY year DESC, month DESC LIMIT 1;
            IF FOUND AND delta <> 0 AND ROW(y, m) >= ROW(cur.year, cur.month) THEN
                INSERT INTO assets (user_id, id, year, month, asset_type, asset_name,
                                    value, cost_basis, notes)
                VALUES (uid,
                        CASE WHEN (cur.year, cur.month) = (y, m) THEN cur.id
                             ELSE (SELECT coalesce(max(id), 0) + 1 FROM assets WHERE user_id = uid) END,
                        y, m, 'compte', cur.asset_name,
                        greatest(0, coalesce(cur.value, 0) + delta),
                        greatest(0, coalesce(cur.cost_basis, 0) + delta),
                        coalesce(cur.notes, ''))
                ON CONFLICT (user_id, year, month, asset_type, asset_name)
                DO UPDATE SET value = EXCLUDED.value, cost_basis = EXCLUDED.cost_basis
                RETURNING to_jsonb(assets.*) - 'user_id' INTO res;
                wrote := true;
            END IF;

        ELSIF kind = 'assert_open' THEN
            SELECT * INTO mo FROM months WHERE user_id = uid AND id = (op ->> 'month_id')::bigint;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'fintrack:not_found' USING ERRCODE = 'P0001';
            END IF;
            IF coalesce(mo.closed, 0) <> 0 THEN
                RAISE EXCEPTION 'fintrack:month_closed' USING ERRCODE = 'P0001';
            END IF;

        ELSIF kind IN ('insert', 'upsert') THEN
            res := '[]'::jsonb;
            nid := NULL;                       -- max(id) lu une fois par opération
            FOR item IN SELECT value FROM jsonb_array_elements(
                    coalesce(op -> 'rows', jsonb_build_array(op -> 'row'))) LOOP
                item := fintrack_private.resolve(item, results);
                IF NOT item ? 'id' THEN
                    IF nid IS NULL THEN
                        EXECUTE format('SELECT coalesce(max(id), 0) + 1 FROM %I WHERE user_id = $1', tbl)
                           INTO nid USING uid;
                    ELSE
                        nid := nid + 1;        -- sous verrou : pas de concurrence
                    END IF;
                    item := item || jsonb_build_object('id', nid);
                END IF;
                SELECT string_agg(format('%I', k), ', ') INTO cols FROM jsonb_object_keys(item) AS k;
                IF kind = 'upsert' THEN
                    SELECT string_agg(format('%I = EXCLUDED.%I', k, k), ', ') INTO upd
                      FROM jsonb_object_keys(item) AS k
                     WHERE k <> 'id'
                       AND NOT (k IN (SELECT jsonb_array_elements_text(op -> 'conflict')));
                    SELECT string_agg(format('%I', c), ', ') INTO cond
                      FROM jsonb_array_elements_text(op -> 'conflict') AS c;
                    EXECUTE format('INSERT INTO %1$I AS t (user_id, %2$s) '
                                   'SELECT $1, %2$s FROM jsonb_populate_record(NULL::%1$I, $2) '
                                   'ON CONFLICT (user_id, %3$s) DO UPDATE SET %4$s '
                                   'RETURNING to_jsonb(t.*) - ''user_id''',
                                   tbl, cols, cond, coalesce(upd, 'id = t.id'))
                       INTO one USING uid, item;
                ELSE
                    EXECUTE format('INSERT INTO %1$I AS t (user_id, %2$s) '
                                   'SELECT $1, %2$s FROM jsonb_populate_record(NULL::%1$I, $2) '
                                   'RETURNING to_jsonb(t.*) - ''user_id''', tbl, cols)
                       INTO one USING uid, item;
                END IF;
                res := res || jsonb_build_array(one);
            END LOOP;
            IF op ? 'row' THEN
                res := res -> 0;
            END IF;
            wrote := true;

        ELSIF kind IN ('update', 'delete') THEN
            -- Filtre d'égalité sur l'objet `where` (+ id indexé s'il est fourni).
            cond := 'to_jsonb(t.*) @> $2';
            IF (op -> 'where') ? 'id' THEN
                cond := cond || ' AND t.id = ($2 ->> ''id'')::bigint';
            END IF;
            IF kind = 'update' THEN
                item := fintrack_private.resolve(op -> 'set', results) - 'id';
                SELECT string_agg(format('%I = s.%I', k, k), ', ') INTO upd FROM jsonb_object_keys(item) AS k;
                IF upd IS NULL THEN
                    RAISE EXCEPTION 'fintrack:bad_request' USING ERRCODE = '22023';
                END IF;
                EXECUTE format('WITH w AS (UPDATE %1$I AS t SET %2$s '
                               'FROM jsonb_populate_record(NULL::%1$I, $3) AS s '
                               'WHERE t.user_id = $1 AND %3$s RETURNING to_jsonb(t.*) - ''user_id'' AS j) '
                               'SELECT coalesce(jsonb_agg(j), ''[]'') FROM w', tbl, upd, cond)
                   INTO res USING uid, fintrack_private.resolve(op -> 'where', results), item;
            ELSE
                EXECUTE format('WITH w AS (DELETE FROM %1$I AS t WHERE t.user_id = $1 AND %2$s '
                               'RETURNING to_jsonb(t.*) - ''user_id'' AS j) '
                               'SELECT coalesce(jsonb_agg(j), ''[]'') FROM w', tbl, cond)
                   INTO res USING uid, fintrack_private.resolve(op -> 'where', results);
            END IF;
            IF coalesce((op ->> 'require')::boolean, false) AND jsonb_array_length(res) = 0 THEN
                -- "on_missing": "conflict" : garde optimiste (ligne modifiée
                -- entre la lecture et l'écriture), pas une ligne absente.
                IF op ->> 'on_missing' = 'conflict' THEN
                    RAISE EXCEPTION 'fintrack:conflict' USING ERRCODE = 'P0001';
                END IF;
                RAISE EXCEPTION 'fintrack:not_found' USING ERRCODE = 'P0001';
            END IF;
            wrote := wrote OR jsonb_array_length(res) > 0;

        ELSE
            RAISE EXCEPTION 'fintrack:bad_op' USING ERRCODE = '22023';
        END IF;

        results := results || jsonb_build_array(res);
    END LOOP;

    RETURN jsonb_build_object(
        'results', results,
        'version', CASE WHEN wrote THEN fintrack_private.bump_version(uid) END);
END
$$;

-- ── Envoi complet depuis l'app desktop (tout ou rien) ──
-- p_tables   : {"categories":[…], "months":[…], …} (lignes SQLite, sans user_id)
-- p_settings : {"clé": "valeur", …} (clés non sensibles)
-- p_exclude  : clés app_settings jamais touchées côté serveur
-- p_expected : version de synchro connue du PC (dernier envoi/réception)
-- p_force    : ignorer la vérification de version (confirmation explicite)
-- Retour : la nouvelle version (à conserver localement).
CREATE OR REPLACE FUNCTION public.fintrack_replace_snapshot(
    p_tables jsonb, p_settings jsonb, p_exclude text[], p_expected text, p_force boolean DEFAULT false)
RETURNS text
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
-- Délai propre à cet envoi complet (une seule transaction) : appliqué par
-- PostgREST >= 12.2 (« hoisting » des réglages de fonction) à la place des
-- 8 s par défaut du rôle authenticated. Les autres requêtes ne changent pas.
SET statement_timeout = '120s'
AS $$
DECLARE
    uid      uuid := auth.uid();
    push     CONSTANT text[] := ARRAY['categories', 'months', 'expenses', 'revenues', 'savings',
                                      'assets', 'asset_transactions', 'liabilities', 'budgets',
                                      'savings_goals', 'recurring_transactions'];
    excl     text[] := coalesce(p_exclude, '{}');
    cur      text;
    t        text;
    rows_in  jsonb;
    cols     text;
    i        int;
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'fintrack:unauthenticated' USING ERRCODE = '42501';
    END IF;
    PERFORM fintrack_private.lock_user(uid);

    SELECT value INTO cur FROM app_settings WHERE user_id = uid AND key = 'last_supabase_sync';
    IF NOT coalesce(p_force, false) AND cur IS NOT NULL AND cur IS DISTINCT FROM p_expected THEN
        RAISE EXCEPTION 'fintrack:sync_conflict' USING ERRCODE = 'P0001';
    END IF;

    FOR i IN REVERSE array_length(push, 1) .. 1 LOOP
        EXECUTE format('DELETE FROM %I WHERE user_id = $1', push[i]) USING uid;
    END LOOP;
    DELETE FROM app_settings WHERE user_id = uid AND NOT (key = ANY (excl));

    FOREACH t IN ARRAY push LOOP
        rows_in := p_tables -> t;
        CONTINUE WHEN rows_in IS NULL OR jsonb_typeof(rows_in) <> 'array'
                   OR jsonb_array_length(rows_in) = 0;
        SELECT string_agg(format('%I', k), ', ') INTO cols
          FROM jsonb_object_keys(rows_in -> 0) AS k WHERE k <> 'user_id';
        EXECUTE format('INSERT INTO %1$I (user_id, %2$s) '
                       'SELECT $1, %2$s FROM jsonb_populate_recordset(NULL::%1$I, $2)', t, cols)
           USING uid, rows_in;
    END LOOP;

    INSERT INTO app_settings (user_id, key, value)
    SELECT uid, e.key, e.value #>> '{}'
      FROM jsonb_each(coalesce(p_settings, '{}'::jsonb)) AS e
     WHERE e.key <> 'last_supabase_sync' AND NOT (e.key = ANY (excl))
    ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value;

    RETURN fintrack_private.bump_version(uid);
END
$$;

REVOKE ALL ON FUNCTION public.fintrack_apply(jsonb) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.fintrack_replace_snapshot(jsonb, jsonb, text[], text, boolean) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION fintrack_private.bump_version(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION fintrack_private.lock_user(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION fintrack_private.resolve(jsonb, jsonb) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.fintrack_apply(jsonb) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fintrack_replace_snapshot(jsonb, jsonb, text[], text, boolean) TO authenticated;
GRANT EXECUTE ON FUNCTION fintrack_private.bump_version(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION fintrack_private.lock_user(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION fintrack_private.resolve(jsonb, jsonb) TO authenticated;

-- ── Index alignés sur la RLS (revue v2.2) ──
-- Les id (month_id, category_id…) sont attribués PAR UTILISATEUR : un index
-- sur month_id seul mélange les lignes de tous les comptes. Toutes les
-- requêtes filtrent d'abord sur user_id (RLS + filtre explicite).
CREATE INDEX IF NOT EXISTS idx_expenses_user_month_cat ON expenses (user_id, month_id, category_id);
CREATE INDEX IF NOT EXISTS idx_expenses_user_cat       ON expenses (user_id, category_id);
CREATE INDEX IF NOT EXISTS idx_expenses_user_payee     ON expenses (user_id, payee);
CREATE INDEX IF NOT EXISTS idx_revenues_user_month     ON revenues (user_id, month_id);
CREATE INDEX IF NOT EXISTS idx_savings_user_month      ON savings (user_id, month_id);
CREATE INDEX IF NOT EXISTS idx_assets_user_name        ON assets (user_id, asset_type, asset_name);
CREATE INDEX IF NOT EXISTS idx_budgets_user_period     ON budgets (user_id, year, month);
CREATE INDEX IF NOT EXISTS idx_asset_tx_user_name      ON asset_transactions (user_id, asset_name);
CREATE INDEX IF NOT EXISTS idx_recurring_user_cat      ON recurring_transactions (user_id, category_id);
DROP INDEX IF EXISTS idx_expenses_month;
DROP INDEX IF EXISTS idx_expenses_cat;
DROP INDEX IF EXISTS idx_expenses_payee;
DROP INDEX IF EXISTS idx_expenses_month_cat;
DROP INDEX IF EXISTS idx_expenses_month_payee;
DROP INDEX IF EXISTS idx_revenues_month;
DROP INDEX IF EXISTS idx_savings_month;
DROP INDEX IF EXISTS idx_assets_period;
DROP INDEX IF EXISTS idx_assets_name_type;
DROP INDEX IF EXISTS idx_assets_type_period;
DROP INDEX IF EXISTS idx_asset_tx_period;
DROP INDEX IF EXISTS idx_asset_tx_name;
DROP INDEX IF EXISTS idx_budgets_period;

-- PostgREST : recharger le cache du schéma (nouvelles fonctions RPC)
NOTIFY pgrst, 'reload schema';
