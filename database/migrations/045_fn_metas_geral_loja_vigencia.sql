-- =====================================================
-- Migracao 045: RPC obter_metas_geral_loja
--               (metas GERAL/LOJA com regiao point-in-time)
--
-- Estagio 2 do rollout. O dashboard carregava as metas GERAL/LOJA
-- via embed PostgREST `lojas!inner(nome, regioes(nome))`, que
-- devolve sempre a regiao ATUAL da loja. O PostgREST nao faz join
-- temporal, entao nao ha como resolver a regiao vigente na
-- competencia da meta por embed. Esta RPC encapsula essa resolucao.
--
-- Retorna, para cada meta GERAL/LOJA do periodo (p_mes/p_ano):
--   * regiao       = regiao vigente na COMPETENCIA da meta
--                    (make_date(ano, mes, 1) contra loja_regiao_vigencia),
--                    casando com a atribuicao das vendas por data_cadastro
--                    na mesma fronteira (ex.: Jul/1);
--   * regiao_atual = regiao corrente da loja (organograma), p/ o
--                    recorte RLS client-side do gerente;
--   * loja_ativa   = lojas.ativo, p/ o filtro de mes corrente
--                    (loja recem-aberta entra; inativa nao) que hoje
--                    e feito no Python.
--
-- No-op ate o 1o remanejamento (mesma logica das views 044):
-- COALESCE(vigencia, l.regiao_id) devolve a regiao atual enquanto so
-- existir a linha de vigencia aberta desde 2020-01-01.
--
-- SECURITY INVOKER (implicito). Recorte por perfil e client-side
-- (aplicar_rls_metas). Objeto NOVO — nao substitui nada.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE OR REPLACE FUNCTION obter_metas_geral_loja(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    loja         TEXT,
    regiao       TEXT,     -- vigente na competencia (mes/ano)
    regiao_atual TEXT,     -- organograma atual (RLS)
    loja_ativa   BOOLEAN,
    nivel        TEXT,
    valor        NUMERIC(15,2)
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
    v_periodo_id UUID;
    v_ref_date   DATE := make_date(p_ano, p_mes, 1);
BEGIN
    SELECT pe.id INTO v_periodo_id
    FROM public.periodos pe
    WHERE pe.mes = p_mes AND pe.ano = p_ano;

    IF v_periodo_id IS NULL THEN
        RETURN;  -- periodo inexistente => resultado vazio
    END IF;

    RETURN QUERY
    SELECT
        l.nome::TEXT   AS loja,
        r.nome::TEXT   AS regiao,
        r_atual.nome::TEXT AS regiao_atual,
        l.ativo        AS loja_ativa,
        m.nivel::TEXT  AS nivel,
        m.valor        AS valor
    FROM public.metas m
    JOIN public.lojas l ON l.id = m.loja_id
    LEFT JOIN LATERAL (
        SELECT vig.regiao_id
        FROM public.loja_regiao_vigencia vig
        WHERE vig.loja_id = l.id
          AND v_ref_date >= vig.vigencia_inicio
          AND (vig.vigencia_fim IS NULL OR v_ref_date < vig.vigencia_fim)
        ORDER BY vig.vigencia_inicio DESC
        LIMIT 1
    ) rv ON true
    LEFT JOIN public.regioes r       ON r.id = COALESCE(rv.regiao_id, l.regiao_id)
    LEFT JOIN public.regioes r_atual ON r_atual.id = l.regiao_id
    WHERE m.periodo_id = v_periodo_id
      AND m.produto = 'GERAL'
      AND m.escopo  = 'LOJA';
END;
$$;

COMMENT ON FUNCTION obter_metas_geral_loja(INTEGER, INTEGER) IS
    'Metas GERAL/LOJA do periodo com regiao point-in-time. regiao = '
    'vigente na competencia (make_date(ano,mes,1) via '
    'loja_regiao_vigencia); regiao_atual = regiao corrente da loja '
    '(RLS client-side); loja_ativa = lojas.ativo (filtro de mes '
    'corrente no cliente). Recorte por perfil e client-side.';

GRANT EXECUTE ON FUNCTION obter_metas_geral_loja(INTEGER, INTEGER)
    TO anon, authenticated;
