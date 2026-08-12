-- =====================================================
-- Migracao 065: valor_bruto / valor_liquido em contratos
--               (+ exposicao com fallback em
--                v_contratos_dashboard)
--
-- Objetivo: habilitar o acelerador "Cobranca Consignavel"
-- (Reconquista + Cobranca Consignavel, vigente a partir de
-- 08/2026). O criterio de negocio compara VLR BRUTO x VLR BASE
-- do contrato — e hoje a tabela `contratos` so persiste
-- VLR BASE (coluna `valor`).
--
-- ORIGEM DOS DADOS (dependencia externa)
-- A planilha de contratos que o projeto irmao `angry-man`
-- importa TEM as colunas "VLR BRUTO", "VLR LIQUIDO" e
-- "VLR BASE", mas o HEADER_MAP de
-- `angry-man/src/services/import-contratos.ts` mapeia apenas
-- "VLR BASE" -> `valor`; as outras duas sao descartadas em
-- mapRow() antes do payload de upsert. Ou seja: as colunas
-- criadas aqui nascem NULL e continuam NULL ate que uma
-- mudanca NAQUELE repositorio (duas entradas novas no
-- HEADER_MAP + sanitizacao de moeda) passe a envia-las.
-- Essa mudanca esta FORA DO ESCOPO desta migration.
-- Nenhuma alteracao de RPC e necessaria la: fn_admin_import
-- detecta as colunas dinamicamente via information_schema.
--
-- POR QUE SEM DEFAULT DE BANCO
-- O default desejado seria "o proprio `valor` da linha", e o
-- Postgres nao permite DEFAULT referenciando outra coluna da
-- mesma linha. O fallback fica na VIEW (abaixo), nao na tabela.
--
-- FALLBACK NA VIEW (COALESCE)
-- v_contratos_dashboard expoe
--   COALESCE(c.valor_bruto,   c.valor) AS valor_bruto
--   COALESCE(c.valor_liquido, c.valor) AS valor_liquido
-- Mesmo espirito do fallback de `flag_elegibilidade` NULL =>
-- ELEGIVEL (migration 053): NULL cai no caso NEUTRO. Aqui o
-- caso neutro e "sem diferenca conhecida", entao qualquer
-- filtro `valor_bruto <> valor` feito por quem consome a view
-- devolve FALSE enquanto o dado real nao chegar — sem
-- tratamento de NULL no consumidor e sem gate/if especial no
-- loader. Como o import do `angry-man` e upsert por
-- contrato_id, no dia em que o valor real divergir a proxima
-- carga corrige sozinha, sem intervencao deste lado.
--
-- IMPORTANTE (CREATE OR REPLACE VIEW): o Postgres so permite
-- ADICIONAR colunas no FINAL da lista, preservando nome/tipo/
-- ordem das existentes. Por isso `valor_bruto`/`valor_liquido`
-- entram DEPOIS de `regiao_atual`, e nao ao lado de `valor`.
-- Mesma restricao ja documentada na migration 044.
--
-- Base da view: migration 051 (regiao dos pagos ancorada na
-- COMPETENCIA do periodo de pagamento). 001/017/044/051 sao
-- imutaveis; esta as substitui de forma versionada, preservando
-- security_invoker.
--
-- Impacto em consumidores: nenhum. O loader usa select
-- explicito de colunas (_COLS_CONTRATOS_PAGOS em
-- src/dashboard/loaders.py) — colunas novas so aparecem quando
-- forem adicionadas la.
--
-- Executar no Supabase SQL Editor. Requer 043-044-051 aplicadas.
-- =====================================================


-- ===========================================
-- 1. Colunas novas em contratos
-- ===========================================

ALTER TABLE public.contratos
    ADD COLUMN IF NOT EXISTS valor_bruto NUMERIC(15,2);

ALTER TABLE public.contratos
    ADD COLUMN IF NOT EXISTS valor_liquido NUMERIC(15,2);

COMMENT ON COLUMN public.contratos.valor_bruto IS
    'Valor BRUTO do contrato. Origem: coluna "VLR BRUTO" da '
    'planilha de contratos importada pelo projeto irmao '
    'angry-man. Hoje o HEADER_MAP de '
    'angry-man/src/services/import-contratos.ts mapeia apenas '
    '"VLR BASE" -> valor, entao esta coluna permanece NULL ate '
    'que aquele repositorio passe a envia-la (fora do escopo '
    'da migration 065). Nullable e sem DEFAULT: o default '
    'desejado seria o proprio `valor` da linha, e o Postgres '
    'nao aceita DEFAULT referenciando outra coluna. O fallback '
    'NULL => valor e aplicado na view v_contratos_dashboard.';

COMMENT ON COLUMN public.contratos.valor_liquido IS
    'Valor LIQUIDO do contrato. Origem: coluna "VLR LIQUIDO" da '
    'planilha de contratos importada pelo projeto irmao '
    'angry-man. Mesma situacao de valor_bruto: descartada hoje '
    'no mapRow() do import, permanece NULL ate mudanca naquele '
    'repositorio. Nullable, sem DEFAULT; fallback NULL => valor '
    'aplicado na view v_contratos_dashboard.';


-- ===========================================
-- 2. v_contratos_dashboard
--    Base: migration 051, identica exceto pelas duas colunas
--    novas ao final (valor_bruto / valor_liquido com fallback).
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
    -- Colunas novas (065) — obrigatoriamente ao FINAL da lista.
    -- Fallback: enquanto o angry-man nao popular, herdam `valor`
    -- (= VLR BASE) => `valor_bruto <> valor` da FALSE, sem NULL.
    COALESCE(c.valor_bruto,   c.valor) AS valor_bruto,
    COALESCE(c.valor_liquido, c.valor) AS valor_liquido
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
    '(organograma), usada pelo RLS client-side. Inclui created_at. '
    'valor_bruto/valor_liquido (065) = colunas homonimas de '
    'contratos com fallback para `valor` (VLR BASE) enquanto o '
    'angry-man nao as popular — nunca NULL na view.';


-- ===========================================
-- 3. Validacao pos-migracao
-- ===========================================
-- 1) As colunas existem e estao vazias (esperado ate o angry-man
--    mudar):
--
--   SELECT count(*) FILTER (WHERE valor_bruto   IS NOT NULL) AS com_bruto,
--          count(*) FILTER (WHERE valor_liquido IS NOT NULL) AS com_liquido,
--          count(*)                                          AS total
--   FROM contratos;
--   -- Esperado hoje: com_bruto = 0, com_liquido = 0
--
-- 2) O fallback da view nao deixa NULL nem cria diferenca falsa:
--
--   SELECT count(*)                                      AS linhas,
--          count(*) FILTER (WHERE valor_bruto IS NULL)   AS bruto_nulo,
--          count(*) FILTER (WHERE valor_bruto <> valor)  AS com_diferenca
--   FROM v_contratos_dashboard;
--   -- Esperado hoje: bruto_nulo = 0 e com_diferenca = 0
--
-- 3) A view manteve a ordem/nomes das colunas antigas (as duas
--    novas devem ser as ULTIMAS):
--
--   SELECT ordinal_position, column_name
--   FROM information_schema.columns
--   WHERE table_name = 'v_contratos_dashboard'
--   ORDER BY ordinal_position;
