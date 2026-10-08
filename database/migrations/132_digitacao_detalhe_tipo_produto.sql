-- =====================================================
-- Migracao 132: obter_digitacao_diaria_detalhe devolve tipo_produto
--               das linhas sem categoria
--
-- Problema (verificado em 2026-10-08): no quadro "Digitacao do Ultimo
-- Dia" (pagina Em Analise) a coluna OUTROS somava R$ 92.684,00 em
-- 06/10 — 15 contratos CLT (BMG/C6) + 23 ANT. DE BENEF. (HELP).
--
-- Causa: o importador de produtos do angry-man ainda nao conhece os
-- tipos renomeados na origem ('CLT', 'ANT. DE BENEF.') e grava
-- produtos.categoria_id = NULL a cada import (desfaz o backfill da
-- 061). As cargas de pagos/em analise/cancelados se recuperam no app
-- (_preencher_categoria_fallback, por TIPO_PRODUTO) e o Caderno tem o
-- proprio CASE por tipo_produto; esta RPC nao trazia o tipo, entao a
-- linha chegava sem grupo_dashboard e virava OUTROS no pivot.
--
-- Correcao (contorno no dashboard; a correcao na origem — angry-man —
-- fica para depois): a RPC passa a devolver `tipo_produto`, e o loader
-- aplica o mesmo fallback das outras cargas.
--
-- Decisoes:
--   * tipo_produto so e preenchido quando o produto NAO tem categoria
--     (CASE WHEN cp.id IS NULL). Linhas categorizadas devolvem NULL:
--     a granularidade (e o payload) nao cresce, e o eh_emissao do app
--     (que le TIPO_PRODUTO) nao muda nada nas linhas que ja tinham
--     categoria.
--   * Mudanca de RETURNS TABLE exige DROP + CREATE (como na 048).
--     Tudo numa transacao: nao ha janela com a funcao ausente.
--   * O wrapper _json (057) e LANGUAGE sql sem BEGIN ATOMIC — nao
--     registra dependencia e repassa as colunas via json_agg(t), entao
--     ja carrega tipo_produto. E recriado aqui identico apenas para
--     deixar o par explicito no mesmo arquivo.
--   * GRANTs reaplicados (o DROP os descarta). A funcao nao tinha
--     statement_timeout proprio (so search_path) — nada a repor.
--   * Ordem de deploy livre: o app novo tolera a RPC antiga (tipo
--     ausente → fallback nao preenche, comportamento de hoje) e o app
--     antigo ignora a coluna nova.
--
-- Fora isso, IDENTICA a 048 (corpo conferido contra pg_get_functiondef
-- em producao em 2026-10-08).
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

DROP FUNCTION IF EXISTS public.obter_digitacao_diaria_detalhe(INTEGER, INTEGER, INTEGER);

CREATE OR REPLACE FUNCTION public.obter_digitacao_diaria_detalhe(
    p_mes INTEGER,
    p_ano INTEGER,
    p_dias_recentes INTEGER DEFAULT NULL
)
RETURNS TABLE (
    data_cadastro    DATE,
    regiao           TEXT,
    regiao_atual     TEXT,
    loja             TEXT,
    grupo_dashboard  TEXT,
    categoria_codigo TEXT,
    tipo_produto     TEXT,
    qtd_digitada     BIGINT,
    valor_digitado   NUMERIC(15,2)
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
    -- Primeiro dia do mes selecionado
    v_data_inicio := make_date(p_ano, p_mes, 1);

    -- Data de referencia: hoje se mes vigente (acumula ate hoje),
    -- senao ultimo dia do mes selecionado (mes inteiro). Identico
    -- ao agregado da migration 035.
    IF p_mes = EXTRACT(MONTH FROM v_hoje)::INTEGER
       AND p_ano = EXTRACT(YEAR FROM v_hoje)::INTEGER
    THEN
        v_data_ref := v_hoje;
    ELSE
        v_data_ref := (v_data_inicio
                       + INTERVAL '1 month'
                       - INTERVAL '1 day')::DATE;
    END IF;

    -- Janela recente opcional: nunca recua antes do 1o dia do mes.
    IF p_dias_recentes IS NOT NULL AND p_dias_recentes > 0 THEN
        v_data_inicio := GREATEST(
            v_data_inicio,
            (v_data_ref - make_interval(days => p_dias_recentes - 1))::DATE
        );
    END IF;

    RETURN QUERY
    SELECT
        c.data_cadastro                          AS data_cadastro,
        r.nome::TEXT                             AS regiao,
        r_atual.nome::TEXT                       AS regiao_atual,
        l.nome::TEXT                             AS loja,
        cp.grupo_dashboard::TEXT                 AS grupo_dashboard,
        cp.codigo::TEXT                          AS categoria_codigo,
        -- So para linhas sem categoria: alimenta o fallback do app.
        (CASE WHEN cp.id IS NULL THEN p.tipo END)::TEXT AS tipo_produto,
        COUNT(*)                                 AS qtd_digitada,
        COALESCE(SUM(c.valor), 0)::NUMERIC(15,2) AS valor_digitado
    FROM public.contratos c
    LEFT JOIN public.lojas l                ON l.id  = c.loja_id
    LEFT JOIN LATERAL (
        SELECT vig.regiao_id
        FROM public.loja_regiao_vigencia vig
        WHERE vig.loja_id = c.loja_id
          AND c.data_cadastro >= vig.vigencia_inicio
          AND (vig.vigencia_fim IS NULL
               OR c.data_cadastro < vig.vigencia_fim)
        ORDER BY vig.vigencia_inicio DESC
        LIMIT 1
    ) rv ON true
    LEFT JOIN public.regioes r       ON r.id = COALESCE(rv.regiao_id, l.regiao_id)
    LEFT JOIN public.regioes r_atual ON r_atual.id = l.regiao_id
    LEFT JOIN public.produtos p             ON p.id  = c.produto_id
    LEFT JOIN public.categorias_produto cp  ON cp.id = p.categoria_id
    WHERE c.data_cadastro >= v_data_inicio
      AND c.data_cadastro <= v_data_ref
    GROUP BY c.data_cadastro, r.nome, r_atual.nome, l.nome,
             cp.grupo_dashboard, cp.codigo,
             (CASE WHEN cp.id IS NULL THEN p.tipo END)
    ORDER BY c.data_cadastro, r.nome, r_atual.nome, l.nome,
             cp.grupo_dashboard, cp.codigo;
END;
$$;

COMMENT ON FUNCTION public.obter_digitacao_diaria_detalhe(INTEGER, INTEGER, INTEGER) IS
    'Digitacao diaria por regiao x loja x grupo_dashboard x '
    'categoria_codigo. regiao = vigente na venda (point-in-time via '
    'loja_regiao_vigencia); regiao_atual = regiao corrente da loja '
    '(RLS client-side). tipo_produto so vem preenchido quando o produto '
    'esta sem categoria (fallback do app). p_dias_recentes NULL = mes '
    'inteiro; = N limita aos ultimos N dias (clamp no 1o dia do mes). '
    'SECURITY INVOKER; recorte client-side. Migration 132 (base 048 + '
    'tipo_produto).';

GRANT EXECUTE ON FUNCTION
    public.obter_digitacao_diaria_detalhe(INTEGER, INTEGER, INTEGER)
    TO anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.obter_digitacao_diaria_detalhe_json(
    p_mes INTEGER,
    p_ano INTEGER,
    p_dias_recentes INTEGER DEFAULT NULL
)
RETURNS JSON
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT COALESCE(json_agg(t), '[]'::json)
    FROM public.obter_digitacao_diaria_detalhe(
        p_mes, p_ano, p_dias_recentes
    ) t;
$$;

COMMIT;

NOTIFY pgrst, 'reload schema';


-- ===========================================
-- Verificacao (rodar apos aplicar):
--
-- 1. A coluna nova existe e so vem preenchida sem categoria:
--   SELECT tipo_produto, categoria_codigo IS NULL AS sem_cat,
--          SUM(qtd_digitada) qtd, SUM(valor_digitado) valor
--   FROM obter_digitacao_diaria_detalhe(10, 2026, 7)
--   GROUP BY 1, 2 ORDER BY 2, 1;
--   -- esperado: tipo_produto NULL em todas as linhas sem_cat = false;
--   -- CLT e ANT. DE BENEF. nas linhas sem_cat = true.
--
-- 2. Totais por dia inalterados (paridade com o agregado):
--   SELECT data_cadastro, SUM(valor_digitado)
--   FROM obter_digitacao_diaria_detalhe(10, 2026)
--   GROUP BY 1 ORDER BY 1;
--   SELECT data_cadastro, valor_digitado
--   FROM obter_digitacao_diaria(10, 2026) ORDER BY 1;
--
-- 3. O wrapper carrega a coluna nova:
--   SELECT obter_digitacao_diaria_detalhe_json(10, 2026, 7)::jsonb -> 0;
-- ===========================================
