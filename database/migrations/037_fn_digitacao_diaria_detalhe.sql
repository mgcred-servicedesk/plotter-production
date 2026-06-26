-- =====================================================
-- Migracao 037: RPC obter_digitacao_diaria_detalhe
--
-- Objetivo: a DIGITACAO DIARIA quebrada por REGIAO x PRODUTO
-- (grupo_dashboard), para alimentar o quadro "Ultimo Dia
-- Apurado" da pagina Em Analise. E a MESMA base do agregado
-- obter_digitacao_diaria (migration 035): le `public.contratos`
-- DIRETO, TODOS os status (sem excluir cancelados/em analise),
-- janela MES-CALENDARIO. Assim o detalhe SOMA exatamente o
-- mesmo total de digitados por dia do agregado.
--
-- A diferenca e so a granularidade: aqui agrupa por
-- (data_cadastro, regiao, grupo_dashboard) em vez de so por dia.
-- As dimensoes vem dos MESMOS joins de v_contratos_dashboard
-- (migration 001): lojas -> regioes (regiao) e produtos ->
-- categorias_produto (grupo_dashboard). LEFT JOIN garante que
-- nenhuma linha do mes fica de fora (contratos sem loja/produto
-- caem em regiao/grupo NULL — bucket "OUTROS" na UI), entao a
-- soma do detalhe == agregado.
--
-- valor_digitado = SUM(valor) BRUTO. Digitacao e volume
-- operacional: SEM ajuste por conta_valor.
--
-- Postura de seguranca: retorna SOMENTE agregados (contagem e
-- soma) por dia x dimensao. NUNCA expoe dado individual. Roda
-- como SECURITY INVOKER (implicito), logo HERDA a policy
-- pol_contratos_select (migration 011) sobre `contratos`: o
-- agregado ja sai filtrado por perfil do chamador. Mesmo padrao
-- (search_path vazio, plpgsql STABLE) da migration 035.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- RPC: obter_digitacao_diaria_detalhe
-- 1 linha por (dia, regiao, grupo_dashboard) com >= 1 contrato.
-- ===========================================

CREATE OR REPLACE FUNCTION obter_digitacao_diaria_detalhe(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    data_cadastro   DATE,
    regiao          TEXT,
    grupo_dashboard TEXT,
    qtd_digitada    BIGINT,
    valor_digitado  NUMERIC(15,2)
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

    RETURN QUERY
    SELECT
        c.data_cadastro                          AS data_cadastro,
        r.nome::TEXT                             AS regiao,
        cp.grupo_dashboard::TEXT                 AS grupo_dashboard,
        COUNT(*)                                 AS qtd_digitada,
        COALESCE(SUM(c.valor), 0)::NUMERIC(15,2) AS valor_digitado
    FROM public.contratos c
    LEFT JOIN public.lojas l                ON l.id  = c.loja_id
    LEFT JOIN public.regioes r              ON r.id  = l.regiao_id
    LEFT JOIN public.produtos p             ON p.id  = c.produto_id
    LEFT JOIN public.categorias_produto cp  ON cp.id = p.categoria_id
    WHERE c.data_cadastro >= v_data_inicio
      AND c.data_cadastro <= v_data_ref
    GROUP BY c.data_cadastro, r.nome, cp.grupo_dashboard
    ORDER BY c.data_cadastro, r.nome, cp.grupo_dashboard;
END;
$$;

COMMENT ON FUNCTION obter_digitacao_diaria_detalhe(INTEGER, INTEGER) IS
    'Digitacao diaria por regiao x grupo_dashboard: mesma base do '
    'agregado obter_digitacao_diaria (contratos direto, todos os '
    'status, janela mes-calendario, valor bruto), apenas com '
    'granularidade dia x dimensao. A soma do detalhe == agregado. '
    'So agregados; SECURITY INVOKER herda a RLS de contratos.';
