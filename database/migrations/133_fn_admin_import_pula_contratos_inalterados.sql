-- =====================================================
-- Migracao 133: fn_admin_import pula contratos inalterados no upsert
--
-- Problema (verificado em 2026-10-08): o import de contratos do
-- angry-man (lotes de 1000, 4 em paralelo, via Edge Function
-- admin-import) estourou o statement_timeout de 8s do authenticator
-- em todos os lotes ("canceling statement due to statement timeout").
--
-- Causa: o ON CONFLICT DO UPDATE reescreve TODAS as linhas do lote,
-- mesmo as identicas ao que ja esta no banco. Cada UPDATE em
-- contratos e non-HOT e mantem os 14 indices da tabela. Medido em
-- producao (transacao com ROLLBACK, 1000 contratos existentes, tudo
-- em cache): ~1,6s para reescrever; com 4 lotes simultaneos na CPU
-- Nano cada um vai a 4-8s. O historico do pg_stat_statements ja
-- mostrava max de 7,5s — o lote vivia no limite.
--
-- Correcao: para p_table = 'contratos' o DO UPDATE ganha
--   WHERE (contratos.<cols>) IS DISTINCT FROM (EXCLUDED.<cols>)
-- e linhas identicas nao sao tocadas. Mesmo teste: ~195ms.
-- Numa reimportacao a maior parte dos contratos vem igual.
--
-- Decisoes:
--   * So contratos. As outras 7 tabelas da whitelist tem trigger
--     atualizar_updated_at; pular o UPDATE deixaria de bumpar
--     updated_at, e o Numeros_venda usa updated_at como desempate
--     (src/dashboard/loaders.py). contratos nao tem trigger nem
--     updated_at — nada observavel muda alem do custo.
--   * 'count' preserva o contrato atual: total de linhas do lote
--     processadas (o app faz data.length como "processados"). Antes,
--     sem erro, o count ja era sempre o tamanho do lote — duplicata
--     dentro do lote levanta "cannot affect row a second time" nos
--     dois casos. Chave nova 'alterados' = linhas inseridas ou
--     efetivamente alteradas; a Edge Function hoje a ignora.
--   * Comparacao por linha: as colunas comparadas sao as mesmas do
--     SET (as do payload, menos id/created_at). Nenhuma coluna de
--     contratos e json/xml (sem operador de igualdade) — conferido.
--   * Mesma assinatura (text, jsonb, text, jsonb): CREATE OR REPLACE
--     nao cria sobrecarga e mantem os GRANTs (postgres, service_role).
--   * Ordem de deploy livre: Edge Function e app nao mudam.
--
-- Fora isso, IDENTICA a definicao em producao (conferida contra
-- pg_get_functiondef em 2026-10-08).
--
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE OR REPLACE FUNCTION public.fn_admin_import(
    p_table text,
    p_data jsonb,
    p_on_conflict text DEFAULT NULL::text,
    p_delete_where jsonb DEFAULT NULL::jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_count         integer := 0;
    v_insert_cols   text;
    v_update_cols   text;
    v_conflict_cols text;
    v_delete_where  text;
    v_sql           text;
    v_cmp_atual     text;
    v_cmp_novo      text;
    v_update_where  text := '';
    v_allowed       text[] := ARRAY[
        'regioes','lojas','consultores','supervisores',
        'periodos','produtos','contratos','metas','pontuacao'
    ];
BEGIN
    -- 1. Validar tabela (whitelist contra SQL injection)
    IF NOT (p_table = ANY(v_allowed)) THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format('Tabela nao permitida: %s', p_table)
        );
    END IF;

    IF p_data IS NULL OR jsonb_array_length(p_data) = 0 THEN
        RETURN jsonb_build_object('count', 0, 'error', NULL);
    END IF;

    -- 2. DELETE antes do insert quando p_delete_where for informado.
    -- Constrói WHERE col = 'val' para cada chave do JSONB.
    -- %I faz quoting seguro do identificador; %L do literal.
    IF p_delete_where IS NOT NULL
       AND jsonb_typeof(p_delete_where) = 'object'
    THEN
        SELECT string_agg(format('%I = %L', key, value), ' AND ')
        INTO v_delete_where
        FROM jsonb_each_text(p_delete_where);

        IF v_delete_where IS NOT NULL THEN
            v_sql := format('DELETE FROM %I WHERE %s', p_table, v_delete_where);
            EXECUTE v_sql;
        END IF;
    END IF;

    -- 3. Construir lista de colunas de conflito com quoting seguro por coluna.
    -- Ignorado quando p_delete_where foi usado (insert simples após delete).
    IF p_on_conflict IS NOT NULL AND p_delete_where IS NULL THEN
        SELECT string_agg(format('%I', trim(col)), ', ')
        INTO v_conflict_cols
        FROM unnest(string_to_array(p_on_conflict, ',')) AS col
        WHERE trim(col) != '';
    END IF;

    -- 4. Colunas do JSONB que existem na tabela destino
    SELECT
        string_agg(format('%I', c.column_name), ', ' ORDER BY c.ordinal_position),
        string_agg(
            CASE WHEN c.column_name NOT IN ('id', 'created_at')
                THEN format('%I = EXCLUDED.%I', c.column_name, c.column_name)
            END,
            ', ' ORDER BY c.ordinal_position
        ),
        -- Mesmas colunas do SET, para o filtro de linha inalterada.
        string_agg(
            CASE WHEN c.column_name NOT IN ('id', 'created_at')
                THEN format('%I.%I', p_table, c.column_name)
            END,
            ', ' ORDER BY c.ordinal_position
        ),
        string_agg(
            CASE WHEN c.column_name NOT IN ('id', 'created_at')
                THEN format('EXCLUDED.%I', c.column_name)
            END,
            ', ' ORDER BY c.ordinal_position
        )
    INTO v_insert_cols, v_update_cols, v_cmp_atual, v_cmp_novo
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name   = p_table
      AND c.column_name IN (
          SELECT jsonb_object_keys(p_data -> 0)
      );

    -- Remover NULLs residuais do string_agg (colunas excluidas)
    v_update_cols := array_to_string(
        array_remove(
            string_to_array(v_update_cols, ', '),
            NULL
        ),
        ', '
    );

    IF v_insert_cols IS NULL THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Nenhuma coluna valida encontrada no payload'
        );
    END IF;

    -- Migration 133: em contratos, nao reescrever linha identica
    -- (UPDATE non-HOT mantem os 14 indices). Outras tabelas tem
    -- trigger de updated_at — ficam como estavam.
    IF p_table = 'contratos' AND v_cmp_atual IS NOT NULL THEN
        v_update_where := format(
            ' WHERE (%s) IS DISTINCT FROM (%s)', v_cmp_atual, v_cmp_novo
        );
    END IF;

    -- 5. Montar e executar SQL dinamico
    IF v_conflict_cols IS NOT NULL AND v_update_cols IS NOT NULL
       AND v_update_cols != '' THEN
        -- Upsert normal: ON CONFLICT (...) DO UPDATE
        v_sql := format(
            'WITH ins AS (
                INSERT INTO %I (%s)
                SELECT %s
                FROM jsonb_populate_recordset(null::%I, $1)
                ON CONFLICT (%s) DO UPDATE SET %s%s
                RETURNING 1
            ) SELECT count(*) FROM ins',
            p_table, v_insert_cols,
            v_insert_cols,
            p_table, v_conflict_cols, v_update_cols, v_update_where
        );
    ELSIF p_delete_where IS NOT NULL THEN
        -- Insert após delete: ON CONFLICT DO NOTHING para linhas
        -- duplicadas dentro do próprio arquivo (segurança extra).
        v_sql := format(
            'WITH ins AS (
                INSERT INTO %I (%s)
                SELECT %s
                FROM jsonb_populate_recordset(null::%I, $1)
                ON CONFLICT DO NOTHING
                RETURNING 1
            ) SELECT count(*) FROM ins',
            p_table, v_insert_cols,
            v_insert_cols,
            p_table
        );
    ELSE
        -- Insert simples sem tratamento de conflito
        v_sql := format(
            'WITH ins AS (
                INSERT INTO %I (%s)
                SELECT %s
                FROM jsonb_populate_recordset(null::%I, $1)
                RETURNING 1
            ) SELECT count(*) FROM ins',
            p_table, v_insert_cols,
            v_insert_cols,
            p_table
        );
    END IF;

    EXECUTE v_sql INTO v_count USING p_data;

    -- Com o filtro, RETURNING so conta as linhas tocadas. 'count'
    -- continua sendo o lote processado (contrato com o app);
    -- 'alterados' expoe o que de fato foi gravado.
    IF v_update_where != '' AND v_sql LIKE '%DO UPDATE%' THEN
        RETURN jsonb_build_object(
            'count', jsonb_array_length(p_data),
            'alterados', v_count,
            'error', NULL
        );
    END IF;

    RETURN jsonb_build_object('count', v_count, 'error', NULL);

EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('count', 0, 'error', SQLERRM);
END;
$function$;

NOTIFY pgrst, 'reload schema';


-- ===========================================
-- Verificacao (rodar apos aplicar):
--
-- (cliente_norm e coluna gerada — o app nao a envia.)
--
-- 1. Reimportar contratos existentes nao altera nada e devolve o lote:
--   BEGIN;
--   SELECT public.fn_admin_import(
--       'contratos',
--       (SELECT jsonb_agg(to_jsonb(c) - 'id' - 'created_at' - 'cliente_norm')
--        FROM (SELECT * FROM public.contratos
--              ORDER BY data_cadastro DESC LIMIT 1000) c),
--       'contrato_id', NULL);
--   ROLLBACK;
--   -- esperado: {"count": 1000, "alterados": 0, "error": null}
--
-- 2. Linha alterada e gravada:
--   BEGIN;
--   SELECT public.fn_admin_import(
--       'contratos',
--       (SELECT jsonb_agg(jsonb_set(to_jsonb(c) - 'id' - 'created_at' - 'cliente_norm',
--                                   '{valor}', to_jsonb(c.valor + 1)))
--        FROM (SELECT * FROM public.contratos
--              ORDER BY data_cadastro DESC LIMIT 5) c),
--       'contrato_id', NULL);
--   ROLLBACK;
--   -- esperado: {"count": 5, "alterados": 5, "error": null}
--
-- 3. Outras tabelas inalteradas (sem 'alterados' na resposta):
--   BEGIN;
--   SELECT public.fn_admin_import('regioes',
--       (SELECT jsonb_agg(to_jsonb(r) - 'created_at' - 'updated_at')
--        FROM public.regioes r), 'id', NULL);
--   ROLLBACK;
-- ===========================================
