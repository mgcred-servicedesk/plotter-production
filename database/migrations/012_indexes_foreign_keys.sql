-- =====================================================
-- Migracao 012: Indices em FKs sem cobertura
--
-- Objetivo: resolver 5 INFOs do tipo
-- "unindexed_foreign_keys" do Supabase Linter.
--
-- Por que importa:
--   - Sem indice, DELETE/UPDATE em tabela pai
--     (lojas, regioes) faz seq scan na tabela
--     filha para validar FK.
--   - JOINs filtrando por estes campos tambem
--     sao penalizados.
--   - Acelera UPSERTs do "angry-man" quando ha
--     cascata em lojas/regioes.
--
-- Tabelas/FKs cobertas:
--   1. consultores  (loja_id)
--   2. lojas        (regiao_id)
--   3. metas        (loja_id)
--   4. supervisores (loja_id)
--   5. supervisores (regiao_id)
--
-- Idempotente. Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. consultores.loja_id
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_consultores_loja_id
    ON consultores (loja_id);


-- ===========================================
-- 2. lojas.regiao_id
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_lojas_regiao_id
    ON lojas (regiao_id);


-- ===========================================
-- 3. metas.loja_id
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_metas_loja_id
    ON metas (loja_id);


-- ===========================================
-- 4. supervisores.loja_id
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_supervisores_loja_id
    ON supervisores (loja_id);


-- ===========================================
-- 5. supervisores.regiao_id
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_supervisores_regiao_id
    ON supervisores (regiao_id);


-- ===========================================
-- Validacao manual (apos executar)
-- ===========================================
-- SELECT
--     i.indexname,
--     i.tablename,
--     pg_size_pretty(pg_relation_size(i.indexname::regclass)) AS size
-- FROM pg_indexes i
-- WHERE i.indexname IN (
--     'idx_consultores_loja_id',
--     'idx_lojas_regiao_id',
--     'idx_metas_loja_id',
--     'idx_supervisores_loja_id',
--     'idx_supervisores_regiao_id'
-- );
--
-- Esperado: 5 linhas com tamanho pequeno (kB).
