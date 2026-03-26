-- =====================================================
-- Migração 001: Views otimizadas para o dashboard
--
-- Objetivo: eliminar joins aninhados no PostgREST e
-- paginação manual no client. O dashboard consulta
-- views "flat" com uma única roundtrip ao banco.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. v_contratos_dashboard
-- View flat de contratos pagos + seguros liquidados
-- com todos os joins resolvidos no banco.
-- Substitui a query com joins aninhados do PostgREST.
-- ===========================================

CREATE OR REPLACE VIEW v_contratos_dashboard AS
SELECT
    c.id,
    c.contrato_id,
    c.valor,
    c.prazo,
    c.valor_parcela,
    c.tipo_operacao,
    c.data_cadastro,
    c.status_banco,
    c.data_status_banco,
    c.status_pagamento_cliente,
    c.data_status_pagamento,
    c.banco,
    c.convenio,
    c.num_proposta,
    c.sub_status_banco,
    c.periodo_id,
    l.nome        AS loja,
    r.nome        AS regiao,
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.grupo_meta,
    cp.conta_valor,
    cp.conta_pontuacao
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN regioes r            ON r.id  = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    -- Contratos pagos
    c.status_pagamento_cliente = 'PAGO AO CLIENTE'
    OR
    -- Seguros liquidados (BMG Med / Vida Familiar)
    (c.sub_status_banco = 'Liquidada'
     AND c.tipo_operacao IN ('BMG MED', 'Seguro'));

COMMENT ON VIEW v_contratos_dashboard IS
    'Contratos pagos + seguros liquidados, com joins '
    'resolvidos (loja, regiao, consultor, produto, categoria). '
    'Usado pelo dashboard em substituicao a query com joins '
    'aninhados do PostgREST. Elimina paginacao manual.';


-- ===========================================
-- 2. v_contratos_em_analise
-- View flat de contratos em análise (pipeline).
-- Mesmos joins, filtros de exclusão aplicados.
-- ===========================================

CREATE OR REPLACE VIEW v_contratos_em_analise AS
SELECT
    c.id,
    c.contrato_id,
    c.valor,
    c.prazo,
    c.valor_parcela,
    c.tipo_operacao,
    c.data_cadastro,
    c.status_banco,
    c.data_status_banco,
    c.status_pagamento_cliente,
    c.data_status_pagamento,
    c.banco,
    c.convenio,
    c.num_proposta,
    c.sub_status_banco,
    l.nome        AS loja,
    r.nome        AS regiao,
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.conta_valor
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN regioes r            ON r.id  = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_pagamento_cliente != 'PAGO AO CLIENTE'
    AND c.status_banco         != 'CANCELADO'
    AND (c.sub_status_banco IS NULL
         OR c.sub_status_banco != 'Liquidada');

COMMENT ON VIEW v_contratos_em_analise IS
    'Pipeline de contratos em analise. Exclui pagos, '
    'cancelados e seguros liquidados. Joins resolvidos '
    '(loja, regiao, consultor, produto, categoria).';


-- ===========================================
-- 3. RPC: obter_contratos_em_analise
-- Encapsula a lógica de datas (últimos 30 dias
-- a partir da referência do período) que antes
-- era calculada no Python.
-- ===========================================

CREATE OR REPLACE FUNCTION obter_contratos_em_analise(
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
    conta_valor               BOOLEAN
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
    v_data_ref   DATE;
    v_data_inicio DATE;
    v_hoje       DATE := current_date;
BEGIN
    -- Data de referencia: hoje se periodo vigente,
    -- senao ultimo dia do mes selecionado
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
    SELECT
        v.id,
        v.contrato_id,
        v.valor,
        v.prazo,
        v.valor_parcela,
        v.tipo_operacao,
        v.data_cadastro,
        v.status_banco,
        v.data_status_banco,
        v.status_pagamento_cliente,
        v.data_status_pagamento,
        v.banco,
        v.convenio,
        v.num_proposta,
        v.sub_status_banco,
        v.loja,
        v.regiao,
        v.consultor,
        v.produto,
        v.tipo_produto,
        v.subtipo,
        v.categoria_codigo,
        v.grupo_dashboard,
        v.conta_valor
    FROM public.v_contratos_em_analise v
    WHERE v.data_cadastro >= v_data_inicio
      AND v.data_cadastro <= v_data_ref;
END;
$$;

COMMENT ON FUNCTION obter_contratos_em_analise(INTEGER, INTEGER) IS
    'Retorna contratos em analise dos ultimos 30 dias '
    'relativos ao periodo informado. Logica de datas '
    'encapsulada no banco (antes era calculada no Python).';


-- ===========================================
-- 4. Índices para performance das views
-- ===========================================

-- Índice composto para a view de contratos pagos
-- (periodo_id + status_pagamento_cliente)
CREATE INDEX IF NOT EXISTS idx_contratos_periodo_status_pag
    ON contratos (periodo_id, status_pagamento_cliente);

-- Índice para a view de contratos em análise
-- (data_cadastro + status filtros)
CREATE INDEX IF NOT EXISTS idx_contratos_cadastro_status
    ON contratos (data_cadastro, status_pagamento_cliente, status_banco);

-- Índice para sub_status_banco (usado em ambas as views)
CREATE INDEX IF NOT EXISTS idx_contratos_sub_status
    ON contratos (sub_status_banco)
    WHERE sub_status_banco IS NOT NULL;

-- Índice para tipo_operacao (filtro de seguros)
CREATE INDEX IF NOT EXISTS idx_contratos_tipo_operacao
    ON contratos (tipo_operacao)
    WHERE tipo_operacao IN ('BMG MED', 'Seguro');
