-- =====================================================
-- Migracao 017: Expor created_at em v_contratos_dashboard
--
-- O dashboard precisa exibir a data da ultima insercao
-- de contratos (rotulo "Atualizado em"), separada da
-- data de competencia dos pagamentos ("Dados em").
--
-- CREATE OR REPLACE preserva a opcao security_invoker
-- definida na migracao 004; ainda assim a re-aplicamos
-- ao final como salvaguarda.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

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
    cp.conta_pontuacao,
    c.created_at
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN regioes r            ON r.id  = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_pagamento_cliente = 'PAGO AO CLIENTE'
    OR
    (c.sub_status_banco = 'Liquidada'
     AND c.tipo_operacao IN ('BMG MED', 'Seguro'));

ALTER VIEW public.v_contratos_dashboard
    SET (security_invoker = on);

COMMENT ON VIEW v_contratos_dashboard IS
    'Contratos pagos + seguros liquidados, com joins '
    'resolvidos (loja, regiao, consultor, produto, categoria). '
    'Inclui created_at do contrato (timestamp de insercao no '
    'Supabase), usado pelo dashboard para exibir "Atualizado em".';
