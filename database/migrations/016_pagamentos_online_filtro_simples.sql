-- =====================================================
-- Migracao 016: simplificacao do filtro de pagamentos online
--
-- Contexto:
-- A migration 014 criou `v_pagamentos_online_efetivo` com
-- triplo filtro (Status='Concluída' AND Situacao='Concluída'
-- AND Agrupamento='Paga'). Apos validacao com dados reais
-- (smoke test em 2026-05-22), constatamos que `Agrupamento='Paga'`
-- ja implica pagamento efetivado para os grupos importados
-- (`Antecipação em Conta` e `Crédito na Conta`) — Status e
-- Situacao sao redundantes.
--
-- Mais critico: no extrator DNA observado, propostas com
-- `Agrupamento='Paga'` chegavam com Status/Situacao
-- diferentes de 'Concluída' em momentos transitorios, e
-- ficavam excluidas indevidamente do dashboard.
--
-- Esta migration:
--   1. Substitui a view por uma versao sem o filtro de
--      Status/Situacao.
--   2. Troca o indice composto `idx_pagamentos_online_triplo`
--      por `idx_pagamentos_online_agrupamento` (volume de
--      ~500-700 linhas torna o ganho irrelevante; e por
--      coerencia semantica com o filtro real).
--
-- Reversao:
--   Re-aplicar a definicao original da migration 014
--   (CREATE OR REPLACE VIEW com triplo filtro + recriar
--   o indice composto).
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. View simplificada
-- ===========================================

CREATE OR REPLACE VIEW public.v_pagamentos_online_efetivo
WITH (security_invoker = on)
AS
SELECT
    p.proposta,
    p.data_implantacao,
    p.data_status,
    p.cliente,
    p.grupo_produto,
    p.produto,
    p.loja_codigo,
    l.id            AS loja_id,
    l.nome          AS loja_nome,
    l.regiao_id,
    p.usuario_nome,
    p.valor_liquido_digitado,
    p.valor_liquido_aprovado,
    p.valor_seguro_aprovado,
    CASE
        WHEN COALESCE(p.valor_liquido_aprovado, 0) = 0
            THEN COALESCE(p.valor_liquido_digitado, 0)
        ELSE COALESCE(p.valor_liquido_aprovado, 0)
             + COALESCE(p.valor_seguro_aprovado, 0)
    END             AS valor_producao,
    p.imported_at
FROM public.pagamentos_online p
LEFT JOIN public.lojas l
    ON l.codigo_dna = p.loja_codigo
WHERE p.agrupamento = 'Paga'
  AND NOT EXISTS (
      SELECT 1 FROM public.contratos c
      WHERE c.num_proposta = p.proposta
        AND c.status_pagamento_cliente = 'PAGO AO CLIENTE'
  );

COMMENT ON VIEW public.v_pagamentos_online_efetivo IS
    'Propostas pagas "online" (estimativa do dia) com '
    'valor_producao calculado e exclusao das ADEs que '
    'ja entraram no consolidado (contratos). Filtro: '
    'agrupamento=''Paga''. security_invoker=on.';


-- ===========================================
-- 2. Indice — substitui o composto por simples
-- ===========================================

DROP INDEX IF EXISTS public.idx_pagamentos_online_triplo;

CREATE INDEX IF NOT EXISTS idx_pagamentos_online_agrupamento
    ON public.pagamentos_online (agrupamento);


-- ===========================================
-- 3. Validacao pos-migracao
-- ===========================================
-- Sanity check:
--
--   SELECT pg_get_viewdef('public.v_pagamentos_online_efetivo', true);
--   -- WHERE deve conter apenas: p.agrupamento = 'Paga' AND NOT EXISTS ...
--
--   SELECT count(*), sum(valor_producao)
--   FROM v_pagamentos_online_efetivo;
--   -- Deve bater com:
--   --   SELECT count(*), sum(...) FROM pagamentos_online
--   --   WHERE agrupamento='Paga'
--   --     AND NOT EXISTS (SELECT 1 FROM contratos c
--   --                     WHERE c.num_proposta=p.proposta
--   --                       AND c.status_pagamento_cliente='PAGO AO CLIENTE');
