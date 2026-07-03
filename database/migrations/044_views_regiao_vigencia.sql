-- =====================================================
-- Migracao 044: views resolvem regiao point-in-time (vigencia)
--               e expoem regiao_atual
--
-- Estagio 2 do rollout. Reescreve as 3 views flat de contratos
-- para que a coluna `regiao` passe a ser a regiao VIGENTE no
-- momento da venda (data_cadastro), resolvida via
-- loja_regiao_vigencia (migration 043), em vez de sempre a regiao
-- ATUAL da loja. Adiciona a coluna `regiao_atual` (regiao corrente
-- da loja), usada pelo recorte RLS client-side do gerente
-- ("lojas que sao dele hoje"), desacoplando relatorio x acesso.
--
-- Por que data_cadastro (e nao periodo_id):
--   periodo_id e o periodo de PAGAMENTO (NULL p/ nao pagos). A
--   venda ocorre na DIGITACAO (data_cadastro) — esse e o ancoro
--   point-in-time correto e uniforme p/ todas as views (pagos,
--   em analise, cancelados).
--
-- No-op ate o 1o remanejamento: enquanto cada loja tem UMA linha
-- de vigencia aberta desde 2020-01-01 (backfill da 043), a
-- resolucao por vigencia devolve a mesma regiao atual — comportamento
-- identico ao de hoje. COALESCE(vigencia, l.regiao_id) garante que
-- contratos sem data_cadastro / loja sem vigencia caem na regiao
-- atual (nunca viram NULL onde antes nao eram).
--
-- LEFT JOIN LATERAL ... LIMIT 1: blinda contra multiplicacao de
-- linhas caso existam vigencias sobrepostas (dado ruim); pega a
-- vigencia mais recente que cobre a data.
--
-- IMPORTANTE (CREATE OR REPLACE VIEW): o Postgres so permite ADICIONAR
-- colunas no FINAL da lista, mantendo nome/tipo/ordem das existentes.
-- Por isso `regiao_atual` entra como ULTIMA coluna de cada view (nao
-- ao lado de `regiao`). Migrations 001/003/017 sao imutaveis; esta as
-- substitui de forma versionada, preservando security_invoker.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. v_contratos_dashboard (pagos + seguros liquidados)
--    Base: migration 017 (+ created_at). regiao_atual entra ao final.
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
    r.nome        AS regiao,        -- vigente na venda (data_cadastro)
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
    r_atual.nome  AS regiao_atual   -- organograma atual (RLS) — coluna nova, ao final
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN LATERAL (
    SELECT vig.regiao_id
    FROM loja_regiao_vigencia vig
    WHERE vig.loja_id = c.loja_id
      AND c.data_cadastro >= vig.vigencia_inicio
      AND (vig.vigencia_fim IS NULL OR c.data_cadastro < vig.vigencia_fim)
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
    'venda (data_cadastro, via loja_regiao_vigencia); regiao_atual '
    '= regiao corrente da loja (organograma), usada pelo RLS '
    'client-side. Inclui created_at do contrato ("Atualizado em").';


-- ===========================================
-- 2. v_contratos_em_analise (pipeline)
--    Base: migration 001. regiao_atual entra ao final.
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
    r.nome        AS regiao,        -- vigente na venda (data_cadastro)
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.conta_valor,
    r_atual.nome  AS regiao_atual   -- organograma atual (RLS) — coluna nova, ao final
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN LATERAL (
    SELECT vig.regiao_id
    FROM loja_regiao_vigencia vig
    WHERE vig.loja_id = c.loja_id
      AND c.data_cadastro >= vig.vigencia_inicio
      AND (vig.vigencia_fim IS NULL OR c.data_cadastro < vig.vigencia_fim)
    ORDER BY vig.vigencia_inicio DESC
    LIMIT 1
) rv ON true
LEFT JOIN regioes r            ON r.id  = COALESCE(rv.regiao_id, l.regiao_id)
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
    'Pipeline de contratos em analise. regiao = vigente na venda '
    '(data_cadastro, via loja_regiao_vigencia); regiao_atual = '
    'regiao corrente da loja (RLS client-side). Exclui pagos, '
    'cancelados e seguros liquidados.';


-- ===========================================
-- 3. v_contratos_cancelados
--    Base: migration 003. regiao_atual entra ao final.
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
    r.nome        AS regiao,        -- vigente na venda (data_cadastro)
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.conta_valor,
    r_atual.nome  AS regiao_atual   -- organograma atual (RLS) — coluna nova, ao final
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN LATERAL (
    SELECT vig.regiao_id
    FROM loja_regiao_vigencia vig
    WHERE vig.loja_id = c.loja_id
      AND c.data_cadastro >= vig.vigencia_inicio
      AND (vig.vigencia_fim IS NULL OR c.data_cadastro < vig.vigencia_fim)
    ORDER BY vig.vigencia_inicio DESC
    LIMIT 1
) rv ON true
LEFT JOIN regioes r            ON r.id  = COALESCE(rv.regiao_id, l.regiao_id)
LEFT JOIN regioes r_atual      ON r_atual.id = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_banco = 'CANCELADO';

ALTER VIEW public.v_contratos_cancelados
    SET (security_invoker = on);

COMMENT ON VIEW v_contratos_cancelados IS
    'Contratos cancelados (status_banco = CANCELADO). regiao = '
    'vigente na venda (data_cadastro, via loja_regiao_vigencia); '
    'regiao_atual = regiao corrente da loja (RLS client-side).';
