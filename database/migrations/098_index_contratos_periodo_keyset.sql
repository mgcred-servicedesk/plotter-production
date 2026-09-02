-- =====================================================
-- Migracao 098: indice (periodo_id, id) para a paginacao keyset
--
-- Contexto (statement_timeout 57014 intermitente no dashboard,
-- 2026-09-01; ver docs/agents/progress/2026-09-01-timeout-keyset-
-- contratos.md):
--
-- A carga de contratos pagos morreu com 57014 (canceling statement due
-- to statement timeout) em `_fetch_contratos_pagos`. Medicao logo apos,
-- com o banco em repouso, mostrou a query SAUDAVEL — 08/2026, 5.630
-- linhas em 6 paginas: 2,32s · 2,02s · 1,19s · 1,35s · 1,39s · 1,13s
-- (~9,4s de banco para UM mes). Logo, nao e regressao: a
-- v_contratos_dashboard nao muda desde a 067.
--
-- O que a medicao expos foi a MARGEM. Tempos da 1a pagina por periodo,
-- sem correlacao com volume — assinatura de contencao, nao de plano
-- ruim (o ETL do angry-man escreve em contratos em paralelo):
--
--   05/2026:  5.627 linhas -> 4,13s      01/2026:  7.043 linhas -> 0,61s
--   08/2026:  5.630 linhas -> 2,66s      03/2026: 11.442 linhas -> 1,14s
--
-- 7x de variancia para volumes parecidos, contra um teto de 15s por
-- statement. Sob rajada de escrita, a pagina estoura.
--
-- CAUSA DO CUSTO — o keyset nao eliminou o sort. Nenhum indice atual
-- lidera por (periodo_id, id): a 055 dropou idx_contratos_periodo_id
-- (prefixo redundante) e idx_contratos_periodo_loja (nao usado), e o
-- sobrevivente idx_contratos_periodo_status_pag tem
-- status_pagamento_cliente na 2a posicao — nao serve para ordenar por
-- id. O planner entao le o periodo inteiro e ORDENA por id a cada
-- pagina. O custo decrescente medido acima (2,32 -> 1,13s) e a
-- impressao digital disso: cada pagina reordena o conjunto RESTANTE.
--
-- Com (periodo_id, id) o predicado do keyset
--
--     WHERE periodo_id = X AND id > <cursor> ORDER BY id LIMIT 1000
--
-- vira range scan puro: o indice ja entrega em ordem de id, o cursor
-- vira ponto de partida e o LIMIT para de ler. Sem sort node — some o
-- trabalho de CPU repetido E o spill de temp files que a 054 apontou
-- como um dos dois vetores de dreno do Disk IO Budget (a propria 054
-- nomeia "as queries paginadas de v_contratos_dashboard" como
-- spillers; work_mem=12MB fez o sort caber em RAM, esta migration
-- remove o sort).
--
-- ⚠️  TRADE-OFF (a 055 e explicita): contratos acumula 1,39M updates
-- para 200k inserts e cada indice amplifica a escrita de todo update
-- (WAL + paginas de indice + autovacuum) — foi por isso que 5 indices
-- cairam. Este entra na direcao contraria e a justificativa e outra:
-- nao e um indice especulativo "por via das duvidas", e o indice que
-- casa EXATAMENTE com o unico padrao de acesso do loader mais quente
-- do dashboard, e o que ele economiza (sort + temp files, ou seja,
-- ESCRITA) e da mesma moeda que ele custa. Se a auditoria de
-- pg_stat_user_indexes mostrar idx_scan baixo depois de algumas
-- semanas, dropar como a 055 fez.
--
-- ⚠️  LOCK: CREATE INDEX adquire SHARE — bloqueia ESCRITA (o ETL) e
-- permite leitura, por alguns segundos nesta tabela (68 MB, inteira em
-- shared_buffers). Preferir janela sem importacao do angry-man rodando.
-- Nao se usa CONCURRENTLY pelo mesmo motivo da 040/055: o SQL Editor
-- roda em bloco transacional (ERRO 25001).
--
-- Schema-qualificado de proposito (mesmo motivo da 055: existe um clone
-- vazio de contratos em outro schema com indices homonimos).
--
-- Executar no Supabase SQL Editor.
-- =====================================================


CREATE INDEX IF NOT EXISTS idx_contratos_periodo_keyset
    ON public.contratos (periodo_id, id);

COMMENT ON INDEX public.idx_contratos_periodo_keyset IS
    'Paginacao keyset de v_contratos_dashboard (_paginar_keyset em '
    'src/dashboard/loaders.py): WHERE periodo_id = X AND id > cursor '
    'ORDER BY id LIMIT N. Existe para eliminar o sort node por pagina — '
    'nao remover sem antes conferir que o loader mudou de padrao. '
    'Substitui tambem o prefixo periodo_id que a 055 dropou.';


-- ===========================================
-- Verificacao
--
-- 1. Plano SEM sort node (o teste que importa). Trocar o UUID por um
--    periodo real (SELECT id FROM periodos ORDER BY ano DESC, mes DESC
--    LIMIT 1):
--
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT id FROM public.contratos
--   WHERE periodo_id = '<PERIODO_UUID>'
--   ORDER BY id LIMIT 1000;
--   -- Esperado: Index Scan using idx_contratos_periodo_keyset.
--   -- NAO deve aparecer nenhum "Sort" nem "Sort Method: ... Disk".
--
-- 2. Uso real, depois de algumas cargas do dashboard:
--
--   SELECT indexrelname, idx_scan
--   FROM pg_stat_user_indexes
--   WHERE schemaname = 'public' AND relname = 'contratos'
--   ORDER BY idx_scan DESC;
--   -- Esperado: idx_contratos_periodo_keyset subindo a cada carga.
--
-- 3. Temp files parando de crescer (continuidade da 054):
--
--   SELECT temp_files, pg_size_pretty(temp_bytes) AS temp_total
--   FROM pg_stat_database WHERE datname = current_database();
-- ===========================================


-- ===========================================
-- Reversao:
--
--   DROP INDEX IF EXISTS public.idx_contratos_periodo_keyset;
-- ===========================================
