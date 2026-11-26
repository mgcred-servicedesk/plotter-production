-- =====================================================
-- Migracao 149: obter_cancelados_classificados — CTE `paga`
--               MATERIALIZED (plano estavel do matching de
--               recuperacao)
--
-- Contexto (diagnostico de performance de 26/11/2026,
-- pg_stat_statements desde 15/10/2026): esta RPC, via o wrapper
-- obter_cancelados_classificados_json, somava 29,5% do tempo de
-- execucao do banco — 1.395 chamadas, media 2,7 s, maximo 27 s,
-- ~1,66M buffers por chamada. Em 07/10/2026 levava 50-150 ms.
--
-- Causa (EXPLAIN ANALYZE, janela 27/10-26/11/2026): `paga` e
-- referenciado UMA vez, entao desde o PG12 o planner o inlina. Sem
-- estatistica do CTE `canc`, ele estimou 81 cancelados a cruzar
-- (eram 2.533) e escolheu nested loop: para CADA cancelado, um
-- range scan em idx_contratos_cadastro_status sobre os ~1.600 pagos
-- dos 7 dias seguintes, filtrando cliente_norm depois. 876 mil dos
-- 901 mil buffers da chamada vinham dai. O custo crescia com
-- cancelados x pagos-por-janela, e o volume dobrou desde julho.
--
-- Correcao (UNICA mudanca vs 052): `paga AS MATERIALIZED`. O pago
-- da janela e montado uma vez (~3,9k linhas, ~1,4k buffers) e o
-- matching vira hash join (nome_norm, categoria_codigo), que cresce
-- com a SOMA dos dois lados. Medido na mesma janela: 1.985 ms /
-- 901k buffers -> 58 ms / 13,9k buffers, mesmo resultado (833
-- cancelados com match). `canc` ja e materializado (3 referencias).
--
-- Fora isso, IDENTICO a 052: mesma classificacao (redigitada /
-- recuperada / liquido), mesmas flags de oportunidade, mesmo
-- matching por cliente_norm + categoria em 7 dias, mesmos SET.
-- `SET statement_timeout` fica, embora seja ineficaz (o teto e o do
-- papel: memoria/progress de 08/10/2026) — remover e outra decisao.
-- RETURNS TABLE inalterado -> CREATE OR REPLACE (sem DROP); o
-- wrapper _json (135) nao muda. Migration 052 e imutavel; esta a
-- substitui.
--
-- Executar no Supabase SQL Editor. Requer 052 aplicada.
-- =====================================================

CREATE OR REPLACE FUNCTION obter_cancelados_classificados(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    id                        UUID,
    contrato_id               BIGINT,
    valor                     NUMERIC(15,2),
    prazo                     TEXT,
    valor_parcela             NUMERIC(15,2),
    tipo_operacao             TEXT,
    data_cadastro             DATE,
    status_banco              TEXT,
    data_status_banco         DATE,
    status_pagamento_cliente  TEXT,
    data_status_pagamento     DATE,
    banco                     TEXT,
    convenio                  TEXT,
    num_proposta              TEXT,
    sub_status_banco          TEXT,
    loja                      TEXT,
    regiao                    TEXT,
    consultor                 TEXT,
    produto                   TEXT,
    tipo_produto              TEXT,
    subtipo                   TEXT,
    categoria_codigo          TEXT,
    grupo_dashboard           TEXT,
    conta_valor               BOOLEAN,
    classificacao             TEXT,
    recuperada_outro          BOOLEAN,
    recuperada_outra_loja     BOOLEAN,
    recuperada_outra_regiao   BOOLEAN,
    regiao_atual              TEXT
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
SET statement_timeout = '15000'
AS $$
DECLARE
    v_data_ref    DATE;
    v_data_inicio DATE;
    v_hoje        DATE := current_date;
BEGIN
    -- Data de referencia: hoje se periodo vigente,
    -- senao ultimo dia do mes selecionado (igual a RPC 003).
    IF p_mes = EXTRACT(MONTH FROM v_hoje)::INTEGER
       AND p_ano = EXTRACT(YEAR FROM v_hoje)::INTEGER
    THEN
        v_data_ref := v_hoje;
    ELSE
        v_data_ref := (make_date(p_ano, p_mes, 1)
                       + INTERVAL '1 month'
                       - INTERVAL '1 day')::DATE;
    END IF;

    v_data_inicio := v_data_ref - INTERVAL '30 days';

    RETURN QUERY
    WITH canc AS (
        -- Cancelados da janela; regiao/regiao_atual da view (051 =
        -- regiao ATUAL). nome normalizado (cliente_norm) p/ o matching.
        SELECT
            v.id, v.contrato_id, v.valor, v.prazo, v.valor_parcela,
            v.tipo_operacao, v.data_cadastro, v.status_banco,
            v.data_status_banco, v.status_pagamento_cliente,
            v.data_status_pagamento, v.banco, v.convenio, v.num_proposta,
            v.sub_status_banco, v.loja, v.regiao, v.regiao_atual,
            v.consultor, v.produto, v.tipo_produto, v.subtipo,
            v.categoria_codigo, v.grupo_dashboard, v.conta_valor,
            c.cliente_norm AS nome_norm
        FROM public.v_contratos_cancelados v
        JOIN public.contratos c ON c.id = v.id
        WHERE v.data_cadastro >= v_data_inicio
          AND v.data_cadastro <= v_data_ref
    ),
    -- 149: MATERIALIZED de proposito. Inlinado, o planner (sem
    -- estatistica de `canc`) escolhia nested loop com um range scan
    -- de pagos POR cancelado. Materializado, o matching e hash join.
    -- Nao remover sem medir (ver cabecalho).
    paga AS MATERIALIZED (
        -- Propostas pagas (mesmo nome+categoria) usadas para detectar
        -- recuperacao. regiao = regiao ATUAL da loja (lojas.regiao_id),
        -- mesmo eixo do cancelado (view 051), p/ o comparativo de
        -- "outra regiao" ficar coerente. Filtro de data limita o scan.
        SELECT
            c.cliente_norm AS nome_norm,
            cp.codigo AS categoria_codigo,
            con.nome  AS consultor,
            l.nome    AS loja,
            r.nome    AS regiao,
            c.data_cadastro
        FROM public.contratos c
        JOIN public.produtos p            ON p.id  = c.produto_id
        JOIN public.categorias_produto cp ON cp.id = p.categoria_id
        LEFT JOIN public.consultores con  ON con.id = c.consultor_id
        LEFT JOIN public.lojas l          ON l.id  = c.loja_id
        LEFT JOIN public.regioes r        ON r.id  = l.regiao_id
        WHERE c.status_pagamento_cliente = 'PAGO AO CLIENTE'
          AND c.data_cadastro >= v_data_inicio
          AND c.data_cadastro <= v_data_ref + INTERVAL '7 days'
    ),
    redig AS (
        -- Superada por cancelamento posterior em <=7d (self-join
        -- sobre canc). LEFT JOIN agregado set-based (036). Guarda de
        -- nome vazio na juncao; desigualdade ESTRITA `>`.
        SELECT
            a.id,
            (a.nome_norm <> '' AND bool_or(b.id IS NOT NULL)) AS is_redig
        FROM canc a
        LEFT JOIN canc b
          ON a.nome_norm <> ''
         AND b.nome_norm        = a.nome_norm
         AND b.categoria_codigo = a.categoria_codigo
         AND b.data_cadastro    > a.data_cadastro
         AND b.data_cadastro   <= a.data_cadastro + INTERVAL '7 days'
        GROUP BY a.id, a.nome_norm
    ),
    matches AS (
        -- Uma unica passagem pela janela de pagas por cancelado:
        -- todas as flags de recuperacao derivam deste JOIN agregado.
        SELECT
            a.id,
            bool_or(g.consultor IS NOT DISTINCT FROM a.consultor)
                AS paga_propria,
            bool_or(g.consultor IS DISTINCT FROM a.consultor)
                AS paga_outro,
            bool_or(g.loja IS NOT DISTINCT FROM a.loja)
                AS paga_mesma_loja,
            bool_or(g.loja IS DISTINCT FROM a.loja)
                AS paga_outra_loja,
            bool_or(g.regiao IS NOT DISTINCT FROM a.regiao)
                AS paga_mesma_regiao,
            bool_or(g.regiao IS DISTINCT FROM a.regiao)
                AS paga_outra_regiao
        FROM canc a
        JOIN paga g
          ON g.nome_norm        = a.nome_norm
         AND g.categoria_codigo = a.categoria_codigo
         AND g.data_cadastro   >= a.data_cadastro
         AND g.data_cadastro   <= a.data_cadastro + INTERVAL '7 days'
        WHERE a.nome_norm <> ''
        GROUP BY a.id
    )
    SELECT
        f.id, f.contrato_id, f.valor, f.prazo, f.valor_parcela,
        f.tipo_operacao, f.data_cadastro, f.status_banco,
        f.data_status_banco, f.status_pagamento_cliente,
        f.data_status_pagamento, f.banco, f.convenio, f.num_proposta,
        f.sub_status_banco, f.loja, f.regiao, f.consultor, f.produto,
        f.tipo_produto, f.subtipo, f.categoria_codigo, f.grupo_dashboard,
        f.conta_valor,
        CASE
            WHEN rd.is_redig THEN 'redigitada'
            WHEN COALESCE(m.paga_propria, false)
              OR COALESCE(m.paga_outro, false) THEN 'recuperada'
            ELSE 'liquido'
        END AS classificacao,
        -- Oportunidade perdida por nivel: representante (nao
        -- redigitada) que NAO foi recuperado no proprio nivel, mas
        -- foi pago em OUTRO consultor / OUTRA loja / OUTRA regiao.
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_propria, false)
            AND COALESCE(m.paga_outro, false))
            AS recuperada_outro,
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_mesma_loja, false)
            AND COALESCE(m.paga_outra_loja, false))
            AS recuperada_outra_loja,
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_mesma_regiao, false)
            AND COALESCE(m.paga_outra_regiao, false))
            AS recuperada_outra_regiao,
        f.regiao_atual
    FROM canc f
    JOIN redig rd        ON rd.id = f.id
    LEFT JOIN matches m  ON m.id  = f.id;
END;
$$;

COMMENT ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER) IS
    'Cancelados dos ultimos 30 dias classificados em '
    'redigitada / recuperada / liquido (matching por nome+categoria '
    'em janela de 7 dias). Marca oportunidade perdida por nivel: '
    'recuperada_outro / recuperada_outra_loja / recuperada_outra_regiao. '
    'regiao = regiao ATUAL da loja (mesmo eixo no cancelado e na paga, '
    'p/ o comparativo de outra-regiao ser coerente); regiao_atual '
    'identica, usada pelo RLS client-side. Migration 149 (base 052): '
    'CTE paga MATERIALIZED para o matching ser hash join.';

-- Acesso de execucao para os papeis do app (preserva GRANT da 039/047/052).
GRANT EXECUTE ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER)
    TO anon, authenticated;


-- ===========================================
-- Validacao pos-migracao
-- ===========================================
-- 1) O `paga` aparece como CTE materializado no plano:
--
--   SELECT pg_get_functiondef(
--     'public.obter_cancelados_classificados(integer,integer)'::regprocedure)
--     LIKE '%paga AS MATERIALIZED%';
--   -- Esperado: t
--
-- 2) Paridade: rode ANTES de aplicar e guarde; rode DEPOIS e compare.
--    O mes corrente muda com a carga do dia — compare na mesma hora.
--
--   SELECT m, count(*) AS linhas,
--          md5(string_agg(t::text, '|' ORDER BY t.id)) AS hash
--   FROM generate_series(6, 11) m,
--        LATERAL obter_cancelados_classificados(m, 2026) t
--   GROUP BY m ORDER BY m;
--   -- Esperado: mesmas linhas e mesmo hash por mes.
--
-- 3) Tempo: acompanhar a media do wrapper por alguns dias.
--
--   SELECT calls, round(mean_exec_time::numeric) AS media_ms,
--          round(max_exec_time::numeric) AS max_ms
--   FROM extensions.pg_stat_statements
--   WHERE query LIKE '%obter_cancelados_classificados_json%';
--   -- Esperado: media na casa das dezenas/centenas de ms (era ~2,7 s).
-- ===========================================


-- ===========================================
-- Reversao: reaplicar o corpo da 052 (identico, sem MATERIALIZED).
-- ===========================================
