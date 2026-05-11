-- =====================================================
-- Migracao 011: Consolidar policies RLS (performance)
--
-- Objetivo: resolver 24 warnings do tipo
-- "multiple_permissive_policies" do Supabase Linter.
--
-- Causa: tabelas com policy FOR ALL (admin) + policies
-- FOR SELECT (outros perfis) -> Postgres avalia ambas
-- em OR para SELECT, executando obter_perfil_atual()
-- multiplas vezes por linha.
--
-- Estrategia:
--   1. Substituir 'pol_X_admin FOR ALL' por policies
--      separadas para INSERT/UPDATE/DELETE (admin only).
--   2. Consolidar SELECT em uma unica policy com OR
--      das condicoes de cada perfil.
--   3. Usar (SELECT obter_perfil_atual()) para forcar
--      avaliacao via initplan (1x por query, nao por
--      linha) — otimizacao recomendada pelo Supabase.
--
-- Comportamento RLS: identico ao atual (mesma logica,
-- so consolidada). Recomenda-se testar cada perfil
-- (admin, gestor, gerente, supervisor, consultor)
-- apos aplicar.
--
-- Impacto em "angry-man": ZERO. service_role tem
-- BYPASSRLS, policies nao executam.
--
-- Idempotente. Executar no Supabase SQL Editor.
-- Tabelas afetadas: contratos, metas, feriados,
-- usuarios, usuario_escopos.
-- =====================================================


-- ===========================================
-- 1. CONTRATOS
-- ===========================================

DROP POLICY IF EXISTS pol_contratos_admin       ON contratos;
DROP POLICY IF EXISTS pol_contratos_gestor      ON contratos;
DROP POLICY IF EXISTS pol_contratos_gerente     ON contratos;
DROP POLICY IF EXISTS pol_contratos_supervisor  ON contratos;
DROP POLICY IF EXISTS pol_contratos_consultor   ON contratos;
DROP POLICY IF EXISTS pol_contratos_select      ON contratos;
DROP POLICY IF EXISTS pol_contratos_admin_insert ON contratos;
DROP POLICY IF EXISTS pol_contratos_admin_update ON contratos;
DROP POLICY IF EXISTS pol_contratos_admin_delete ON contratos;

-- Policy unica de SELECT (consolida 5 perfis)
CREATE POLICY pol_contratos_select
    ON contratos FOR SELECT
    USING (
        (SELECT obter_perfil_atual()) = 'admin'
        OR (SELECT obter_perfil_atual()) = 'gestor'
        OR (
            (SELECT obter_perfil_atual()) = 'gerente_comercial'
            AND loja_id IN (
                SELECT l.id FROM lojas l
                JOIN usuario_escopos ue
                    ON ue.regiao_id = l.regiao_id
                WHERE ue.usuario_id = (SELECT obter_usuario_atual_id())
            )
        )
        OR (
            (SELECT obter_perfil_atual()) = 'supervisor'
            AND loja_id IN (
                SELECT ue.loja_id FROM usuario_escopos ue
                WHERE ue.usuario_id = (SELECT obter_usuario_atual_id())
            )
        )
        OR (
            (SELECT obter_perfil_atual()) = 'consultor'
            AND consultor_id IN (
                SELECT ue.consultor_id FROM usuario_escopos ue
                WHERE ue.usuario_id = (SELECT obter_usuario_atual_id())
            )
        )
    );

-- Policies de escrita: admin only (substituem o FOR ALL)
CREATE POLICY pol_contratos_admin_insert
    ON contratos FOR INSERT
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_contratos_admin_update
    ON contratos FOR UPDATE
    USING ((SELECT obter_perfil_atual()) = 'admin')
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_contratos_admin_delete
    ON contratos FOR DELETE
    USING ((SELECT obter_perfil_atual()) = 'admin');


-- ===========================================
-- 2. METAS
-- ===========================================

DROP POLICY IF EXISTS pol_metas_admin       ON metas;
DROP POLICY IF EXISTS pol_metas_gestor      ON metas;
DROP POLICY IF EXISTS pol_metas_gerente     ON metas;
DROP POLICY IF EXISTS pol_metas_supervisor  ON metas;
DROP POLICY IF EXISTS pol_metas_consultor   ON metas;
DROP POLICY IF EXISTS pol_metas_select      ON metas;
DROP POLICY IF EXISTS pol_metas_admin_insert ON metas;
DROP POLICY IF EXISTS pol_metas_admin_update ON metas;
DROP POLICY IF EXISTS pol_metas_admin_delete ON metas;

CREATE POLICY pol_metas_select
    ON metas FOR SELECT
    USING (
        (SELECT obter_perfil_atual()) = 'admin'
        OR (SELECT obter_perfil_atual()) = 'gestor'
        OR (
            (SELECT obter_perfil_atual()) = 'gerente_comercial'
            AND loja_id IN (
                SELECT l.id FROM lojas l
                JOIN usuario_escopos ue
                    ON ue.regiao_id = l.regiao_id
                WHERE ue.usuario_id = (SELECT obter_usuario_atual_id())
            )
        )
        OR (
            (SELECT obter_perfil_atual()) = 'supervisor'
            AND loja_id IN (
                SELECT ue.loja_id FROM usuario_escopos ue
                WHERE ue.usuario_id = (SELECT obter_usuario_atual_id())
            )
        )
        OR (
            (SELECT obter_perfil_atual()) = 'consultor'
            AND loja_id IN (
                SELECT c.loja_id
                FROM consultores c
                JOIN usuario_escopos ue
                    ON ue.consultor_id = c.id
                WHERE ue.usuario_id = (SELECT obter_usuario_atual_id())
            )
        )
    );

CREATE POLICY pol_metas_admin_insert
    ON metas FOR INSERT
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_metas_admin_update
    ON metas FOR UPDATE
    USING ((SELECT obter_perfil_atual()) = 'admin')
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_metas_admin_delete
    ON metas FOR DELETE
    USING ((SELECT obter_perfil_atual()) = 'admin');


-- ===========================================
-- 3. FERIADOS
-- ===========================================

DROP POLICY IF EXISTS pol_feriados_admin        ON feriados;
DROP POLICY IF EXISTS pol_feriados_leitura      ON feriados;
DROP POLICY IF EXISTS pol_feriados_admin_insert ON feriados;
DROP POLICY IF EXISTS pol_feriados_admin_update ON feriados;
DROP POLICY IF EXISTS pol_feriados_admin_delete ON feriados;

-- Leitura publica (necessaria para calculo de dias uteis)
CREATE POLICY pol_feriados_leitura
    ON feriados FOR SELECT
    USING (true);

-- Escrita: admin only
CREATE POLICY pol_feriados_admin_insert
    ON feriados FOR INSERT
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_feriados_admin_update
    ON feriados FOR UPDATE
    USING ((SELECT obter_perfil_atual()) = 'admin')
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_feriados_admin_delete
    ON feriados FOR DELETE
    USING ((SELECT obter_perfil_atual()) = 'admin');


-- ===========================================
-- 4. USUARIOS
-- ===========================================

DROP POLICY IF EXISTS pol_usuarios_admin        ON usuarios;
DROP POLICY IF EXISTS pol_usuarios_proprio      ON usuarios;
DROP POLICY IF EXISTS pol_usuarios_select       ON usuarios;
DROP POLICY IF EXISTS pol_usuarios_admin_insert ON usuarios;
DROP POLICY IF EXISTS pol_usuarios_admin_update ON usuarios;
DROP POLICY IF EXISTS pol_usuarios_admin_delete ON usuarios;

-- SELECT: admin OU o proprio usuario
CREATE POLICY pol_usuarios_select
    ON usuarios FOR SELECT
    USING (
        (SELECT obter_perfil_atual()) = 'admin'
        OR id = (SELECT obter_usuario_atual_id())
    );

-- Escrita: admin only
CREATE POLICY pol_usuarios_admin_insert
    ON usuarios FOR INSERT
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_usuarios_admin_update
    ON usuarios FOR UPDATE
    USING ((SELECT obter_perfil_atual()) = 'admin')
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_usuarios_admin_delete
    ON usuarios FOR DELETE
    USING ((SELECT obter_perfil_atual()) = 'admin');


-- ===========================================
-- 5. USUARIO_ESCOPOS
-- ===========================================

DROP POLICY IF EXISTS pol_escopos_admin        ON usuario_escopos;
DROP POLICY IF EXISTS pol_escopos_proprio      ON usuario_escopos;
DROP POLICY IF EXISTS pol_escopos_select       ON usuario_escopos;
DROP POLICY IF EXISTS pol_escopos_admin_insert ON usuario_escopos;
DROP POLICY IF EXISTS pol_escopos_admin_update ON usuario_escopos;
DROP POLICY IF EXISTS pol_escopos_admin_delete ON usuario_escopos;

-- SELECT: admin OU escopos do proprio usuario
CREATE POLICY pol_escopos_select
    ON usuario_escopos FOR SELECT
    USING (
        (SELECT obter_perfil_atual()) = 'admin'
        OR usuario_id = (SELECT obter_usuario_atual_id())
    );

-- Escrita: admin only
CREATE POLICY pol_escopos_admin_insert
    ON usuario_escopos FOR INSERT
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_escopos_admin_update
    ON usuario_escopos FOR UPDATE
    USING ((SELECT obter_perfil_atual()) = 'admin')
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_escopos_admin_delete
    ON usuario_escopos FOR DELETE
    USING ((SELECT obter_perfil_atual()) = 'admin');


-- ===========================================
-- Validacao manual (apos executar)
-- ===========================================
-- Listar policies por tabela:
--
-- SELECT tablename, policyname, cmd
-- FROM pg_policies
-- WHERE tablename IN (
--     'contratos', 'metas', 'feriados',
--     'usuarios', 'usuario_escopos'
-- )
-- ORDER BY tablename, cmd, policyname;
--
-- Esperado: 1 policy de SELECT por tabela +
-- 3 policies de escrita (INSERT/UPDATE/DELETE).
--
-- Teste funcional: logar com cada perfil e
-- conferir que so ve dados esperados em
-- contratos e metas.
