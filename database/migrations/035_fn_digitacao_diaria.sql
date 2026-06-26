-- =====================================================
-- Migracao 035: RPC obter_digitacao_diaria
--
-- Objetivo: expor a DIGITACAO DIARIA (volume operacional)
-- do mes selecionado, contando TODA linha de `contratos`
-- com data_cadastro no mes, em QUALQUER status (sem excluir
-- cancelados, em analise, etc.). E uma visao de esforco de
-- digitacao, nao de producao paga.
--
-- Por isso le `public.contratos` DIRETO, e nao as views do
-- dashboard: v_contratos_dashboard e PAGOS-ONLY e demais
-- views excluem linhas por status. Aqui nenhuma linha do mes
-- pode ficar de fora.
--
-- Janela = MES-CALENDARIO (NAO a janela movel de 30 dias da
-- migration 003):
--   * data de referencia = hoje, se (p_mes, p_ano) for o mes
--     vigente -> acumula dia a dia ate hoje;
--   * senao = ultimo dia do mes selecionado -> mes inteiro.
--   Conta data_cadastro entre o 1o dia do mes e a data de ref.
--
-- valor_digitado = SUM(valor) BRUTO de contratos. Digitacao e
-- volume operacional: SEM ajuste por conta_valor.
--
-- Postura de seguranca: a RPC retorna SOMENTE agregados por
-- dia (contagem e soma). NUNCA expoe nome do cliente, CPF ou
-- qualquer dado individual. Roda como SECURITY INVOKER, logo
-- HERDA a policy pol_contratos_select (migration 011) sobre
-- `contratos`: o agregado ja sai filtrado por perfil do
-- usuario chamador, sem vazamento entre perfis.
--
-- Segue o mesmo padrao (SECURITY INVOKER implicito, search_path
-- vazio, plpgsql STABLE) da RPC obter_contratos_cancelados
-- (migration 003).
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- RPC: obter_digitacao_diaria
-- 1 linha por dia com >= 1 contrato no mes.
-- ===========================================

CREATE OR REPLACE FUNCTION obter_digitacao_diaria(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    data_cadastro   DATE,
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
    -- senao ultimo dia do mes selecionado (mes inteiro)
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
        c.data_cadastro                       AS data_cadastro,
        COUNT(*)                              AS qtd_digitada,
        COALESCE(SUM(c.valor), 0)::NUMERIC(15,2) AS valor_digitado
    FROM public.contratos c
    WHERE c.data_cadastro >= v_data_inicio
      AND c.data_cadastro <= v_data_ref
    GROUP BY c.data_cadastro
    ORDER BY c.data_cadastro;
END;
$$;

COMMENT ON FUNCTION obter_digitacao_diaria(INTEGER, INTEGER) IS
    'Digitacao diaria do mes (volume operacional): le contratos '
    'direto, todos os status, agrupando por data_cadastro. Janela '
    'mes-calendario (mes vigente -> ate hoje; historico -> mes '
    'inteiro). valor bruto, sem conta_valor. So agregados; '
    'SECURITY INVOKER herda a RLS de contratos por perfil.';
