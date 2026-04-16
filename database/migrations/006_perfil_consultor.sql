-- =====================================================
-- Migracao 006: Perfil consultor
--
-- Objetivo: adicionar perfil 'consultor' para acesso
-- individual ao dashboard, restrito aos proprios dados.
--
-- Alteracoes:
--   1. usuarios.perfil CHECK aceita 'consultor'
--   2. usuario_escopos.consultor_id (nova coluna)
--   3. CHECK de exclusividade atualizado para 3 colunas
--   4. Indice em usuario_escopos.consultor_id
--   5. Policy RLS pol_contratos_consultor
--   6. Policy RLS pol_metas_consultor
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. usuarios: adicionar 'consultor' ao CHECK
-- ===========================================

ALTER TABLE usuarios
    DROP CONSTRAINT IF EXISTS chk_usuarios_perfil;

ALTER TABLE usuarios
    ADD CONSTRAINT chk_usuarios_perfil
    CHECK (perfil IN (
        'admin',
        'gestor',
        'gerente_comercial',
        'supervisor',
        'consultor'
    ));

COMMENT ON COLUMN usuarios.perfil IS
    'Perfil de acesso: admin (acesso total + gerenciamento), '
    'gestor (visao global), '
    'gerente_comercial (acesso por regiao), '
    'supervisor (acesso por loja), '
    'consultor (acesso aos proprios dados).';


-- ===========================================
-- 2. usuario_escopos: adicionar consultor_id
-- ===========================================

ALTER TABLE usuario_escopos
    ADD COLUMN IF NOT EXISTS consultor_id UUID
        REFERENCES consultores (id) ON DELETE CASCADE;

COMMENT ON COLUMN usuario_escopos.consultor_id IS
    'Consultor vinculado (para perfil consultor). '
    'Exclusivo com regiao_id e loja_id.';


-- ===========================================
-- 3. CHECK de exclusividade: exatamente 1 dos 3
-- ===========================================

ALTER TABLE usuario_escopos
    DROP CONSTRAINT IF EXISTS chk_escopo_exclusivo;

ALTER TABLE usuario_escopos
    ADD CONSTRAINT chk_escopo_exclusivo
    CHECK (
        num_nonnulls(regiao_id, loja_id, consultor_id) = 1
    );


-- ===========================================
-- 4. Unicidade por usuario+consultor
-- ===========================================

ALTER TABLE usuario_escopos
    DROP CONSTRAINT IF EXISTS uq_escopo_consultor;

ALTER TABLE usuario_escopos
    ADD CONSTRAINT uq_escopo_consultor
    UNIQUE (usuario_id, consultor_id);


-- ===========================================
-- 5. Indice
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_usuario_escopos_consultor_id
    ON usuario_escopos (consultor_id);


-- ===========================================
-- 6. RLS: policy para consultor em contratos
-- Consultor so ve seus proprios contratos
-- ===========================================

DROP POLICY IF EXISTS pol_contratos_consultor ON contratos;

CREATE POLICY pol_contratos_consultor
    ON contratos FOR SELECT
    USING (
        obter_perfil_atual() = 'consultor'
        AND consultor_id IN (
            SELECT ue.consultor_id
            FROM usuario_escopos ue
            WHERE ue.usuario_id = obter_usuario_atual_id()
        )
    );


-- ===========================================
-- 7. RLS: policy para consultor em metas
-- Consultor ve metas da sua loja (precisa
-- para contextualizar progresso pessoal)
-- ===========================================

DROP POLICY IF EXISTS pol_metas_consultor ON metas;

CREATE POLICY pol_metas_consultor
    ON metas FOR SELECT
    USING (
        obter_perfil_atual() = 'consultor'
        AND loja_id IN (
            SELECT c.loja_id
            FROM consultores c
            JOIN usuario_escopos ue
                ON ue.consultor_id = c.id
            WHERE ue.usuario_id = obter_usuario_atual_id()
        )
    );


-- ===========================================
-- Validacao pos-migracao
-- ===========================================

-- Verificar CHECK de perfil
-- SELECT conname, pg_get_constraintdef(oid)
-- FROM pg_constraint
-- WHERE conname = 'chk_usuarios_perfil';

-- Verificar CHECK de exclusividade
-- SELECT conname, pg_get_constraintdef(oid)
-- FROM pg_constraint
-- WHERE conname = 'chk_escopo_exclusivo';

-- Listar policies
-- SELECT tablename, policyname
-- FROM pg_policies
-- WHERE tablename IN ('contratos', 'metas')
--   AND policyname LIKE '%consultor%';
