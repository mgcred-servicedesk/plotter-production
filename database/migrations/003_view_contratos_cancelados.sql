-- =====================================================
-- Migracao 003: View e RPC para contratos cancelados
--
-- Objetivo: permitir que o dashboard exiba analiticos
-- de contratos cancelados (status_banco = 'CANCELADO'),
-- seguindo o mesmo padrao das views existentes.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. v_contratos_cancelados
-- View flat de contratos cancelados com
-- todos os joins resolvidos no banco.
-- ===========================================

CREATE OR REPLACE VIEW v_contratos_cancelados AS
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
    cp.conta_valor
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN regioes r            ON r.id  = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_banco = 'CANCELADO';

COMMENT ON VIEW v_contratos_cancelados IS
    'Contratos cancelados (status_banco = CANCELADO), '
    'com joins resolvidos (loja, regiao, consultor, produto, '
    'categoria). Usado pelo dashboard na aba de analiticos.';


-- ===========================================
-- 2. RPC: obter_contratos_cancelados
-- Encapsula logica de datas (periodo do mes)
-- seguindo o mesmo padrao da RPC de em analise.
-- ===========================================

CREATE OR REPLACE FUNCTION obter_contratos_cancelados(
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
    v_data_ref    DATE;
    v_data_inicio DATE;
    v_hoje        DATE := current_date;
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
    FROM public.v_contratos_cancelados v
    WHERE v.data_cadastro >= v_data_inicio
      AND v.data_cadastro <= v_data_ref;
END;
$$;

COMMENT ON FUNCTION obter_contratos_cancelados(INTEGER, INTEGER) IS
    'Retorna contratos cancelados dos ultimos 30 dias '
    'relativos ao periodo informado. Logica de datas '
    'encapsulada no banco.';


-- ===========================================
-- 3. Indice para performance da view
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_contratos_status_banco_cancelado
    ON contratos (data_cadastro, status_banco)
    WHERE status_banco = 'CANCELADO';
