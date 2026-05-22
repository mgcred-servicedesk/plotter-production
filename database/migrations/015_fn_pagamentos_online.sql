-- =====================================================
-- Migracao 015: RPCs para ingestao de pagamentos_online
--
-- Contexto:
-- A migracao 014 criou a tabela `pagamentos_online` e a
-- view `v_pagamentos_online_efetivo`. Esta migracao adiciona
-- as RPCs que o angry-man chama via service_role para:
--   1. Substituir o conteudo da tabela atomicamente (DELETE
--      + INSERT em uma transacao, com advisory lock e
--      validacao de minimo de linhas).
--   2. Limpar a tabela (DELETE simples) no fim do dia.
--
-- Por que RPCs separadas em vez de extender fn_admin_import:
--   - fn_admin_import nao suporta DELETE-ALL (so chave=valor).
--   - O contrato exige advisory lock + pre-validacao de minimo,
--     ambos especificos desta feature.
--   - Mantem a superficie de fn_admin_import enxuta e auditavel.
--
-- Seguranca:
--   - Ambas SECURITY DEFINER. EXECUTE concedido APENAS a
--     service_role; anon/authenticated bloqueados.
--   - O angry-man chama via service_role no Electron main
--     process (ou via Edge Function em modo web no futuro).
--
-- Doc do contrato: database/INTEGRACAO_PAGAMENTOS_ONLINE.md
-- =====================================================


-- ===========================================
-- 1. fn_pagamentos_online_replace(p_data jsonb)
--
-- Substitui integralmente o conteudo de `pagamentos_online`
-- de forma atomica. Recebe um array JSONB de registros ja
-- filtrados (Grupo Produto IN ('Antecipacao em Conta',
-- 'Credito na Conta')) pelo angry-man.
--
-- Garante:
--   (a) Pre-validacao de minimo de linhas (50) para evitar
--       wipe silencioso por CSV corrompido.
--   (b) Advisory lock no id 20260521 — duas chamadas
--       concorrentes serializam.
--   (c) DELETE + INSERT na MESMA transacao (a funcao toda
--       roda como uma unica transacao implicita). Se o
--       INSERT falhar, o DELETE e revertido.
--
-- Retorno:
--   { count: N, count_before: M, error: NULL }       sucesso
--   { count: 0, error: 'mensagem' }                  falha
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_pagamentos_online_replace(p_data jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_min_linhas    integer := 50;
    v_payload_len   integer;
    v_count_before  integer := 0;
    v_count_after   integer := 0;
BEGIN
    -- 1. Validar payload nao-nulo e do tipo array
    IF p_data IS NULL OR jsonb_typeof(p_data) <> 'array' THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Payload ausente ou nao e um array JSON.'
        );
    END IF;

    v_payload_len := jsonb_array_length(p_data);

    -- 2. Pre-validacao de minimo de linhas (evita wipe silencioso)
    IF v_payload_len < v_min_linhas THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format(
                'CSV com %s linhas apos filtro — abaixo do minimo esperado (%s). Upload abortado.',
                v_payload_len, v_min_linhas
            )
        );
    END IF;

    -- 3. Advisory lock — serializa uploads concorrentes
    PERFORM pg_advisory_xact_lock(20260521);

    -- 4. Snapshot do count anterior (para retornar o delta)
    SELECT count(*) INTO v_count_before FROM pagamentos_online;

    -- 5. Substituicao atomica
    -- `WHERE true` e necessario porque a extensao `safeupdate`
    -- (carregada por padrao no Supabase) bloqueia DELETE sem WHERE.
    -- Funcionalmente equivalente a DELETE FROM pagamentos_online.
    DELETE FROM pagamentos_online WHERE true;

    INSERT INTO pagamentos_online (
        proposta, data_implantacao, data_status, cliente,
        grupo_produto, produto, loja_codigo, usuario_nome,
        status, situacao, agrupamento,
        valor_liquido_digitado, valor_liquido_aprovado, valor_seguro_aprovado
    )
    SELECT
        proposta,
        data_implantacao,
        data_status,
        cliente,
        grupo_produto,
        produto,
        loja_codigo,
        usuario_nome,
        status,
        situacao,
        agrupamento,
        valor_liquido_digitado,
        valor_liquido_aprovado,
        valor_seguro_aprovado
    FROM jsonb_populate_recordset(null::pagamentos_online, p_data);

    GET DIAGNOSTICS v_count_after = ROW_COUNT;

    RETURN jsonb_build_object(
        'count',         v_count_after,
        'count_before',  v_count_before,
        'error',         NULL
    );

EXCEPTION WHEN OTHERS THEN
    -- A transacao implicita da funcao ja foi revertida pelo Postgres
    -- ao chegar aqui, entao o DELETE nao persistiu.
    RETURN jsonb_build_object(
        'count', 0,
        'error', SQLERRM
    );
END;
$$;

COMMENT ON FUNCTION public.fn_pagamentos_online_replace(jsonb) IS
    'Substitui atomicamente o conteudo de pagamentos_online a '
    'partir de um array JSONB ja filtrado pelo angry-man. '
    'Valida minimo de 50 linhas, aplica advisory lock '
    '(id 20260521) e faz DELETE+INSERT na mesma transacao. '
    'SECURITY DEFINER; EXECUTE so para service_role.';


-- ===========================================
-- 2. fn_pagamentos_online_clear()
--
-- Limpa `pagamentos_online`. Disparada no fim do dia (manual
-- na fase 1, cron na fase 2) para evitar que os pagamentos
-- de ontem aparecam como "do dia" no primeiro acesso ao
-- dashboard em D+1.
--
-- Retorna o count anterior (para log/feedback do operador).
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_pagamentos_online_clear()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count_before integer := 0;
BEGIN
    SELECT count(*) INTO v_count_before FROM pagamentos_online;
    -- `WHERE true` requerido pela extensao safeupdate do Supabase.
    DELETE FROM pagamentos_online WHERE true;
    RETURN jsonb_build_object(
        'cleared', v_count_before,
        'error',   NULL
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object(
        'cleared', 0,
        'error',   SQLERRM
    );
END;
$$;

COMMENT ON FUNCTION public.fn_pagamentos_online_clear() IS
    'Limpa pagamentos_online (DELETE sem WHERE). Usada na '
    'limpeza de fim de dia. SECURITY DEFINER; EXECUTE so '
    'para service_role.';


-- ===========================================
-- 3. Permissoes
--
-- Padrao: fechar para anon/authenticated, abrir so para
-- service_role. O angry-man (Electron) ja roda com
-- service_role. Em modo web, uma Edge Function dedicada
-- (futura) seria o canal autorizado.
-- ===========================================

REVOKE ALL ON FUNCTION public.fn_pagamentos_online_replace(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_pagamentos_online_replace(jsonb) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_pagamentos_online_replace(jsonb) TO service_role;

REVOKE ALL ON FUNCTION public.fn_pagamentos_online_clear() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_pagamentos_online_clear() FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_pagamentos_online_clear() TO service_role;


-- ===========================================
-- 4. Validacao pos-migracao (opcional)
-- ===========================================
-- Smoke test:
--
--   SELECT public.fn_pagamentos_online_clear();
--   -- { "cleared": 0, "error": null }
--
--   -- Replace com payload abaixo do minimo (deve recusar):
--   SELECT public.fn_pagamentos_online_replace(
--       jsonb_build_array(jsonb_build_object('proposta','X'))
--   );
--   -- { "count": 0, "error": "CSV com 1 linhas ..." }
--
-- Confirmar permissoes:
--   SELECT routine_name, grantee, privilege_type
--   FROM information_schema.routine_privileges
--   WHERE routine_name IN (
--       'fn_pagamentos_online_replace',
--       'fn_pagamentos_online_clear'
--   );
