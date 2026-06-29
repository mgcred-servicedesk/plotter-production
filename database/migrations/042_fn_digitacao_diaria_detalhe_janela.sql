-- =====================================================
-- Migracao 042: obter_digitacao_diaria_detalhe com janela recente
--               opcional (p_dias_recentes)
--
-- Motivo:
-- O detalhe da digitacao alimenta DOIS quadros da pagina "Em Analise":
--   * "Digitacao do Ultimo Dia" (so o ultimo dia apurado do escopo);
--   * "Digitacao - Ultimos 7 Dias" (serie dos 7 dias recentes).
-- Ambos so precisam da JANELA RECENTE, mas a RPC trazia o MES INTEIRO
-- (dia x loja x grupo_dashboard x categoria_codigo apos a 041) e o app
-- descartava o resto. Com a 041 o numero de linhas ~dobrou (split do
-- PACK/CNC/SAQUE/CONSIGNADO por categoria), agravando o over-fetch.
--
-- IMPORTANTE — por que NAO filtrar "so o ultimo dia" no servidor:
-- o app usa UMA chave Supabase compartilhada (sem JWT por usuario), entao
-- a RPC devolve dado GLOBAL e o recorte por perfil e feito CLIENT-SIDE
-- (aplicar_rls). Logo o servidor NAO sabe o escopo do usuario e nao pode
-- calcular "o ultimo dia DELE". A solucao correta e trazer uma janela
-- recente (em dias de calendario) e deixar o cliente, apos o recorte RLS,
-- escolher o ultimo dia / os 7 dias do escopo.
--
-- Comportamento:
--   * p_dias_recentes NULL (default) -> MES INTEIRO (= comportamento 041,
--     retrocompativel para qualquer outro consumidor).
--   * p_dias_recentes = N            -> janela [v_data_ref - (N-1) ..
--     v_data_ref], nunca antes do 1o dia do mes (clamp em mes-calendario).
--
-- Funcao continua SECURITY INVOKER, STABLE, mesma base e granularidade
-- (incl. categoria_codigo da 041). Migrations 037/038/041 sao imutaveis;
-- esta substitui a RPC via DROP + CREATE (a assinatura ganha um arg).
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- A assinatura muda (novo parametro): dropar a versao (INTEGER, INTEGER)
-- da 041 antes de recriar com o 3o argumento (default NULL).
DROP FUNCTION IF EXISTS obter_digitacao_diaria_detalhe(INTEGER, INTEGER);

CREATE OR REPLACE FUNCTION obter_digitacao_diaria_detalhe(
    p_mes INTEGER,
    p_ano INTEGER,
    p_dias_recentes INTEGER DEFAULT NULL
)
RETURNS TABLE (
    data_cadastro    DATE,
    regiao           TEXT,
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
        l.nome::TEXT                             AS loja,
        cp.grupo_dashboard::TEXT                 AS grupo_dashboard,
        cp.codigo::TEXT                          AS categoria_codigo,
        COUNT(*)                                 AS qtd_digitada,
        COALESCE(SUM(c.valor), 0)::NUMERIC(15,2) AS valor_digitado
    FROM public.contratos c
    LEFT JOIN public.lojas l                ON l.id  = c.loja_id
    LEFT JOIN public.regioes r              ON r.id  = l.regiao_id
    LEFT JOIN public.produtos p             ON p.id  = c.produto_id
    LEFT JOIN public.categorias_produto cp  ON cp.id = p.categoria_id
    WHERE c.data_cadastro >= v_data_inicio
      AND c.data_cadastro <= v_data_ref
    GROUP BY c.data_cadastro, r.nome, l.nome,
             cp.grupo_dashboard, cp.codigo
    ORDER BY c.data_cadastro, r.nome, l.nome,
             cp.grupo_dashboard, cp.codigo;
END;
$$;

COMMENT ON FUNCTION obter_digitacao_diaria_detalhe(INTEGER, INTEGER, INTEGER) IS
    'Digitacao diaria por regiao x loja x grupo_dashboard x '
    'categoria_codigo. p_dias_recentes NULL = mes inteiro (041); '
    'p_dias_recentes = N limita a janela aos ultimos N dias de '
    'calendario (clamp no 1o dia do mes), para os quadros Ultimo Dia / '
    'Ultimos 7 Dias sem trazer o mes todo. Mesma base do agregado '
    'obter_digitacao_diaria (contratos direto, todos os status, valor '
    'bruto). SECURITY INVOKER; recorte por perfil e client-side.';
