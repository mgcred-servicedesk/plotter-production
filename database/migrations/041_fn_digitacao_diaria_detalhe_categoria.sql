-- =====================================================
-- Migracao 041: RPC obter_digitacao_diaria_detalhe expoe categoria_codigo
--
-- Objetivo: estender a migration 038 para que a DIGITACAO DIARIA
-- detalhada tambem retorne ``categoria_codigo`` (= categorias_produto.codigo).
-- Assim o dashboard pode DESMEMBRAR o grupo_dashboard 'PACK' em colunas
-- granulares (FGTS, ANT_BENEF, CNC_13) no quadro "Digitação do Último
-- Dia", do mesmo modo que ja e possivel em An. por Produto / Cancelados
-- (que carregam categoria_codigo direto dos contratos).
--
-- A funcao continua lendo public.contratos DIRETO, TODOS os status,
-- janela MES-CALENDARIO, e continua como SECURITY INVOKER herdando a
-- RLS de contratos. A soma do detalhe ainda bate com o agregado do
-- mesmo dia.
--
-- Granularidade nova: (data_cadastro, regiao, loja, grupo_dashboard,
-- categoria_codigo). Para nao quebrar consumidores existentes, retorna
-- TANTO grupo_dashboard quanto categoria_codigo.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- RPC: obter_digitacao_diaria_detalhe
-- 1 linha por (dia, regiao, loja, grupo_dashboard, categoria_codigo)
-- com >= 1 contrato.
-- ===========================================

-- Necessario porque o tipo de retorno (OUT parameters) mudou em
-- relacao a migration 038: adicionamos a coluna ``categoria_codigo``.
DROP FUNCTION IF EXISTS obter_digitacao_diaria_detalhe(INTEGER, INTEGER);

CREATE OR REPLACE FUNCTION obter_digitacao_diaria_detalhe(
    p_mes INTEGER,
    p_ano INTEGER
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

COMMENT ON FUNCTION obter_digitacao_diaria_detalhe(INTEGER, INTEGER) IS
    'Digitacao diaria por regiao x loja x grupo_dashboard x '
    'categoria_codigo: mesma base do agregado obter_digitacao_diaria '
    '(contratos direto, todos os status, janela mes-calendario, valor '
    'bruto), apenas com granularidade dia x dimensao x produto. A soma '
    'do detalhe == agregado. So agregados; SECURITY INVOKER herda a RLS '
    'de contratos.';
