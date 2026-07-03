-- =====================================================
-- Migracao 048: obter_digitacao_diaria_detalhe com regiao
--               point-in-time e regiao_atual
--
-- Estagio 2b. Ajusta a RPC (ancora 042) para o versionamento de
-- regiao:
--   * `regiao` passa a ser a vigente na venda (data_cadastro, via
--     loja_regiao_vigencia), em vez da regiao atual da loja;
--   * adiciona `regiao_atual` (regiao corrente da loja) p/ o recorte
--     RLS client-side do gerente.
--
-- LEFT JOIN LATERAL ... LIMIT 1 e OBRIGATORIO aqui: a RPC AGREGA
-- (COUNT/SUM com GROUP BY), entao qualquer multiplicacao de linha por
-- vigencias sobrepostas corromperia os totais. O LIMIT 1 garante 1
-- regiao por contrato. COALESCE(vigencia, l.regiao_id) preserva o
-- no-op (regiao nunca vira NULL onde nao era).
--
-- Fora isso, IDENTICO a 042: mesma base (contratos direto, todos os
-- status, valor bruto), granularidade dia x regiao x loja x
-- grupo_dashboard x categoria_codigo, janela recente opcional
-- (p_dias_recentes), SECURITY INVOKER. Migrations 037/038/041/042 sao
-- imutaveis; esta substitui a RPC via DROP + CREATE (RETURNS TABLE
-- ganhou `regiao_atual`).
--
-- ⚠️ Validar com EXPLAIN ANALYZE antes do Estagio 3 (vide secao final).
--
-- Executar no Supabase SQL Editor.
-- =====================================================

DROP FUNCTION IF EXISTS obter_digitacao_diaria_detalhe(INTEGER, INTEGER, INTEGER);

CREATE OR REPLACE FUNCTION obter_digitacao_diaria_detalhe(
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
             cp.grupo_dashboard, cp.codigo
    ORDER BY c.data_cadastro, r.nome, r_atual.nome, l.nome,
             cp.grupo_dashboard, cp.codigo;
END;
$$;

COMMENT ON FUNCTION obter_digitacao_diaria_detalhe(INTEGER, INTEGER, INTEGER) IS
    'Digitacao diaria por regiao x loja x grupo_dashboard x '
    'categoria_codigo. regiao = vigente na venda (point-in-time via '
    'loja_regiao_vigencia); regiao_atual = regiao corrente da loja '
    '(RLS client-side). p_dias_recentes NULL = mes inteiro; = N limita '
    'aos ultimos N dias (clamp no 1o dia do mes). Mesma base do '
    'agregado obter_digitacao_diaria. SECURITY INVOKER; recorte '
    'client-side. Migration 048 (base 042 + versionamento regiao).';


-- ===========================================
-- Validacao (EXPLAIN ANALYZE) — rodar no Supabase antes do Estagio 3:
--
--   EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
--   SELECT * FROM obter_digitacao_diaria_detalhe(6, 2026);
--   EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
--   SELECT * FROM obter_digitacao_diaria_detalhe(6, 2026, 7);
--
-- Sanidade PRE-remanejamento: o SUM(valor_digitado) por dia deve
-- continuar batendo com obter_digitacao_diaria(6, 2026) (agregado).
-- ===========================================
