-- ============================================================
-- Migracao 031: Reconquista — remover objetos da v1 (DESTRUTIVO)
--
-- Substituido pela v2 (028/029/030 + view v_reconquista + RPC
-- fn_importar_reconquista + tabela reconquista). Esta migracao
-- remove o modelo antigo (snapshots por envio + maciças + flags).
--
-- ATENCAO — IRREVERSIVEL:
--   * reconquista_snapshot (~6410 linhas de historico de envios)
--   * macicas (campanhas)
-- O historico de snapshots NAO e recuperavel apos o DROP. Faca
-- backup/export antes se quiser preservar o historico v1.
--
-- MANTIDO de proposito (NAO dropar):
--   * lojas.sucessora_id — usado pela RPC v2 fn_importar_reconquista
--     (COALESCE(sucessora_id, id)).
--   * lojas.ativo — atributo geral de loja; sem custo manter.
--
-- Depende de: 030_reconquista_v2_view.sql aplicada e validada.
-- Executar no Supabase SQL Editor APOS confirmar que nada mais
-- consome os objetos v1.
-- ============================================================

-- 1. Views v1 (algumas ja removidas em 026/027 — IF EXISTS) ----
DROP VIEW IF EXISTS v_reconquista_evolucao;
DROP VIEW IF EXISTS v_reconquista_indiferentes;
DROP VIEW IF EXISTS v_reconquista_resistentes;
DROP VIEW IF EXISTS v_reconquista_clientes;
DROP VIEW IF EXISTS v_reconquista_por_consultor;
DROP VIEW IF EXISTS v_reconquista_por_loja;
DROP VIEW IF EXISTS v_reconquista_ultimo;

-- 2. RPCs v1 ---------------------------------------------------
DROP FUNCTION IF EXISTS fn_macica_ativa(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS fn_upsert_macica(TEXT, TEXT, DATE, DATE, NUMERIC);
DROP FUNCTION IF EXISTS fn_importar_reconquista_snapshot(UUID, DATE, JSONB);

-- 3. Tabelas v1 (snapshot referencia macicas — dropar antes) ---
DROP TABLE IF EXISTS reconquista_snapshot;
DROP TABLE IF EXISTS macicas;
