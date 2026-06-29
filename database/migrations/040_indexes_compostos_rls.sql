-- =====================================================
-- Migracao 040: indices compostos para o filtro RLS por loja
--
-- Contexto:
-- O app NAO filtra contratos por loja/regiao/consultor no SQL —
-- esse afunilamento e feito (a) client-side por aplicar_rls e
-- (b) server-side pela policy pol_contratos_select (migration 011),
-- que para perfis nao-admin acrescenta a TODA query de contratos:
--   * gerente_comercial / supervisor -> AND loja_id IN (...)
--   * consultor                      -> AND consultor_id IN (...)
--
-- Com isso, as cargas mais comuns combinam dois predicados que hoje
-- nao tem indice composto de suporte:
--   * pagos / em_analise (view): periodo_id  +  loja_id (RLS)
--   * digitacao diaria (RPC):    data_cadastro (range) + loja_id (RLS)
-- Os indices atuais sao (periodo_id, status_pagamento_cliente),
-- (data_cadastro, status..., status...) e os single-column de FK —
-- nenhum lidera por (periodo_id, loja_id) nem (loja_id, data_cadastro).
--
-- ⚠️  HIPOTESE A VALIDAR:
-- O ganho destes indices depende da seletividade do escopo (quantas
-- lojas o perfil enxerga) e do plano escolhido pelo planner. Rodar os
-- EXPLAIN ANALYZE da secao final ANTES de considerar definitivo;
-- se algum nao for usado, derrubar com DROP INDEX (reversivel).
--
-- ⚠️  LOCK: CREATE INDEX (sem CONCURRENTLY) adquire um lock que
-- BLOQUEIA ESCRITAS em contratos durante a construcao (leituras
-- seguem). Em contratos isso deve ser na casa de segundos — rode em
-- JANELA DE BAIXO MOVIMENTO. Optou-se pela forma NAO-concorrente
-- porque o Supabase SQL Editor envolve os comandos em uma transacao
-- e CREATE INDEX CONCURRENTLY nao pode rodar em bloco transacional
-- (ERRO 25001). Idempotente via IF NOT EXISTS.
--
-- Alternativa SEM bloqueio de escrita (apenas se tiver conexao
-- DIRETA via psql, em autocommit, fora de transacao):
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contratos_periodo_loja
--       ON public.contratos (periodo_id, loja_id);
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contratos_loja_data_cadastro
--       ON public.contratos (loja_id, data_cadastro);
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. (periodo_id, loja_id)
-- Cobre o scan de v_contratos_dashboard / v_contratos_em_analise
-- (filtro .eq periodo_id) quando a RLS de gerente/supervisor
-- acrescenta loja_id IN (...).
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_contratos_periodo_loja
    ON public.contratos (periodo_id, loja_id);


-- ===========================================
-- 2. (loja_id, data_cadastro)
-- Cobre as RPCs de digitacao diaria (range em data_cadastro) sob
-- RLS de gerente/supervisor (loja_id IN (...)). Lidera por loja_id
-- por ser o predicado de igualdade/IN; data_cadastro fecha o range.
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_contratos_loja_data_cadastro
    ON public.contratos (loja_id, data_cadastro);


-- ===========================================
-- Validacao de performance (EXPLAIN ANALYZE)
--
-- Rodar AUTENTICADO como um perfil nao-admin (gerente/supervisor)
-- para que a policy RLS injete o filtro de loja. Como admin/gestor
-- a policy NAO filtra por loja e estes indices nao serao exercitados.
--
--   -- pagos (substitua <PERIODO_UUID> por um periodo real):
--   EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
--   SELECT * FROM v_contratos_dashboard
--   WHERE periodo_id = '<PERIODO_UUID>';
--
--   -- digitacao diaria:
--   EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
--   SELECT * FROM obter_digitacao_diaria(6, 2026);
--
-- Procure por "Index Scan using idx_contratos_periodo_loja" /
-- "idx_contratos_loja_data_cadastro". Se o planner ignorar (ex.:
-- escopo pouco seletivo, seq scan mais barato), derrube o indice:
--
--   DROP INDEX IF EXISTS idx_contratos_periodo_loja;
--   DROP INDEX IF EXISTS idx_contratos_loja_data_cadastro;
-- ===========================================
