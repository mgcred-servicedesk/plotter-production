-- =====================================================
-- Migracao 008: RLS na tabela feriados
--
-- Objetivo: corrigir alerta de seguranca do Supabase
-- ("Table public.feriados is public, but RLS has not
-- been enabled"). Habilita RLS e cria policies seguindo
-- o mesmo padrao das tabelas de referencia (regioes,
-- lojas, produtos, etc.) definido em schema.sql.
--
-- Politica:
--   - Leitura: liberada para todos (necessaria para o
--     calculo de dias uteis em todos os perfis).
--   - Escrita (INSERT/UPDATE/DELETE): apenas admin,
--     consistente com a UI em feriados_mgmt.py.
--
-- Idempotente: pode ser reexecutado sem erro.
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Habilita Row Level Security
-- ===========================================

ALTER TABLE feriados ENABLE ROW LEVEL SECURITY;


-- ===========================================
-- 2. Policy: leitura liberada
-- ===========================================

DROP POLICY IF EXISTS pol_feriados_leitura ON feriados;

CREATE POLICY pol_feriados_leitura
    ON feriados FOR SELECT
    USING (true);


-- ===========================================
-- 3. Policy: gerenciamento apenas por admin
-- ===========================================

DROP POLICY IF EXISTS pol_feriados_admin ON feriados;

CREATE POLICY pol_feriados_admin
    ON feriados FOR ALL
    USING (obter_perfil_atual() = 'admin')
    WITH CHECK (obter_perfil_atual() = 'admin');
