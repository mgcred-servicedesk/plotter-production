-- =====================================================
-- Migracao 067: valor_consolidado + is_cobranca_consignavel
--               em v_contratos_dashboard
--
-- Objetivo: entrou em vigor a modalidade "Cobranca
-- Consignavel" — em propostas NOVAS de consignado BMG o
-- cliente usa parte do valor para quitar debitos com o
-- banco, e o VLR BRUTO (valor cheio da venda) difere do
-- VLR BASE. Nessas operacoes a producao de loja/consultor
-- deve considerar o VLR BRUTO, nao o VLR BASE.
--
-- DECISAO DE ALCANCE: o dashboard passa a ler UMA coluna
-- consolidada. `valor_consolidado` e o VLR BASE em toda
-- linha que nao qualifica e o VLR BRUTO nas que qualificam.
-- O loader mapeia valor_consolidado -> VALOR, entao os ~40
-- consumidores de VALOR (KPIs, rankings, metas, graficos)
-- ficam corretos sem alteracao — e a pontuacao, que e
-- VALOR x PTS, passa a pontuar sobre o consolidado
-- automaticamente. O VLR BASE segue exposto em `valor`
-- (loader: VALOR_BASE) para auditoria.
--
-- NUNCA REDUZ: valor_consolidado = GREATEST(valor_bruto,
-- valor) quando a linha qualifica. Se um VLR BRUTO vier
-- MENOR que o VLR BASE (dado sujo na origem), a producao
-- NAO cai — fica no VLR BASE. A linha continua contando
-- como Cobranca Consignavel no CONTADOR (o criterio la e
-- |bruto - base| > 0,005, sem mudanca de comportamento).
--
-- ESCOPO: SO contratos pagos (esta view). v_contratos_em_
-- analise, v_contratos_cancelados e as RPCs obter_digitacao_
-- diaria* NAO sao tocadas — pipeline, cancelados e digitacao
-- seguem em VLR BASE, por decisao de negocio.
--
-- CRITERIO UNICO (fn_eh_cobranca_consignavel): o predicado
-- alimenta DUAS colunas derivadas (a flag e o CASE do
-- valor). Inline, o predicado ficaria escrito duas vezes na
-- view e uma edicao futura poderia atualizar so uma — o
-- pior bug possivel aqui (a producao sobe e a flag diz que
-- nao qualifica). Como funcao, as duas colunas nao tem como
-- divergir, o criterio ganha COMMENT proprio, e trocar a
-- regra passa a ser CREATE OR REPLACE FUNCTION — sem
-- reescrever a view (e sem esbarrar na restricao de ordem
-- de colunas do CREATE OR REPLACE VIEW).
--
-- POR QUE SEM `SET search_path = ''` (desvio consciente da
-- convencao das migrations 019/066): a clausula SET grava
-- pg_proc.proconfig, e o planner RECUSA inlinear funcao SQL
-- com proconfig (inline_function, clauses.c). Sem inlining
-- seriam ~64k chamadas de funcao por carga de periodo
-- (~16k linhas x 2 colunas x 2 queries) numa instancia Nano.
-- A convencao protege funcoes SECURITY DEFINER e/ou que
-- referenciam TABELAS (por isso o `public.` qualificado
-- nelas); esta e SECURITY INVOKER e nao toca objeto nenhum
-- — so argumentos e builtins, aqui qualificados com
-- pg_catalog (upper/btrim/abs; COALESCE e GREATEST sao
-- construcoes da GRAMATICA SQL, nao funcoes de catalogo —
-- nao podem ser qualificadas nem shadowadas). Sem SECURITY
-- DEFINER nao ha escalonamento de privilegio. NAO
-- reintroduzir o SET "por convencao" sem medir o EXPLAIN da
-- secao 4.
--
-- PARALLEL SAFE NAO E DECORATIVO: o default de qualquer
-- funcao e PARALLEL UNSAFE, e uma funcao unsafe na lista de
-- SELECT desabilita plano paralelo para TODA query sobre
-- v_contratos_dashboard.
--
-- IMPORTANTE (CREATE OR REPLACE VIEW): o Postgres so
-- permite ADICIONAR colunas no FINAL da lista, preservando
-- nome/tipo/ordem das existentes. Ordem final obrigatoria:
--   ... regiao_atual, valor_bruto, valor_liquido,
--       is_cobranca_consignavel, valor_consolidado
-- Mesma restricao ja documentada nas migrations 044 e 065.
--
-- Base da view: migration 065, identica exceto pelas duas
-- colunas novas ao final. 001/017/044/051/065 sao imutaveis;
-- esta as substitui de forma versionada, preservando
-- security_invoker.
--
-- Executar no Supabase SQL Editor. Requer 065 aplicada.
-- =====================================================


-- ===========================================
-- 0. Pre-condicao: migration 065 aplicada
--    Sem ela o CREATE OR REPLACE VIEW abaixo falharia com
--    "column c.valor_bruto does not exist" — mensagem que
--    nao diz o que fazer. Falha alto e com instrucao.
-- ===========================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'contratos'
          AND column_name  = 'valor_bruto'
    ) THEN
        RAISE EXCEPTION
            'Migration 065 nao aplicada (contratos.valor_bruto ausente). '
            'Aplique 065_contratos_valor_bruto.sql antes desta.';
    END IF;
END
$$;


-- ===========================================
-- 1. fn_eh_cobranca_consignavel
--
--    Criterio de negocio, definido UMA vez. Espelha
--    exatamente a mascara que rodava em pandas
--    (_fetch_cobranca_consignavel, src/dashboard/loaders.py)
--    e o que docs/agents/business-rules.md documenta em
--    "Cobranca Consignavel — criterio":
--
--      TIPO OPER. normalizado = 'CONTRATO NOVO'
--      SUBTIPO    normalizado = 'NOVO'  (MARGEM COMPLEMENTAR fora)
--      categoria_codigo       = 'CONSIG_BMG'
--      BANCO      normalizado IN ('BMG','BANCO BMG')  (HELP fora)
--      |VLR BRUTO - VLR BASE| > 0,005
--
--    Normalizacao upper(btrim(coalesce(x,''))) = equivalente
--    do _norm_texto do Python (.astype(str).strip().upper()):
--    NULL vira 'NONE'/'NAN' la e '' aqui — nos dois casos
--    nunca casa com os literais alvo.
--
--    NAO E STRICT de proposito: p_valor_bruto NULL e o caso
--    NORMAL (o ETL externo so passou a enviar VLR BRUTO
--    agora). STRICT devolveria NULL e a flag viraria NULL —
--    o contrario do requisito "nunca NULL". O COALESCE
--    interno faz NULL => "sem diferenca conhecida" => FALSE,
--    mesmo espirito do fallback da migration 065.
--
--    O criterio de PERIODO (status_pagamento_cliente =
--    'PAGO AO CLIENTE' + data no mes) NAO entra aqui: esta
--    view so tem pagos ou seguros liquidados, e seguro
--    liquidado tem tipo_operacao IN ('BMG MED','Seguro') —
--    nunca 'Contrato Novo'. Logo nenhuma linha nao-paga
--    consegue qualificar. O recorte de mes continua sendo
--    do consumidor (periodo_id + reconferencia em DATA).
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_eh_cobranca_consignavel(
    p_tipo_operacao    TEXT,
    p_subtipo          TEXT,
    p_categoria_codigo TEXT,
    p_banco            TEXT,
    p_valor            NUMERIC,
    p_valor_bruto      NUMERIC
)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $$
    -- COALESCE nao aparece qualificado de proposito: e uma construcao da
    -- GRAMATICA SQL (como CASE/GREATEST/NULLIF), nao uma funcao de
    -- pg_catalog — `pg_catalog.coalesce(...)` e erro de sintaxe. Pelo
    -- mesmo motivo, nao ha como shadowa-la via search_path. Ja upper /
    -- btrim / abs SAO funcoes de catalogo e ficam qualificadas.
    SELECT COALESCE(
        pg_catalog.upper(pg_catalog.btrim(
            COALESCE(p_tipo_operacao, ''))) = 'CONTRATO NOVO'
        AND pg_catalog.upper(pg_catalog.btrim(
            COALESCE(p_subtipo, ''))) = 'NOVO'
        AND pg_catalog.upper(pg_catalog.btrim(
            COALESCE(p_categoria_codigo, ''))) = 'CONSIG_BMG'
        AND pg_catalog.upper(pg_catalog.btrim(
            COALESCE(p_banco, ''))) IN ('BMG', 'BANCO BMG')
        AND pg_catalog.abs(
                COALESCE(p_valor_bruto, COALESCE(p_valor, 0))
                - COALESCE(p_valor, 0)
            ) > 0.005,
        false
    );
$$;

COMMENT ON FUNCTION public.fn_eh_cobranca_consignavel(
    TEXT, TEXT, TEXT, TEXT, NUMERIC, NUMERIC) IS
    'Criterio unico da modalidade Cobranca Consignavel '
    '(vigente 08/2026): proposta NOVA de consignado BMG em '
    'que o cliente usa parte do valor para quitar debitos '
    'com o banco — VLR BRUTO diferente do VLR BASE. AND de: '
    'tipo_operacao=CONTRATO NOVO, subtipo=NOVO (MARGEM '
    'COMPLEMENTAR fora), categoria_codigo=CONSIG_BMG, banco '
    'em (BMG, BANCO BMG) e |valor_bruto - valor| > 0,005. '
    'Comparacoes normalizadas com upper(btrim(coalesce(...))) '
    'porque a base nao e uniformemente maiuscula. NUNCA '
    'retorna NULL: valor_bruto NULL (ETL ainda nao enviou) '
    'cai em FALSE, mesmo caso neutro da migration 065 — por '
    'isso a funcao nao e STRICT. Alimenta as colunas '
    'is_cobranca_consignavel e valor_consolidado de '
    'v_contratos_dashboard; nao duplicar o predicado em '
    'nenhum outro lugar — alterar a regra e CREATE OR '
    'REPLACE desta funcao. Espelho documental em '
    'docs/agents/business-rules.md.';


-- ===========================================
-- 2. v_contratos_dashboard
--    Base: migration 065, identica exceto pelas DUAS colunas
--    novas ao final (is_cobranca_consignavel /
--    valor_consolidado).
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
    -- Colunas da 065 — fallback: enquanto o angry-man nao popular,
    -- herdam `valor` (= VLR BASE) => `valor_bruto <> valor` da FALSE.
    COALESCE(c.valor_bruto,   c.valor) AS valor_bruto,
    COALESCE(c.valor_liquido, c.valor) AS valor_liquido,
    -- Colunas novas (067) — obrigatoriamente ao FINAL da lista.
    -- Passa c.valor_bruto CRU (nao o alias COALESCE acima: alias de
    -- SELECT nao e referenciavel na mesma lista, e a funcao ja trata
    -- NULL => FALSE).
    public.fn_eh_cobranca_consignavel(
        c.tipo_operacao, p.subtipo, cp.codigo, c.banco,
        c.valor, c.valor_bruto
    ) AS is_cobranca_consignavel,
    -- GREATEST so aparece no ramo que qualifica: e o "nunca reduzir".
    -- O COALESCE interno e redundante por construcao (qualificar
    -- implica valor_bruto NOT NULL), mas fica explicito para a
    -- expressao ser segura lida fora de contexto. GREATEST ignora
    -- NULL no Postgres e so retorna NULL se TODOS os argumentos forem
    -- NULL — como contratos.valor e NOT NULL DEFAULT 0 (schema.sql),
    -- esta coluna nunca e NULL. Cast explicito para NUMERIC(15,2)
    -- porque GREATEST/CASE descartam o typmod, e o tipo de uma coluna
    -- de view e imutavel para CREATE OR REPLACE futuros.
    (CASE
        WHEN public.fn_eh_cobranca_consignavel(
                c.tipo_operacao, p.subtipo, cp.codigo, c.banco,
                c.valor, c.valor_bruto)
        THEN GREATEST(COALESCE(c.valor_bruto, c.valor), c.valor)
        ELSE c.valor
     END)::NUMERIC(15,2) AS valor_consolidado
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
    'contratos com fallback para `valor` (VLR BASE). '
    'is_cobranca_consignavel/valor_consolidado (067) = flag do '
    'criterio de Cobranca Consignavel e valor que o dashboard usa '
    'como PRODUCAO. Nenhuma das quatro e NULL.';

COMMENT ON COLUMN v_contratos_dashboard.is_cobranca_consignavel IS
    'TRUE quando a linha e uma operacao de Cobranca Consignavel '
    '(proposta NOVA de consignado BMG em que o cliente quitou '
    'debitos com o banco, VLR BRUTO <> VLR BASE). Definido por '
    'fn_eh_cobranca_consignavel — criterio unico, nao reimplementar '
    'no consumidor. Nunca NULL. Enquanto o ETL (angry-man) nao '
    'popular contratos.valor_bruto, e FALSE em 100% das linhas.';

COMMENT ON COLUMN v_contratos_dashboard.valor_consolidado IS
    'Valor que o dashboard considera como PRODUCAO da linha: o '
    'VLR BASE (`valor`) no caso geral, e GREATEST(valor_bruto, '
    'valor) quando is_cobranca_consignavel — nessas operacoes a '
    'venda cheia e o VLR BRUTO. NUNCA reduz: VLR BRUTO menor que o '
    'VLR BASE (dado sujo) mantem o VLR BASE, mas a linha segue '
    'contando no CONTADOR de Cobranca Consignavel (criterio la e '
    '|bruto - base| > 0,005). Nunca NULL (contratos.valor e NOT '
    'NULL). O loader mapeia esta coluna para VALOR e `valor` para '
    'VALOR_BASE — todo KPI de producao e a pontuacao (VALOR x PTS) '
    'leem esta coluna.';


-- ===========================================
-- 3. Indice: NENHUM — decisao deliberada
--
-- Nao criar indice (nem funcional sobre a expressao, nem parcial)
-- para o filtro is_cobranca_consignavel. Motivos, na linha da
-- migration 055:
--   a) contratos acumula 1,39M updates para 200k inserts (o ETL
--      reescreve linhas) e CADA indice amplifica a escrita de TODO
--      update (WAL + paginas + autovacuum). A 055 dropou 5 indices
--      exatamente por isso.
--   b) a tabela tem ~68 MB e cabe inteira em shared_buffers: o
--      filtro roda EM MEMORIA, sem tocar disco.
--   c) o predicado referencia colunas de produtos e
--      categorias_produto (lado nullable de LEFT JOIN) — nao ha como
--      avalia-lo antes dos joins, entao um indice em contratos nao
--      seria usavel de todo jeito.
--   d) a query ja e recortada por periodo_id (idx_contratos_periodo_
--      status_pag), ~16k linhas/mes, e o dashboard a executa no
--      maximo 1x a cada 30min (cache).
-- Se um dia o volume mudar, medir com pg_stat_statements ANTES —
-- nao criar indice preventivo.
-- ===========================================


-- ===========================================
-- 4. Validacao pos-migracao
--
-- ATENCAO: este bloco E a suite de testes do criterio. Como a regra
-- migrou para SQL, o pytest deixou de cobri-la — rodar as queries 1
-- a 3 a cada alteracao de fn_eh_cobranca_consignavel.
-- ===========================================
-- 1) Bordas da funcao (nenhuma linha da base envolvida):
--
--   SELECT fn_eh_cobranca_consignavel('Contrato Novo','NOVO','CONSIG_BMG','BMG',100,120)              AS deve_true,
--          fn_eh_cobranca_consignavel(' contrato novo ',' novo ','CONSIG_BMG','Banco BMG',100,120)    AS deve_true_norm,
--          fn_eh_cobranca_consignavel('Contrato Novo','NOVO','CONSIG_BMG','BMG',100,NULL)             AS deve_false_null,
--          fn_eh_cobranca_consignavel('Contrato Novo','NOVO','CONSIG_BMG','BMG',100,100.004)          AS deve_false_tolerancia,
--          fn_eh_cobranca_consignavel('Contrato Novo','MARGEM COMPLEMENTAR','CONSIG_BMG','BMG',100,120) AS deve_false_margem,
--          fn_eh_cobranca_consignavel('Contrato Novo','NOVO',NULL,'BMG',100,120)                      AS deve_false_sem_categoria,
--          fn_eh_cobranca_consignavel('Contrato Novo','NOVO','CONSIG_BMG','HELP',100,120)             AS deve_false_help,
--          fn_eh_cobranca_consignavel('Portabilidade','NOVO','CONSIG_BMG','BMG',100,120)              AS deve_false_portab;
--   -- Esperado: t, t, f, f, f, f, f, f
--
--   -- E o "nunca reduzir" na propria expressao (bruto < base):
--   SELECT fn_eh_cobranca_consignavel('Contrato Novo','NOVO','CONSIG_BMG','BMG',100,80) AS flag_deve_true,
--          GREATEST(80::NUMERIC, 100::NUMERIC)                                          AS consolidado_deve_100;
--
-- 2) Colunas novas existem, sao as ULTIMAS e nunca NULL:
--
--   SELECT ordinal_position, column_name, data_type
--   FROM information_schema.columns
--   WHERE table_name = 'v_contratos_dashboard'
--   ORDER BY ordinal_position;
--   -- Esperado no fim: ... regiao_atual, valor_bruto, valor_liquido,
--   --                  is_cobranca_consignavel, valor_consolidado
--
--   SELECT count(*) FILTER (WHERE is_cobranca_consignavel IS NULL) AS flag_nula,
--          count(*) FILTER (WHERE valor_consolidado       IS NULL) AS valor_nulo
--   FROM v_contratos_dashboard;
--   -- Esperado SEMPRE: 0, 0
--
--   -- E a funcao ficou inlineavel/paralelizavel?
--   SELECT proname, provolatile, proparallel, proconfig
--   FROM pg_proc WHERE proname = 'fn_eh_cobranca_consignavel';
--   -- Esperado: i (immutable), s (safe), proconfig NULL (inlineavel)
--
-- 3) "Nunca reduzir" (invariante permanente):
--
--   SELECT count(*) FROM v_contratos_dashboard
--   WHERE valor_consolidado < valor;
--   -- Esperado SEMPRE: 0
--
-- 4) GATE DE IDA/NAO-IDA DO DEPLOY — o impacto tem que bater com a
--    previa medida ANTES de aplicar esta migration (auditoria de
--    2026-08-14 sobre a base real; ver o progress
--    2026-08-14-producao-valor-bruto-cobranca-consignavel.md):
--
--   SELECT count(*) FILTER (WHERE is_cobranca_consignavel)    AS qualificam,
--          count(*) FILTER (WHERE valor_consolidado <> valor) AS divergem,
--          sum(valor)                                         AS total_base,
--          sum(valor_consolidado)                             AS total_consolidado,
--          sum(valor_consolidado - valor)                     AS uplift
--   FROM v_contratos_dashboard;
--   -- Esperado na aplicacao (14/08/2026): qualificam = 2, divergem = 2,
--   --   uplift = 15429.70 (contratos 2991146 e 2994099, ambos 08/2026).
--   -- Numero MUITO maior que isso = provavel ETL gravando 0 em
--   --   valor_bruto (ver INTEGRACAO.md 4.2) — NAO seguir com o deploy.
--   --
--   -- Se rodar numa base onde o ETL ainda nao populou valor_bruto, o
--   -- esperado e o caso neutro: qualificam = 0, divergem = 0,
--   -- total_base = total_consolidado (igualdade exata).
--
-- 5) DEPOIS da primeira carga com VLR BRUTO — impacto por periodo:
--
--   SELECT per.referencia,
--          count(*) FILTER (WHERE v.is_cobranca_consignavel) AS qtd_consignavel,
--          sum(v.valor_consolidado - v.valor)                AS uplift
--   FROM v_contratos_dashboard v
--   JOIN periodos per ON per.id = v.periodo_id
--   GROUP BY per.referencia, per.ano, per.mes
--   ORDER BY per.ano DESC, per.mes DESC;
--
-- 6) DIVERGENCIA CONHECIDA — fallback de categoria do Python.
--    _preencher_categoria_fallback (loaders.py) mapeia TIPO_PRODUTO
--    'CONSIG'/'CONSIG BMG' -> CONSIG_BMG quando produtos.categoria_id
--    esta NULL (ver migration 061). O SQL usa cp.codigo cru e NAO
--    enxerga esse fallback — a linha nao receberia o uplift
--    (subnotificacao, nunca superestimacao). Esta query mede o gap;
--    se voltar > 0, a causa e produto sem categoria_id: corrigir a
--    ORIGEM (ETL), nao a regra.
--
--   SELECT count(*)
--   FROM contratos c
--   LEFT JOIN produtos p            ON p.id  = c.produto_id
--   LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
--   WHERE cp.codigo IS NULL
--     AND upper(btrim(coalesce(p.tipo,''))) IN ('CONSIG','CONSIG BMG')
--     AND upper(btrim(coalesce(c.tipo_operacao,''))) = 'CONTRATO NOVO'
--     AND abs(coalesce(c.valor_bruto, c.valor) - c.valor) > 0.005;
--   -- Esperado: 0
--
-- 7) Paridade com o contador que rodava em pandas (rodar UMA vez no
--    deploy, comparando com o card da aba Reconquista do mes):
--
--   SELECT count(*) FROM v_contratos_dashboard v
--   JOIN periodos per ON per.id = v.periodo_id
--   WHERE per.mes = 8 AND per.ano = 2026
--     AND v.status_pagamento_cliente = 'PAGO AO CLIENTE'
--     AND v.is_cobranca_consignavel;
--   -- Esperado: mesmo numero do card "Cobranca Consignavel"
--
-- 8) Custo do predicado na query mais quente (comparar com baseline
--    capturado ANTES da 067):
--
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT id, valor, valor_consolidado, is_cobranca_consignavel
--   FROM v_contratos_dashboard
--   WHERE periodo_id = '<uuid do mes>'
--   ORDER BY id LIMIT 1000;
