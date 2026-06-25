-- =====================================================
-- Migracao 034: otimizacao de obter_cancelados_classificados
--
-- Problema: a versao da migration 033 dispara, para CADA linha
-- de cancelados, 7 subconsultas EXISTS correlacionadas sobre o
-- CTE `paga`. Como a chave de match e `nome_norm`
-- (upper(trim(regexp_replace(...)))), calculada em runtime,
-- nenhum indice e usavel — cada EXISTS faz scan. O custo e
-- 7 * |canc| * |paga| e estoura o statement_timeout do Supabase
-- (erro 57014: canceling statement due to statement timeout).
--
-- Correcao: substituir as 6 subconsultas EXISTS que olham `paga`
-- por UM unico JOIN `canc x paga` agregado com bool_or. Assim a
-- janela de match (nome+categoria, <=7 dias) e percorrida uma
-- unica vez por linha de cancelado, em vez de seis.
--
-- O 7o EXISTS (is_redig) e um self-join sobre `canc` — barato,
-- pois canc e pequeno (cancelados de 30 dias) — e fica isolado
-- no CTE `redig`.
--
-- Semantica IDENTICA a 033: mesmas colunas, mesma classificacao
-- e mesmas flags de oportunidade perdida. Apenas o plano de
-- execucao muda.
--
-- Como o tipo de retorno NAO muda, CREATE OR REPLACE basta.
--
-- Executar no Supabase SQL Editor.
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
    recuperada_outra_regiao   BOOLEAN
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
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
        -- Cancelados da janela; puxa o nome do base contratos
        -- apenas para o matching (nao sera retornado).
        SELECT
            v.id, v.contrato_id, v.valor, v.prazo, v.valor_parcela,
            v.tipo_operacao, v.data_cadastro, v.status_banco,
            v.data_status_banco, v.status_pagamento_cliente,
            v.data_status_pagamento, v.banco, v.convenio, v.num_proposta,
            v.sub_status_banco, v.loja, v.regiao, v.consultor, v.produto,
            v.tipo_produto, v.subtipo, v.categoria_codigo, v.grupo_dashboard,
            v.conta_valor,
            upper(trim(regexp_replace(
                coalesce(c.cliente, ''), '\s+', ' ', 'g'
            ))) AS nome_norm
        FROM public.v_contratos_cancelados v
        JOIN public.contratos c ON c.id = v.id
        WHERE v.data_cadastro >= v_data_inicio
          AND v.data_cadastro <= v_data_ref
    ),
    paga AS (
        -- Propostas pagas (mesmo nome+categoria) usadas para
        -- detectar recuperacao. Traz consultor/loja/regiao para
        -- distinguir recuperacao propria x por outro consultor,
        -- outra loja, outra regiao. Filtro de data limita o scan.
        SELECT
            upper(trim(regexp_replace(
                coalesce(c.cliente, ''), '\s+', ' ', 'g'
            ))) AS nome_norm,
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
        -- sobre canc — pequeno, mantido como EXISTS).
        SELECT
            a.id,
            (a.nome_norm <> '' AND EXISTS (
                SELECT 1 FROM canc b
                WHERE b.nome_norm = a.nome_norm
                  AND b.categoria_codigo = a.categoria_codigo
                  AND b.data_cadastro > a.data_cadastro
                  AND b.data_cadastro <= a.data_cadastro + INTERVAL '7 days'
            )) AS is_redig
        FROM canc a
    ),
    matches AS (
        -- Uma unica passagem pela janela de pagas por cancelado:
        -- todas as flags de recuperacao derivam deste JOIN agregado,
        -- substituindo as 6 subconsultas EXISTS da migration 033.
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
            AS recuperada_outra_regiao
    FROM canc f
    JOIN redig rd        ON rd.id = f.id
    LEFT JOIN matches m  ON m.id  = f.id;
END;
$$;

COMMENT ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER) IS
    'Cancelados dos ultimos 30 dias classificados em '
    'redigitada / recuperada / liquido (matching por nome+categoria '
    'em janela de 7 dias). Marca tambem oportunidade perdida por nivel: '
    'recuperada_outro / recuperada_outra_loja / recuperada_outra_regiao '
    '(venda capturada por outro consultor / loja / regiao). '
    'O nome do cliente nao e exposto: so as flags saem no resultado. '
    'Migration 034: flags derivadas de JOIN+bool_or unico (perf).';

-- Acesso de execucao para os papeis do app. O dashboard le em
-- escopo completo e filtra por perfil client-side (aplicar_rls);
-- a classificacao e global de proposito (detecta cross-nivel).
GRANT EXECUTE ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER)
    TO anon, authenticated;
