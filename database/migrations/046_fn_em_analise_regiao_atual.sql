-- =====================================================
-- Migracao 046: obter_contratos_em_analise expoe regiao_atual
--
-- Estagio 2b. A RPC apenas re-seleciona de v_contratos_em_analise
-- (janela de 30 dias). Com a migration 044 a view ja devolve
-- `regiao` point-in-time e a nova coluna `regiao_atual`; falta a RPC
-- repassa-la no RETURNS TABLE para o dashboard recortar o gerente
-- pelo organograma atual (RLS client-side).
--
-- Mudanca minima vs 001: acrescenta a coluna `regiao_atual` (ao final
-- do RETURNS TABLE e do SELECT). Como o tipo de retorno muda, e
-- preciso DROP + CREATE. Migration 001 e imutavel; esta a substitui.
--
-- No-op ate o 1o remanejamento (a view resolve para a regiao atual).
--
-- Executar no Supabase SQL Editor.
-- =====================================================

DROP FUNCTION IF EXISTS obter_contratos_em_analise(INTEGER, INTEGER);

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
    conta_valor               BOOLEAN,
    regiao_atual              TEXT
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
        v.conta_valor,
        v.regiao_atual
    FROM public.v_contratos_em_analise v
    WHERE v.data_cadastro >= v_data_inicio
      AND v.data_cadastro <= v_data_ref;
END;
$$;

COMMENT ON FUNCTION obter_contratos_em_analise(INTEGER, INTEGER) IS
    'Contratos em analise dos ultimos 30 dias relativos ao periodo. '
    'regiao = vigente na venda (point-in-time via view); regiao_atual '
    '= regiao corrente da loja (RLS client-side). Logica de datas no '
    'banco (antes calculada no Python).';
