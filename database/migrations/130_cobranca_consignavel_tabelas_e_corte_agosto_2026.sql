-- =====================================================
-- Migracao 130: Cobranca Consignavel — criterio misto
--               (tabelas do banco + VLR BRUTO) e corte
--               em 08/2026
--
-- Contexto: ate aqui (067) a Cobranca Consignavel era
-- reconhecida por um SINAL de valor: Contrato Novo / NOVO /
-- CONSIG_BMG / BMG com VLR BRUTO <> VLR BASE. Em 05/10/2026
-- o banco criou tabelas proprias para a modalidade:
--   COBRANCA CONSIGNAVEL - NOVO  - Digital Token - Nao
--   COBRANCA CONSIGNAVEL - REFIN - Digital Token - Nao
-- e passou a lancar tambem REFIN como Cobranca Consignavel.
--
-- DECISOES DO USUARIO (06/10/2026):
--   1) CRITERIO MISTO. Antes de 05/10 houve propostas de
--      Cobranca Consignavel em tabelas normais (INSS...),
--      reconhecidas so pelo sinal de valor. O sinal continua
--      valendo E, alem dele, conta toda proposta das tabelas
--      novas (NOVO e REFIN):
--        is_cobranca_consignavel = por_valor OR por_tabela
--   2) PRODUCAO DO REFIN = VLR BASE. No refin o VLR BRUTO
--      inclui o saldo quitado do contrato anterior (ex.:
--      3011868, base 4.075,96 x bruto 47.130,79) — o refin
--      conta no CONTADOR, nao no valor. O uplift para VLR
--      BRUTO (valor_consolidado) continua restrito ao sinal de
--      valor, que por construcao so pega subtipo NOVO.
--      Nas tabelas novas o NOVO chega com bruto = base, entao
--      nao ha uplift a perder.
--   3) CORTE EM 08/2026 no sinal de valor. A carga retroativa
--      de 09/2025 (feita em 05/10/2026) foi o primeiro mes
--      antigo a trazer VLR BRUTO, e o sinal marcou 233
--      contratos de um mes em que a modalidade nao existia:
--      +R$ 181.821,56 de producao (e pontuacao) em 09/2025.
--      A modalidade vigora desde 08/2026 (primeiro caso em
--      03/08/2026); antes disso o sinal nao vale.
--
-- RECONHECIMENTO DA TABELA POR NOME (p.tabela), normalizado e
-- com `_` no lugar de Ç/A acentuado para nao depender da
-- grafia exata. Escolhido em vez de uma coluna nova em
-- `produtos` para nao criar estrutura; se o banco criar uma
-- tabela da modalidade com outro nome, a regra e CREATE OR
-- REPLACE de fn_eh_tabela_cobranca_consignavel.
--
-- fn_eh_cobranca_consignavel (067) NAO muda: vira o nucleo do
-- sinal de valor, chamado por fn_eh_cobranca_consignavel_por_valor.
-- Todas as funcoes seguem o padrao da 067: SQL, IMMUTABLE,
-- PARALLEL SAFE, sem SET search_path (inlining).
--
-- Base da view: migration 067, identica exceto pelas duas
-- colunas de Cobranca Consignavel. Nenhuma coluna muda de
-- nome, tipo ou ordem. O WHERE fica igual ao da 067: estorno
-- pos-pagamento (CANCELADO entre os pagos) segue contando
-- como pago de proposito, como sinal para investigacao
-- humana (decisao do usuario, 06/10/2026).
--
-- Executar no Supabase SQL Editor. Requer 067 aplicada.
-- =====================================================


-- ===========================================
-- 0. Pre-condicao: migration 067 aplicada
--    (fn_eh_cobranca_consignavel e o nucleo do sinal de valor)
-- ===========================================

DO $$
BEGIN
    IF to_regprocedure(
        'public.fn_eh_cobranca_consignavel(text, text, text, text, numeric, numeric)') IS NULL
    THEN
        RAISE EXCEPTION
            'Migration 067 nao aplicada (fn_eh_cobranca_consignavel ausente). '
            'Aplique 067_valor_consolidado_cobranca_consignavel.sql antes desta.';
    END IF;
END
$$;


-- ===========================================
-- 1. fn_eh_cobranca_consignavel_por_valor
--    Sinal de valor da 067 + corte temporal (pagamento a
--    partir de 01/08/2026). E o UNICO criterio que move o
--    valor de producao para o VLR BRUTO.
--    data de pagamento NULL => FALSE.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_eh_cobranca_consignavel_por_valor(
    p_tipo_operacao         TEXT,
    p_subtipo               TEXT,
    p_categoria_codigo      TEXT,
    p_banco                 TEXT,
    p_valor                 NUMERIC,
    p_valor_bruto           NUMERIC,
    p_data_status_pagamento DATE
)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT COALESCE(
        p_data_status_pagamento >= DATE '2026-08-01'
        AND public.fn_eh_cobranca_consignavel(
                p_tipo_operacao, p_subtipo, p_categoria_codigo,
                p_banco, p_valor, p_valor_bruto),
        false
    );
$$;

COMMENT ON FUNCTION public.fn_eh_cobranca_consignavel_por_valor(
    TEXT, TEXT, TEXT, TEXT, NUMERIC, NUMERIC, DATE) IS
    'Sinal de valor da Cobranca Consignavel: fn_eh_cobranca_consignavel '
    '(Contrato Novo / NOVO / CONSIG_BMG / BMG com VLR BRUTO <> VLR BASE) '
    'com pagamento a partir de 01/08/2026 (inicio da modalidade; antes '
    'disso o sinal marcava falsos positivos na carga retroativa de '
    '09/2025). Unico criterio que leva valor_consolidado ao VLR BRUTO. '
    'Nunca NULL.';


-- ===========================================
-- 2. fn_eh_tabela_cobranca_consignavel
--    Tabela do banco dedicada a modalidade (NOVO ou REFIN).
--    Conta no CONTADOR; nao mexe no valor de producao.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_eh_tabela_cobranca_consignavel(
    p_tabela TEXT
)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $$
    -- `_` casa Ç/C e A/Á: a grafia do banco ja variou entre cargas.
    SELECT pg_catalog.upper(pg_catalog.btrim(COALESCE(p_tabela, '')))
           LIKE 'COBRAN_A CONSIGN_VEL%';
$$;

COMMENT ON FUNCTION public.fn_eh_tabela_cobranca_consignavel(TEXT) IS
    'TRUE quando a tabela (produtos.tabela) e uma das tabelas que o '
    'banco criou em 10/2026 para apurar Cobranca Consignavel '
    '("COBRANCA CONSIGNAVEL - NOVO/REFIN - ..."). Proposta dessas '
    'tabelas conta como Cobranca Consignavel (NOVO e REFIN), mas a '
    'producao segue no VLR BASE. Nunca NULL.';


-- ===========================================
-- 3. v_contratos_dashboard
--    Base: migration 067. Mudam so as expressoes de
--    is_cobranca_consignavel e valor_consolidado. WHERE
--    identico ao da 067.
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
    r_atual.nome  AS regiao_atual,   -- organograma atual (RLS)
    COALESCE(c.valor_bruto,   c.valor) AS valor_bruto,
    COALESCE(c.valor_liquido, c.valor) AS valor_liquido,
    -- 130: criterio misto — sinal de valor (>= 08/2026) OU tabela
    -- dedicada do banco.
    (public.fn_eh_cobranca_consignavel_por_valor(
         c.tipo_operacao, p.subtipo, cp.codigo, c.banco,
         c.valor, c.valor_bruto, c.data_status_pagamento)
     OR public.fn_eh_tabela_cobranca_consignavel(p.tabela)
    ) AS is_cobranca_consignavel,
    -- 130: uplift SO pelo sinal de valor. Tabela dedicada (inclusive
    -- REFIN) produz no VLR BASE.
    (CASE
        WHEN public.fn_eh_cobranca_consignavel_por_valor(
                c.tipo_operacao, p.subtipo, cp.codigo, c.banco,
                c.valor, c.valor_bruto, c.data_status_pagamento)
        THEN GREATEST(COALESCE(c.valor_bruto, c.valor), c.valor)
        ELSE c.valor
     END)::NUMERIC(15,2) AS valor_consolidado
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN periodos per         ON per.id = c.periodo_id
LEFT JOIN LATERAL (
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
    '(organograma), usada pelo RLS client-side. Inclui created_at. '
    'valor_bruto/valor_liquido (065) = colunas homonimas de '
    'contratos com fallback para `valor` (VLR BASE). '
    'is_cobranca_consignavel (130) = sinal de valor >= 08/2026 OU '
    'tabela dedicada do banco; valor_consolidado = VLR BRUTO so pelo '
    'sinal de valor, VLR BASE no resto. Nenhuma das quatro e NULL.';

COMMENT ON COLUMN v_contratos_dashboard.is_cobranca_consignavel IS
    'TRUE quando a linha e Cobranca Consignavel: '
    'fn_eh_cobranca_consignavel_por_valor (Contrato Novo BMG com VLR '
    'BRUTO <> VLR BASE, pago >= 08/2026) OU '
    'fn_eh_tabela_cobranca_consignavel (tabelas COBRANCA CONSIGNAVEL - '
    'NOVO/REFIN do banco). Nao reimplementar no consumidor. Nunca NULL.';

COMMENT ON COLUMN v_contratos_dashboard.valor_consolidado IS
    'Valor que o dashboard considera como PRODUCAO da linha: '
    'GREATEST(valor_bruto, valor) quando '
    'fn_eh_cobranca_consignavel_por_valor; `valor` (VLR BASE) em todo o '
    'resto — inclusive Cobranca Consignavel reconhecida so pela tabela '
    '(REFIN produz no VLR BASE). NUNCA reduz. Nunca NULL. O loader '
    'mapeia esta coluna para VALOR e `valor` para VALOR_BASE.';


-- ===========================================
-- 4. Validacao pos-migracao
-- ===========================================
-- 1) Bordas das funcoes:
--
--   SELECT fn_eh_cobranca_consignavel_por_valor('Contrato Novo','NOVO','CONSIG_BMG','BMG',100,120,'2026-08-01') AS deve_true,
--          fn_eh_cobranca_consignavel_por_valor('Contrato Novo','NOVO','CONSIG_BMG','BMG',100,120,'2026-07-31') AS deve_false_antes_corte,
--          fn_eh_cobranca_consignavel_por_valor('Contrato Novo','NOVO','CONSIG_BMG','BMG',100,120,NULL)         AS deve_false_sem_data,
--          fn_eh_cobranca_consignavel_por_valor('Refinanciamento','REFIN','CONSIG_BMG','BMG',100,900,'2026-10-05') AS deve_false_refin,
--          fn_eh_tabela_cobranca_consignavel('COBRANÇA CONSIGNAVEL - REFIN - Digital Token - Não') AS deve_true_tab_refin,
--          fn_eh_tabela_cobranca_consignavel(' cobranca consignável - novo ')                    AS deve_true_tab_grafia,
--          fn_eh_tabela_cobranca_consignavel('INSS NORMAL DIGITAL TOKEN - Digital Token - Não')  AS deve_false_tab_normal,
--          fn_eh_tabela_cobranca_consignavel(NULL)                                               AS deve_false_tab_null;
--   -- Esperado: t, f, f, f, t, t, f, f
--
--   SELECT proname, provolatile, proparallel, proconfig
--   FROM pg_proc
--   WHERE proname IN ('fn_eh_cobranca_consignavel_por_valor',
--                     'fn_eh_tabela_cobranca_consignavel');
--   -- Esperado: i, s, proconfig NULL nas duas
--
-- 2) Tabelas reconhecidas — so as duas do banco:
--
--   SELECT tabela FROM produtos
--   WHERE fn_eh_tabela_cobranca_consignavel(tabela);
--   -- Esperado em 06/10/2026: COBRANCA CONSIGNAVEL - NOVO / - REFIN
--
-- 3) GATE — impacto por mes (medido inline em 06/10/2026, antes de
--    aplicar):
--
--   SELECT to_char(date_trunc('month', data_status_pagamento),'YYYY-MM') AS mes,
--          count(*) FILTER (WHERE is_cobranca_consignavel) AS qtd,
--          sum(valor_consolidado - valor)                  AS uplift
--   FROM v_contratos_dashboard
--   WHERE data_status_pagamento >= '2025-09-01'
--   GROUP BY 1 HAVING count(*) FILTER (WHERE is_cobranca_consignavel) > 0
--                  OR sum(valor_consolidado - valor) > 0
--   ORDER BY 1;
--   -- Esperado:
--   --   2025-09: nao aparece (era 233 / 181.821,56)
--   --   2026-08: 2  / 15.429,70  (inalterado)
--   --   2026-09: 14 / 24.146,69  (inalterado)
--   --   2026-10: 19 / 10.273,28  (era 3; +16 das tabelas novas,
--   --            uplift inalterado). Cresce com as cargas do mes.
--
-- 4) REFIN da tabela nova produz no VLR BASE:
--
--   SELECT count(*) FROM v_contratos_dashboard
--   WHERE fn_eh_tabela_cobranca_consignavel(produto)
--     AND upper(btrim(subtipo)) = 'REFIN'
--     AND valor_consolidado <> valor;
--   -- Esperado SEMPRE: 0
--
-- 5) Invariante "nunca reduz":
--
--   SELECT count(*) FROM v_contratos_dashboard WHERE valor_consolidado < valor;
--   -- Esperado SEMPRE: 0
--
-- 6) 09/2025 de volta ao VLR BASE:
--
--   SELECT sum(valor_consolidado) - sum(valor) FROM v_contratos_dashboard
--   WHERE data_status_pagamento BETWEEN '2025-09-01' AND '2025-09-30';
--   -- Esperado: 0
