-- =====================================================
-- Migracao 055: remove 5 indices nao usados / redundantes de contratos
--
-- Contexto (continuacao do diagnostico de Disk IO Budget, 2026-07-08;
-- ver migration 054 e docs/agents/progress/2026-07-08-disk-io-*.md):
--
-- contratos acumula 1,39M updates para 200k inserts (ETL reescreve
-- linhas sem mudanca) e cada um dos 17 indices da tabela amplifica a
-- escrita de TODO update (WAL + paginas de indice + autovacuum).
-- Auditoria via pg_stat_user_indexes (contadores desde fev/2026):
--
--   indice                              idx_scan   veredito
--   ---------------------------------   --------   -----------------------
--   idx_contratos_loja_data_cadastro           0   040 previa "derrubar se
--   idx_contratos_periodo_loja                 6   nao usado". A premissa
--                                                  (RLS server-side inje-
--                                                  tando loja_id IN (...))
--                                                  nao ocorre: o app usa
--                                                  chave unica sem JWT por
--                                                  usuario — o filtro por
--                                                  loja e client-side
--                                                  (aplicar_rls).
--   idx_contratos_periodo_id               1.040   prefixo redundante —
--                                                  idx_contratos_periodo_
--                                                  status_pag lidera por
--                                                  periodo_id; scans migram
--                                                  para o composto.
--   idx_contratos_data_cadastro            1.783   prefixo redundante —
--                                                  idx_contratos_cadastro_
--                                                  status lidera por
--                                                  data_cadastro.
--   idx_contratos_status_banco                 3   o parcial idx_contratos_
--                                                  status_banco_cancelado
--                                                  cobre o caso real.
--
-- Risco baixo: contratos tem 68 MB (inteiro em shared_buffers) — plano
-- que eventualmente perdesse o indice degrada para scan EM MEMORIA,
-- sem voltar a tocar disco. Reversivel: recriar (comandos ao final).
--
-- ⚠️  LOCK: DROP INDEX adquire ACCESS EXCLUSIVE na tabela por instantes
-- (bloqueia leituras/escritas durante o drop — nesta tabela, subsegundo
-- por indice). Preferir janela de baixo movimento. Nao se usa
-- CONCURRENTLY pelo mesmo motivo da 040: o SQL Editor roda em bloco
-- transacional (ERRO 25001).
--
-- Schema-qualificado de proposito: existe um clone vazio de contratos
-- em outro schema com indices homonimos (achado da auditoria) — o alvo
-- aqui e APENAS public.
--
-- Executar no Supabase SQL Editor. Requer 040 aplicada.
-- =====================================================


DROP INDEX IF EXISTS public.idx_contratos_loja_data_cadastro;
DROP INDEX IF EXISTS public.idx_contratos_periodo_loja;
DROP INDEX IF EXISTS public.idx_contratos_periodo_id;
DROP INDEX IF EXISTS public.idx_contratos_data_cadastro;
DROP INDEX IF EXISTS public.idx_contratos_status_banco;


-- ===========================================
-- Verificacao
--
--   SELECT indexrelname FROM pg_stat_user_indexes
--   WHERE schemaname = 'public' AND relname = 'contratos'
--   ORDER BY indexrelname;
--   -- Esperado: 12 indices, sem os 5 acima.
--
-- Acompanhar por alguns dias (queries do dashboard nao devem
-- regredir; com a tabela em RAM, nada deve mudar visivelmente):
--
--   SELECT LEFT(query, 100), calls,
--          ROUND(mean_exec_time::numeric, 1) AS media_ms
--   FROM extensions.pg_stat_statements
--   ORDER BY mean_exec_time DESC LIMIT 10;
-- ===========================================


-- ===========================================
-- Reversao (se algum plano regredir — recriar o(s) afetado(s)):
--
--   CREATE INDEX idx_contratos_periodo_id
--       ON public.contratos (periodo_id);
--   CREATE INDEX idx_contratos_data_cadastro
--       ON public.contratos (data_cadastro);
--   CREATE INDEX idx_contratos_status_banco
--       ON public.contratos (status_banco);
--   CREATE INDEX idx_contratos_periodo_loja
--       ON public.contratos (periodo_id, loja_id);
--   CREATE INDEX idx_contratos_loja_data_cadastro
--       ON public.contratos (loja_id, data_cadastro);
-- ===========================================
