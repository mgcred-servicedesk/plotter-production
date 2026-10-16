-- =====================================================
-- Migracao 141: fix de fn_importar_reconquista_elegivel (140)
--
-- BUG (reportado pelo usuario no primeiro import, 16/10/2026):
--   "column reference "baixa_prioridade" is ambiguous" (42702)
-- A RPC da 140 declara `baixa_prioridade` em RETURNS TABLE (contador de
-- saida) e a tabela `reconquista_elegivel` tem coluna com o mesmo nome.
-- No PL/pgSQL, as colunas de RETURNS TABLE sao variaveis: o
-- `RETURNING elegivel, baixa_prioridade, ...` sem qualificar ficou
-- ambiguo e TODO import falhava (a transacao revertia; nada foi gravado).
-- O smoke test da 140 so exercitou as recusas, que abortam antes do
-- INSERT — por isso nao pegou.
--
-- FIX: alias `t` na tabela de destino e RETURNING qualificado. Nenhuma
-- outra mudanca: mesma assinatura, mesmo retorno, mesmas validacoes.
-- CREATE OR REPLACE preserva GRANT/REVOKE e o COMMENT da 140; reaplicados
-- abaixo so por defesa.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE OR REPLACE FUNCTION public.fn_importar_reconquista_elegivel(
    p_periodo_id UUID,
    p_rows       JSONB
)
RETURNS TABLE (
    removidos         INTEGER,
    inseridos         INTEGER,
    elegiveis         INTEGER,
    baixa_prioridade  INTEGER,
    sem_loja          INTEGER,
    sem_consultor     INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_ano        INTEGER;
    v_mes        INTEGER;
    v_ref        TEXT;
    v_removidos  INTEGER := 0;
    v_qtd        INTEGER;
    v_lista      TEXT;
    v_valores    TEXT;
BEGIN
    -- ---------------------------------------
    -- Periodo
    -- ---------------------------------------
    SELECT p.ano, p.mes INTO v_ano, v_mes
    FROM public.periodos p
    WHERE p.id = p_periodo_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Periodo % inexistente.', p_periodo_id;
    END IF;

    v_ref := lpad(v_mes::TEXT, 2, '0') || '/' || v_ano;

    -- ---------------------------------------
    -- Forma do payload
    -- ---------------------------------------
    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RAISE EXCEPTION '%', 'Payload invalido: esperado um array JSON de '
            || 'linhas. Nada foi gravado.';
    END IF;

    IF jsonb_array_length(p_rows) = 0 THEN
        RAISE EXCEPTION '%', format(
            'Nenhum cliente elegivel para %s no lote. Nada foi gravado nem '
            || 'removido (confira o periodo escolhido e o arquivo).', v_ref);
    END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) e
        WHERE jsonb_typeof(e) <> 'object'
    ) THEN
        RAISE EXCEPTION '%', 'Payload invalido: toda linha deve ser um '
            || 'objeto JSON. Nada foi gravado.';
    END IF;

    -- Lista FECHADA de chaves: barra nu_matricula / franqueado / gerencia
    SELECT string_agg(DISTINCT k, ', ' ORDER BY k) INTO v_lista
    FROM jsonb_array_elements(p_rows) e,
         LATERAL jsonb_object_keys(e) k
    WHERE k <> ALL (ARRAY[
        'co_adesao', 'anomes_referencia',
        'flag_elegibilidade', 'flag_atuacao', 'motivo_impedido_operar',
        'status_cliente_anterior', 'status_cliente_atual',
        'flag_promessa_sem_retorno', 'saldo_carteira',
        'banco_origem', 'banco_destino', 'banco_saldo_residual',
        'regra_pagamento', 'link_reconquista',
        'no_franquia', 'cod_bmg', 'supervisor_nome', 'consultor_nome'
    ]);

    IF v_lista IS NOT NULL THEN
        RAISE EXCEPTION '%', format(
            'Payload com chave(s) nao permitida(s): %s. A Carteira Elegivel '
            || 'nao aceita nu_matricula, franqueado nem cadeia de gerencia. '
            || 'Nada foi gravado.', v_lista);
    END IF;

    -- ---------------------------------------
    -- co_adesao ausente
    -- ---------------------------------------
    SELECT count(*) INTO v_qtd
    FROM jsonb_array_elements(p_rows) e
    WHERE NULLIF(TRIM(e->>'co_adesao'), '') IS NULL;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) sem co_adesao (ADE). Nada foi '
            || 'gravado.', v_qtd);
    END IF;

    -- ---------------------------------------
    -- co_adesao duplicado (lista ate 20 ADEs)
    -- ---------------------------------------
    SELECT count(*),
           string_agg(d.ade::TEXT, ', ' ORDER BY d.ade) FILTER (WHERE d.rn <= 20)
      INTO v_qtd, v_lista
    FROM (
        SELECT x.ade, row_number() OVER (ORDER BY x.ade) AS rn
        FROM (
            SELECT (e->>'co_adesao')::BIGINT AS ade
            FROM jsonb_array_elements(p_rows) e
        ) x
        GROUP BY x.ade
        HAVING count(*) > 1
    ) d;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s ADE(s) duplicada(s) no arquivo para %s: %s%s. '
            || 'Nada foi gravado.',
            v_qtd, v_ref, v_lista,
            CASE WHEN v_qtd > 20 THEN format(' (e mais %s)', v_qtd - 20) ELSE '' END);
    END IF;

    -- ---------------------------------------
    -- anomes_referencia ausente ou diferente do periodo
    -- ---------------------------------------
    SELECT count(*),
           string_agg(DISTINCT COALESCE(NULLIF(TRIM(e->>'anomes_referencia'), ''),
                                        'vazio'), ', ')
      INTO v_qtd, v_valores
    FROM jsonb_array_elements(p_rows) e
    WHERE NULLIF(TRIM(e->>'anomes_referencia'), '') IS NULL
       OR TRIM(e->>'anomes_referencia') <> (v_ano * 100 + v_mes)::TEXT;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) com anomes_referencia ausente ou '
            || 'diferente de %s (valores: %s). Nada foi gravado.',
            v_qtd, (v_ano * 100 + v_mes)::TEXT, v_valores);
    END IF;

    -- ---------------------------------------
    -- Flag de elegibilidade vazia/desconhecida
    -- Normalizacao IDENTICA a do INSERT abaixo.
    -- ---------------------------------------
    SELECT count(*),
           string_agg(f.ade::TEXT, ', ' ORDER BY f.ade) FILTER (WHERE f.rn <= 20),
           string_agg(DISTINCT COALESCE('"' || f.flag || '"', 'nula'), ', ')
      INTO v_qtd, v_lista, v_valores
    FROM (
        SELECT x.ade, x.flag, row_number() OVER (ORDER BY x.ade) AS rn
        FROM (
            SELECT (e->>'co_adesao')::BIGINT AS ade,
                   e->>'flag_elegibilidade' AS flag
            FROM jsonb_array_elements(p_rows) e
        ) x
        WHERE translate(upper(trim(x.flag)), 'ÍÃ', 'IA') IS NULL
           OR translate(upper(trim(x.flag)), 'ÍÃ', 'IA')
                  NOT IN ('ELEGIVEL', 'NAO ELEGIVEL')
    ) f;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) com flag de elegibilidade vazia ou '
            || 'desconhecida (valores: %s). ADEs: %s%s. Esperado ELEGIVEL ou '
            || 'NAO ELEGIVEL. Nada foi gravado.',
            v_qtd, v_valores, v_lista,
            CASE WHEN v_qtd > 20 THEN format(' (e mais %s)', v_qtd - 20) ELSE '' END);
    END IF;

    -- ---------------------------------------
    -- Flag de atuacao vazia/desconhecida
    -- Normalizacao IDENTICA a do INSERT abaixo.
    -- ---------------------------------------
    SELECT count(*),
           string_agg(f.ade::TEXT, ', ' ORDER BY f.ade) FILTER (WHERE f.rn <= 20),
           string_agg(DISTINCT COALESCE('"' || f.flag || '"', 'nula'), ', ')
      INTO v_qtd, v_lista, v_valores
    FROM (
        SELECT x.ade, x.flag, row_number() OVER (ORDER BY x.ade) AS rn
        FROM (
            SELECT (e->>'co_adesao')::BIGINT AS ade,
                   e->>'flag_atuacao' AS flag
            FROM jsonb_array_elements(p_rows) e
        ) x
        WHERE regexp_replace(upper(trim(x.flag)), '\s+', ' ', 'g') IS NULL
           OR regexp_replace(upper(trim(x.flag)), '\s+', ' ', 'g')
                  NOT IN ('PRIORIDADE', 'BAIXA PRIORIDADE')
    ) f;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) com flag de atuacao vazia ou '
            || 'desconhecida (valores: %s). ADEs: %s%s. Esperado PRIORIDADE ou '
            || 'BAIXA PRIORIDADE. Nada foi gravado.',
            v_qtd, v_valores, v_lista,
            CASE WHEN v_qtd > 20 THEN format(' (e mais %s)', v_qtd - 20) ELSE '' END);
    END IF;

    -- ---------------------------------------
    -- Lote valido: substitui o periodo
    -- ---------------------------------------
    DELETE FROM public.reconquista_elegivel WHERE periodo_id = p_periodo_id;
    GET DIAGNOSTICS v_removidos = ROW_COUNT;

    RETURN QUERY
    WITH src AS (
        SELECT
            r.co_adesao,
            r.flag_elegibilidade,
            translate(upper(trim(r.flag_elegibilidade)), 'ÍÃ', 'IA')  AS flag_eleg_norm,
            r.flag_atuacao,
            regexp_replace(upper(trim(r.flag_atuacao)), '\s+', ' ', 'g') AS flag_atu_norm,
            NULLIF(TRIM(r.motivo_impedido_operar), '')                AS motivo_impedido_operar,
            NULLIF(TRIM(r.status_cliente_anterior), '')               AS status_cliente_anterior,
            NULLIF(TRIM(r.status_cliente_atual), '')                  AS status_cliente_atual,
            NULLIF(TRIM(r.flag_promessa_sem_retorno), '')             AS flag_promessa_sem_retorno,
            r.saldo_carteira,
            NULLIF(TRIM(r.banco_origem), '')                          AS banco_origem,
            NULLIF(TRIM(r.banco_destino), '')                         AS banco_destino,
            NULLIF(TRIM(r.banco_saldo_residual), '')                  AS banco_saldo_residual,
            NULLIF(TRIM(r.regra_pagamento), '')                       AS regra_pagamento,
            NULLIF(TRIM(r.link_reconquista), '')                      AS link_reconquista,
            NULLIF(TRIM(r.no_franquia), '')                           AS no_franquia,
            r.cod_bmg,
            NULLIF(TRIM(r.supervisor_nome), '')                       AS supervisor_nome,
            NULLIF(TRIM(r.consultor_nome), '')                        AS consultor_nome
        FROM jsonb_to_recordset(p_rows) AS r (
            co_adesao                  BIGINT,
            flag_elegibilidade         TEXT,
            flag_atuacao               TEXT,
            motivo_impedido_operar     TEXT,
            status_cliente_anterior    TEXT,
            status_cliente_atual       TEXT,
            flag_promessa_sem_retorno  TEXT,
            saldo_carteira             NUMERIC(15, 2),
            banco_origem               TEXT,
            banco_destino              TEXT,
            banco_saldo_residual       TEXT,
            regra_pagamento            TEXT,
            link_reconquista           TEXT,
            no_franquia                TEXT,
            cod_bmg                    INTEGER,
            supervisor_nome            TEXT,
            consultor_nome             TEXT
        )
    ),
    resolvido AS (
        SELECT s.*, lj.loja_id, cs.consultor_id
        FROM src s
        -- Loja: cod_bmg ja com sucessora aplicada (criterio da 053/127/137)
        LEFT JOIN LATERAL (
            SELECT COALESCE(l.sucessora_id, l.id) AS loja_id
            FROM public.lojas l
            WHERE l.cod_bmg = s.cod_bmg
            LIMIT 1
        ) lj ON true
        -- Consultor: nome completo + loja (criterio da 053/127/137)
        LEFT JOIN LATERAL (
            SELECT c.id AS consultor_id
            FROM public.consultores c
            WHERE s.consultor_nome IS NOT NULL
              AND c.nome ILIKE s.consultor_nome
              AND (c.loja_id = lj.loja_id OR c.loja_id IS NULL)
            ORDER BY CASE WHEN c.loja_id = lj.loja_id THEN 0 ELSE 1 END, c.nome
            LIMIT 1
        ) cs ON true
    ),
    ins AS (
        -- Alias `t` + RETURNING qualificado (fix da 141): `baixa_prioridade`
        -- e tambem coluna de saida do RETURNS TABLE, e sem qualificar o
        -- PL/pgSQL nao sabe se e a variavel ou a coluna (42702).
        INSERT INTO public.reconquista_elegivel AS t (
            periodo_id, co_adesao,
            flag_elegibilidade, elegivel, flag_atuacao, baixa_prioridade,
            motivo_impedido_operar, status_cliente_anterior,
            status_cliente_atual, flag_promessa_sem_retorno, saldo_carteira,
            banco_origem, banco_destino, banco_saldo_residual,
            regra_pagamento, link_reconquista,
            no_franquia, cod_bmg, loja_id,
            supervisor_nome, consultor_nome, consultor_id
        )
        SELECT
            p_periodo_id, r.co_adesao,
            r.flag_elegibilidade, (r.flag_eleg_norm = 'ELEGIVEL'),
            r.flag_atuacao, (r.flag_atu_norm = 'BAIXA PRIORIDADE'),
            r.motivo_impedido_operar, r.status_cliente_anterior,
            r.status_cliente_atual, r.flag_promessa_sem_retorno,
            r.saldo_carteira,
            r.banco_origem, r.banco_destino, r.banco_saldo_residual,
            r.regra_pagamento, r.link_reconquista,
            r.no_franquia, r.cod_bmg, r.loja_id,
            r.supervisor_nome, r.consultor_nome, r.consultor_id
        FROM resolvido r
        RETURNING t.elegivel, t.baixa_prioridade, t.loja_id, t.consultor_id
    )
    SELECT
        v_removidos,
        count(*)::INTEGER,
        (count(*) FILTER (WHERE i.elegivel))::INTEGER,
        (count(*) FILTER (WHERE i.baixa_prioridade))::INTEGER,
        (count(*) FILTER (WHERE i.loja_id IS NULL))::INTEGER,
        (count(*) FILTER (WHERE i.consultor_id IS NULL))::INTEGER
    FROM ins i;
END;
$$;

COMMENT ON FUNCTION public.fn_importar_reconquista_elegivel(UUID, JSONB) IS
    'Carteira Elegivel da Reconquista: valida o lote inteiro (chaves '
    'permitidas, ADE unica, anomes_referencia = periodo, flag de '
    'elegibilidade e de atuacao conhecidas) e so entao faz DELETE do periodo '
    '+ INSERT, na mesma transacao. Deriva `elegivel` e `baixa_prioridade`; '
    'resolve loja_id (cod_bmg + sucessora) e consultor_id (nome completo + '
    'loja). Retorna (removidos, inseridos, elegiveis, baixa_prioridade, '
    'sem_loja, sem_consultor) para o log do importador.';

REVOKE EXECUTE ON FUNCTION public.fn_importar_reconquista_elegivel(UUID, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_importar_reconquista_elegivel(UUID, JSONB)
    TO service_role;

NOTIFY pgrst, 'reload schema';


-- =====================================================
-- VALIDACAO — caminho de SUCESSO, sem gravar (tudo em ROLLBACK).
-- Esperado: 1 linha (removidos 0, inseridos 1, elegiveis 1,
-- baixa_prioridade 1, sem_loja 0 ou 1, sem_consultor 0 ou 1) — e nao o
-- erro 42702.
--
--    BEGIN;
--    SELECT * FROM public.fn_importar_reconquista_elegivel(
--        (SELECT id FROM public.periodos WHERE ano = 2026 AND mes = 10),
--        '[{"co_adesao":1,"anomes_referencia":202610,
--           "flag_elegibilidade":"ELEGÍVEL",
--           "flag_atuacao":"BAIXA PRIORIDADE"}]');
--    ROLLBACK;
--
-- Depois: reimportar o Extrator de Elegiveis de 10/2026 pelo angry-man e
-- rodar as validacoes 1 e 2 da migration 140.
-- =====================================================
