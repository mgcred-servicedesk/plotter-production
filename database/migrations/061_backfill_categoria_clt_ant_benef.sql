-- =====================================================
-- Migracao 061: backfill de categoria_id para os tipos
-- renomeados na origem: CONSIG PRIV -> CLT e
-- CNC ANT -> ANT. DE BENEF.
--
-- Contexto: em 2026-07-09 as planilhas de origem trocaram a
-- nomenclatura dos tipos de produto. O upsert do ETL
-- (repo angry-man) sobrescreveu produtos.tipo com os nomes
-- novos, mas o mapeamento tipo -> categoria_id do ETL nao
-- conhece 'CLT' nem 'ANT. DE BENEF.' e gravou
-- categoria_id = NULL. Estado verificado no banco:
--
--   * 19 produtos com tipo = 'CLT'            (cat NULL)
--   *  1 produto  com tipo = 'ANT. DE BENEF.' (cat NULL)
--   * 12.818 contratos apontando para esses produtos,
--     todos sem categoria_codigo no dashboard (fora do
--     MIX/KPIs).
--
-- Mapeamento (identico ao dos nomes antigos):
--   CLT            -> CONSIG_PRIV (grupo_dashboard CLT)
--   ANT. DE BENEF. -> ANT_BENEF   (grupo_dashboard PACK)
--
-- ATENCAO — correcao na origem obrigatoria: produtos sofre
-- upsert integral a cada import do ETL (ver 060). Enquanto o
-- mapeamento do angry-man nao aprender os nomes novos, cada
-- import volta a gravar categoria_id = NULL e desfaz este
-- backfill. O fallback _TIPO_PARA_CATEGORIA em
-- src/dashboard/loaders.py cobre o dashboard nesse
-- meio-tempo, mas a correcao definitiva e no ETL.
--
-- Reversao:
--   UPDATE produtos SET categoria_id = NULL
--   WHERE tipo IN ('CLT', 'ANT. DE BENEF.');
--
-- Executar no Supabase SQL Editor.
-- =====================================================

UPDATE public.produtos AS p
SET categoria_id = cp.id
FROM public.categorias_produto AS cp
WHERE p.tipo = 'CLT'
  AND cp.codigo = 'CONSIG_PRIV'
  AND p.categoria_id IS DISTINCT FROM cp.id;

UPDATE public.produtos AS p
SET categoria_id = cp.id
FROM public.categorias_produto AS cp
WHERE p.tipo = 'ANT. DE BENEF.'
  AND cp.codigo = 'ANT_BENEF'
  AND p.categoria_id IS DISTINCT FROM cp.id;


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- SELECT p.tipo, cp.codigo, COUNT(*)
-- FROM produtos p
-- LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
-- WHERE p.tipo IN ('CLT', 'ANT. DE BENEF.')
-- GROUP BY p.tipo, cp.codigo;
-- Esperado:
--   ANT. DE BENEF. | ANT_BENEF   | 1
--   CLT            | CONSIG_PRIV | 19
--
-- Nenhum produto restante sem categoria nesses tipos:
-- SELECT COUNT(*) FROM produtos
-- WHERE tipo IN ('CLT', 'ANT. DE BENEF.')
--   AND categoria_id IS NULL;
-- Esperado: 0
-- =====================================================
