-- =====================================================
-- Migracao 051: alinha a ancora temporal da regiao ao eixo de cada view
--
-- Contexto (correcao do descasamento observado em "Onde Agir Agora ->
-- Regioes" apos o remanejamento H2/2026):
--
-- A 044 resolvia `regiao` point-in-time SEMPRE por data_cadastro (venda)
-- nas 3 views. Mas cada view e consumida com um eixo temporal diferente:
--
--   * v_contratos_dashboard (PAGOS) e bucketizada por periodo_id
--     (periodo de PAGAMENTO) no loader, e as metas (RPC 045) resolvem
--     regiao pela COMPETENCIA do periodo. Ancorar o realizado por
--     data_cadastro fazia um contrato vendido em junho e pago em julho
--     cair na regiao ANTIGA dentro da visao de julho -> a loja aparecia
--     "partida" entre duas regioes e o realizado nao batia com a meta
--     (que ja e por competencia). CORRECAO: resolver a regiao dos pagos
--     pela competencia do periodo de pagamento (mesmo eixo das metas).
--     Sem periodo (ex.: seguro liquidado sem periodo_id) -> cai em
--     data_cadastro (COALESCE).
--
--   * v_contratos_em_analise (PIPELINE, sem periodo de pagamento ainda)
--     e v_contratos_cancelados: reportam pela regiao ATUAL da loja —
--     onde o contrato sera/seria creditado. CORRECAO: `regiao` passa a
--     ser a regiao corrente (organograma), igual a `regiao_atual`.
--
-- Decisao de negocio (2026-07-03): produção do periodo credita a regiao
-- dona da loja NO PERIODO DE PAGAMENTO; pipeline/cancelados creditam a
-- regiao ATUAL. O recorte RLS do gerente segue por `regiao_atual`
-- (inalterado). Nada muda para periodos <= jun/2026 (competencia = era
-- da regiao) nem antes do remanejamento (linha de vigencia unica).
--
-- CREATE OR REPLACE VIEW: mantem nome/tipo/ordem das colunas; so muda a
-- expressao por tras de `regiao`. Migration 044 e imutavel; esta a
-- substitui de forma versionada, preservando security_invoker.
--
-- Executar no Supabase SQL Editor. Requer 043-044 aplicadas.
-- =====================================================


-- ===========================================
-- 1. v_contratos_dashboard (PAGOS): regiao por competencia do periodo
--    de pagamento (COALESCE -> data_cadastro quando sem periodo).
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
    r.nome        AS regiao,        -- vigente na COMPETENCIA do pagamento
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.grupo_meta,
    cp.conta_valor,
    cp.conta_pontuacao,
    c.created_at,
    r_atual.nome  AS regiao_atual   -- organograma atual (RLS) — ultima coluna
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN periodos per         ON per.id = c.periodo_id
LEFT JOIN LATERAL (
    -- Ancora = 1o dia da competencia do periodo de pagamento; sem
    -- periodo, cai em data_cadastro (mantem o comportamento anterior
    -- para seguros liquidados sem periodo_id).
    SELECT vig.regiao_id
    FROM loja_regiao_vigencia vig
    WHERE vig.loja_id = c.loja_id
      AND COALESCE(make_date(per.ano, per.mes, 1), c.data_cadastro)
              >= vig.vigencia_inicio
      AND (vig.vigencia_fim IS NULL
           OR COALESCE(make_date(per.ano, per.mes, 1), c.data_cadastro)
              < vig.vigencia_fim)
    ORDER BY vig.vigencia_inicio DESC
    LIMIT 1
) rv ON true
LEFT JOIN regioes r            ON r.id  = COALESCE(rv.regiao_id, l.regiao_id)
LEFT JOIN regioes r_atual      ON r_atual.id = l.regiao_id
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
    'Contratos pagos + seguros liquidados. regiao = vigente na '
    'COMPETENCIA do periodo de pagamento (via loja_regiao_vigencia; '
    'COALESCE p/ data_cadastro quando sem periodo), casando com as '
    'metas (RPC 045). regiao_atual = regiao corrente da loja '
    '(organograma), usada pelo RLS client-side. Inclui created_at.';


-- ===========================================
-- 2. v_contratos_em_analise (PIPELINE): regiao = regiao ATUAL da loja.
--    Sem periodo de pagamento ainda -> credita o dono atual.
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
    r_atual.nome  AS regiao,        -- regiao ATUAL (pipeline credita o dono atual)
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.conta_valor,
    r_atual.nome  AS regiao_atual   -- organograma atual (RLS) — ultima coluna
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN regioes r_atual      ON r_atual.id = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_pagamento_cliente != 'PAGO AO CLIENTE'
    AND c.status_banco         != 'CANCELADO'
    AND (c.sub_status_banco IS NULL
         OR c.sub_status_banco != 'Liquidada');

ALTER VIEW public.v_contratos_em_analise
    SET (security_invoker = on);

COMMENT ON VIEW v_contratos_em_analise IS
    'Pipeline de contratos em analise. regiao = regiao ATUAL da loja '
    '(o pipeline credita o dono atual quando pagar); regiao_atual '
    '(identica) usada pelo RLS client-side. Exclui pagos, cancelados '
    'e seguros liquidados.';


-- ===========================================
-- 3. v_contratos_cancelados: regiao = regiao ATUAL da loja.
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
    r_atual.nome  AS regiao,        -- regiao ATUAL da loja
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.conta_valor,
    r_atual.nome  AS regiao_atual   -- organograma atual (RLS) — ultima coluna
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN regioes r_atual      ON r_atual.id = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_banco = 'CANCELADO';

ALTER VIEW public.v_contratos_cancelados
    SET (security_invoker = on);

COMMENT ON VIEW v_contratos_cancelados IS
    'Contratos cancelados (status_banco = CANCELADO). regiao = regiao '
    'ATUAL da loja (onde a recuperacao seria creditada); regiao_atual '
    '(identica) usada pelo RLS client-side.';
