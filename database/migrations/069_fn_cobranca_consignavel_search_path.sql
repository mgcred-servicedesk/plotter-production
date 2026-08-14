-- =====================================================
-- Migracao 069: SET search_path = '' em
--               fn_eh_cobranca_consignavel
--
-- Objetivo: fechar o aviso do Supabase Security Advisor
-- `function_search_path_mutable` ("Detects functions where
-- the search_path parameter is not set"). Depois da 067,
-- fn_eh_cobranca_consignavel era a UNICA funcao do projeto
-- sem a clausula — as ~30 outras (schema.sql + migrations
-- 001..068) ja usam `SET search_path = ''` (ou `= public`
-- nas duas de escrita, 015 e 063).
--
-- ESTA MIGRATION REVERTE UM DESVIO DELIBERADO DA 067.
-- O cabecalho da 067, secao "POR QUE SEM `SET search_path`",
-- fica SUPERSEDIDO por este arquivo. A 067 e imutavel (ja
-- aplicada) e nao pode ser corrigida in-place — quem ler
-- aquele paragrafo deve ler este. Motivo da reversao:
--
--   1. A conta de custo da 067 estava errada, e para mais.
--      Ela estimava "~64k chamadas por carga de periodo
--      (~16k linhas x 2 colunas x 2 queries)". O codigo que
--      de fato ficou chama menos: _fetch_contratos_pagos
--      seleciona apenas valor_consolidado (1 chamada/linha,
--      ~16k) e _fetch_cobranca_consignavel avalia o
--      predicado no WHERE via .eq(is_cobranca_consignavel)
--      (~16k) — a lista de SELECT roda so nas ~2 linhas
--      sobreviventes. Total ~32k, nao ~64k. A ~1-3 us por
--      chamada de funcao SQL nao inlinada, sao ~30-100 ms
--      por carga de periodo, UMA vez a cada 30 min (TTL do
--      @st.cache_data), dentro de uma query que ja serializa
--      ~16k linhas de JSON por HTTPS. Medir na secao 3.
--
--   2. O risco que a clausula previne nao existe aqui, mas o
--      custo de ser a excecao existe. A funcao e SECURITY
--      INVOKER (sem escalonamento de privilegio) e nao
--      referencia objeto nenhum — so parametros, literais e
--      builtins ja qualificados com pg_catalog. Nao ha
--      superficie pratica de sequestro, ainda mais com o
--      projeto usando uma unica chave service_role (sem
--      usuarios SQL nao confiaveis). Mas um WARN permanente
--      e sem supressao por objeto no advisor vira ruido
--      fixo, e ruido fixo mascara o proximo aviso — que pode
--      ser real. Convencao uniforme tambem e o que permite
--      revisar por excecao.
--
-- O CORPO NAO MUDA. `search_path = ''` nao quebra nada aqui:
-- pg_catalog e sempre pesquisado implicitamente quando nao
-- nomeado no path, entao operadores (=, >, -, AND, IN) e os
-- builtins continuam resolvendo. E upper/btrim/abs ja estao
-- qualificados desde a 067; COALESCE e construcao da
-- gramatica SQL. A funcao nao le tabela alguma, logo `''`
-- (o mais estrito) e correto — nao `= public`.
--
-- CUIDADO (a armadilha desta migration): CREATE OR REPLACE
-- FUNCTION NAO preserva atributos omitidos. O manual e
-- explicito: "All other function properties are assigned the
-- values specified or implied in the command" — o que nao
-- for repetido volta ao DEFAULT (VOLATILE, PARALLEL UNSAFE,
-- SECURITY INVOKER). Omitir PARALLEL SAFE aqui desabilitaria
-- plano paralelo em TODA query sobre v_contratos_dashboard,
-- e omitir IMMUTABLE tiraria a funcao de qualquer avaliacao
-- antecipada. Por isso IMMUTABLE e PARALLEL SAFE aparecem
-- repetidos abaixo, identicos aos da 067. A secao 2 verifica.
--
-- A VIEW NAO PRECISA SER REEMITIDA: v_contratos_dashboard
-- referencia a funcao por OID, que CREATE OR REPLACE
-- preserva. Nenhuma coluna, tipo ou ordem muda — e portanto
-- nenhum contrato com o loader muda. Esta migration e
-- semanticamente NEUTRA: mesmos valores, mesmas flags.
--
-- ROLLBACK: se a secao 3 mostrar um delta inaceitavel,
-- reemitir a funcao SEM a clausula numa migration 070 (nunca
-- editando esta) e registrar a medicao que justificou.
--
-- Executar no Supabase SQL Editor. Requer 067 aplicada.
-- =====================================================


-- ===========================================
-- 0. Pre-condicao: migration 067 aplicada
--    Sem ela nao ha o que substituir, e um CREATE puro
--    criaria a funcao sem que a view a usasse — estado
--    silenciosamente inutil. Falha alto e com instrucao.
-- ===========================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc pr
        JOIN pg_namespace n ON n.oid = pr.pronamespace
        WHERE n.nspname = 'public'
          AND pr.proname = 'fn_eh_cobranca_consignavel'
    ) THEN
        RAISE EXCEPTION
            'Migration 067 nao aplicada (funcao '
            'fn_eh_cobranca_consignavel ausente). Aplique '
            '067_valor_consolidado_cobranca_consignavel.sql antes desta.';
    END IF;
END
$$;


-- ===========================================
-- 1. fn_eh_cobranca_consignavel — corpo IDENTICO ao da 067.
--    A unica diferenca e a linha `SET search_path = ''`.
--    IMMUTABLE e PARALLEL SAFE repetidos de proposito (ver
--    "CUIDADO" no cabecalho): CREATE OR REPLACE nao herda
--    atributo omitido.
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
SET search_path = ''
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

-- COMMENT ON substitui o comentario inteiro (nao acrescenta),
-- entao o texto da 067 e reemitido na integra, com a ultima
-- frase nova sobre o search_path.
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
    'docs/agents/business-rules.md. '
    'search_path fixado em '''' pela migration 069 (advisor '
    'function_search_path_mutable); a funcao nao referencia '
    'objeto algum, entao o path vazio e seguro — nao '
    'reintroduzir search_path mutavel.';


-- ===========================================
-- 2. Validacao — rodar apos aplicar
-- ===========================================

-- 2.1 Atributos: a clausula entrou E nada regrediu ao default.
--     Esperado: provolatile=i, proparallel=s, prosecdef=f,
--               proconfig={"search_path="}
--     proparallel='u' ou provolatile='v' aqui significa que a
--     linha correspondente foi perdida no copy/paste — pare e
--     reemita a secao 1.
-- SELECT proname, provolatile, proparallel, prosecdef, proconfig
-- FROM pg_proc
-- WHERE proname = 'fn_eh_cobranca_consignavel';

-- 2.2 Bordas do criterio — mesmos casos da secao 4 da 067.
--     TODOS devem devolver o mesmo resultado de antes: esta
--     migration nao muda o predicado. Esperado por linha:
--     t, t, f, f, f, f, f
-- SELECT
--     public.fn_eh_cobranca_consignavel(
--         'Contrato Novo','NOVO','CONSIG_BMG','BMG',100,120)   AS qualifica,
--     public.fn_eh_cobranca_consignavel(
--         '  contrato novo ',' novo ','consig_bmg','Banco BMG',
--         100,120)                                             AS normalizado,
--     public.fn_eh_cobranca_consignavel(
--         'Contrato Novo','NOVO','CONSIG_BMG','BMG',100,NULL)  AS bruto_nulo,
--     public.fn_eh_cobranca_consignavel(
--         'Contrato Novo','NOVO','CONSIG_BMG','BMG',100,100.004) AS sob_tolerancia,
--     public.fn_eh_cobranca_consignavel(
--         'Contrato Novo','MARGEM COMPLEMENTAR','CONSIG_BMG','BMG',
--         100,120)                                             AS margem,
--     public.fn_eh_cobranca_consignavel(
--         'Contrato Novo','NOVO',NULL,'BMG',100,120)           AS sem_categoria,
--     public.fn_eh_cobranca_consignavel(
--         'Contrato Novo','NOVO','CONSIG_BMG','HELP',100,120)  AS outro_banco;

-- 2.3 Invariante permanente da view. Esperado: 0.
-- SELECT count(*) FROM v_contratos_dashboard
-- WHERE valor_consolidado < valor;

-- 2.4 Neutralidade semantica — o numero do negocio nao pode
--     ter mudado. Comparar com a medicao pos-067 registrada em
--     docs/agents/progress/2026-08-14-producao-valor-bruto-
--     cobranca-consignavel.md. Esperado (08/2026):
--     qualificam = 2, uplift = 15429.70
-- SELECT
--     count(*) FILTER (WHERE v.is_cobranca_consignavel) AS qualificam,
--     round(sum(v.valor_consolidado - v.valor), 2)      AS uplift
-- FROM v_contratos_dashboard v
-- JOIN periodos pe ON pe.id = v.periodo_id
-- WHERE pe.referencia = '2026-08';

-- 2.5 Nao sobrou nenhuma funcao sem search_path (fecha o
--     advisor). Esperado: 0 linhas.
-- SELECT n.nspname, pr.proname
-- FROM pg_proc pr
-- JOIN pg_namespace n ON n.oid = pr.pronamespace
-- WHERE n.nspname = 'public'
--   AND pr.prokind = 'f'
--   AND pr.proconfig IS NULL
-- ORDER BY 2;


-- ===========================================
-- 3. Medicao do custo do inlining perdido
--
--    A funcao passa a ter proconfig != NULL, e o planner
--    recusa inlinear funcao SQL nessa condicao
--    (inline_function, clauses.c). O cabecalho estima
--    ~30-100 ms por carga de periodo; esta secao mede o
--    numero real em vez de confiar na estimativa.
--
--    Rodar com o uuid do periodo corrente. O primeiro
--    EXPLAIN ja e o estado NOVO (pos-069). Para o baseline
--    inlinado, o bloco de comparacao abaixo reemite a versao
--    sem a clausula dentro de uma transacao e faz ROLLBACK —
--    nada persiste.
--
--    Se o delta passar de ~1 s, reavaliar (ver ROLLBACK no
--    cabecalho). Abaixo disso, o custo e irrelevante frente
--    ao TTL de 30 min do cache.
-- ===========================================

-- 3.1 Estado atual (pos-069, NAO inlinado):
-- EXPLAIN (ANALYZE, BUFFERS)
-- SELECT id, valor, valor_consolidado
-- FROM v_contratos_dashboard
-- WHERE periodo_id = '<uuid do periodo>';

-- 3.2 Baseline inlinado, sem persistir:
-- BEGIN;
--     CREATE OR REPLACE FUNCTION public.fn_eh_cobranca_consignavel(
--         p_tipo_operacao TEXT, p_subtipo TEXT, p_categoria_codigo TEXT,
--         p_banco TEXT, p_valor NUMERIC, p_valor_bruto NUMERIC)
--     RETURNS BOOLEAN LANGUAGE SQL IMMUTABLE PARALLEL SAFE
--     AS $BENCH$
--         SELECT COALESCE(
--             pg_catalog.upper(pg_catalog.btrim(
--                 COALESCE(p_tipo_operacao, ''))) = 'CONTRATO NOVO'
--             AND pg_catalog.upper(pg_catalog.btrim(
--                 COALESCE(p_subtipo, ''))) = 'NOVO'
--             AND pg_catalog.upper(pg_catalog.btrim(
--                 COALESCE(p_categoria_codigo, ''))) = 'CONSIG_BMG'
--             AND pg_catalog.upper(pg_catalog.btrim(
--                 COALESCE(p_banco, ''))) IN ('BMG', 'BANCO BMG')
--             AND pg_catalog.abs(
--                     COALESCE(p_valor_bruto, COALESCE(p_valor, 0))
--                     - COALESCE(p_valor, 0)
--                 ) > 0.005,
--             false
--         );
--     $BENCH$;
--
--     EXPLAIN (ANALYZE, BUFFERS)
--     SELECT id, valor, valor_consolidado
--     FROM v_contratos_dashboard
--     WHERE periodo_id = '<uuid do periodo>';
-- ROLLBACK;   -- descarta a versao sem search_path

-- 3.3 Caminho mais sensivel (predicado no WHERE, avaliado em
--     todas as linhas do periodo para devolver ~2):
-- EXPLAIN (ANALYZE, BUFFERS)
-- SELECT id, valor, valor_consolidado, is_cobranca_consignavel
-- FROM v_contratos_dashboard
-- WHERE periodo_id = '<uuid do periodo>'
--   AND is_cobranca_consignavel;
