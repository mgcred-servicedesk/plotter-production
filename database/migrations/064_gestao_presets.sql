-- ============================================================
-- Migracao 064: presets de criterio da aba de Gestao
--
-- Adiciona:
--   - gestao_presets  (recortes salvos da aba de Gestao)
--
-- Depende de: usuarios (existente), atualizar_updated_at(),
-- obter_usuario_atual_id(), obter_perfil_atual().
--
-- MOTIVACAO
-- A aba de Gestao monta recortes com varios eixos (nivel,
-- metrica, produtos, criterios com base relativa). Sem
-- persistencia, o gestor remonta tudo a cada acesso e nao
-- consegue passar o recorte adiante. Um preset e exatamente
-- essa configuracao, nomeada.
--
-- FORMATO DO CONFIG (jsonb)
-- Chaves gravadas pela aplicacao (src/dashboard/loaders.py,
-- funcao salvar_preset_gestao):
--   {
--     "nivel": "Consultor" | "Loja" | "Supervisor" | "Regiao",
--     "metrica": "valor" | "qtd" | "ticket" | "share",
--     "combinacao": "E" | "OU" | "minimo",
--     "minimo": int,
--     "incluir_zerados": bool,
--     "produtos": ["CLT", "CNC", ...],
--     "criterios": {
--        "<rotulo>": {"modo": ..., "base": ..., "min": num,
--                     "max": num}
--     }
--   }
-- Fica em jsonb de proposito: os eixos da aba ainda estao
-- crescendo, e um preset antigo com chave faltando e lido com
-- o default da UI em vez de quebrar. Nao ha FK para produto —
-- rotulo que sair do MIX e simplesmente ignorado na leitura.
--
-- ATENCAO — ALCANCE REAL DA RLS AQUI
-- O dashboard conecta com uma chave unica de service_role, que
-- tem BYPASSRLS: as policies abaixo NAO sao executadas por ele,
-- e o recorte "cada um ve os seus" e feito client-side em
-- carregar_presets_gestao (filtro por usuario_id). As policies
-- valem como defense-in-depth para qualquer acesso futuro com
-- chave anon/authenticated, e sao fail-closed: sem
-- app.current_user_id setado, ninguem le nem escreve.
-- Um preset guarda limiares e nomes de produto — nenhum dado
-- pessoal, nenhum valor de contrato. Ver docs/agents/rls.md.
--
-- Executar no Supabase SQL Editor.
-- ============================================================


-- ============================================================
-- 1. Tabela
-- ============================================================

CREATE TABLE IF NOT EXISTS gestao_presets (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id    UUID NOT NULL
                      REFERENCES usuarios(id)
                      ON DELETE CASCADE,
    nome          TEXT NOT NULL,
    compartilhado BOOLEAN NOT NULL DEFAULT false,
    config        JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_gestao_presets_dono_nome UNIQUE (usuario_id, nome),
    CONSTRAINT chk_gestao_presets_nome
        CHECK (length(btrim(nome)) BETWEEN 1 AND 60),
    CONSTRAINT chk_gestao_presets_config_objeto
        CHECK (jsonb_typeof(config) = 'object')
);

COMMENT ON TABLE gestao_presets IS
    'Recortes salvos da aba de Gestao (nivel, metrica, produtos '
    'e criterios). Um preset por (usuario, nome).';
COMMENT ON COLUMN gestao_presets.compartilhado IS
    'true = visivel para os demais usuarios em modo leitura. '
    'Editar/apagar segue sendo exclusivo do dono.';
COMMENT ON COLUMN gestao_presets.config IS
    'Configuracao completa do recorte. Ver cabecalho da '
    'migracao 064 para o formato das chaves.';

CREATE INDEX IF NOT EXISTS idx_gestao_presets_usuario
    ON gestao_presets (usuario_id, nome);

CREATE INDEX IF NOT EXISTS idx_gestao_presets_compartilhado
    ON gestao_presets (compartilhado)
    WHERE compartilhado;

DROP TRIGGER IF EXISTS trg_gestao_presets_updated_at ON gestao_presets;
CREATE TRIGGER trg_gestao_presets_updated_at
    BEFORE UPDATE ON gestao_presets
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ============================================================
-- 2. RLS
--
-- SELECT: os proprios + os compartilhados por qualquer um.
-- INSERT/UPDATE/DELETE: so o dono. Admin nao ganha excecao —
-- preset e preferencia de trabalho, nao dado operacional, e
-- ninguem precisa editar o recorte alheio.
--
-- Fail-closed: obter_usuario_atual_id() devolve NULL quando a
-- aplicacao nao seta app.current_user_id, e toda comparacao
-- com NULL e falsa. Nenhuma linha vaza por omissao.
-- ============================================================

ALTER TABLE gestao_presets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_gestao_presets_select ON gestao_presets;
DROP POLICY IF EXISTS pol_gestao_presets_insert ON gestao_presets;
DROP POLICY IF EXISTS pol_gestao_presets_update ON gestao_presets;
DROP POLICY IF EXISTS pol_gestao_presets_delete ON gestao_presets;

CREATE POLICY pol_gestao_presets_select
    ON gestao_presets FOR SELECT
    USING (
        usuario_id = (SELECT obter_usuario_atual_id())
        OR (
            compartilhado
            AND (SELECT obter_usuario_atual_id()) IS NOT NULL
        )
    );

CREATE POLICY pol_gestao_presets_insert
    ON gestao_presets FOR INSERT
    WITH CHECK (usuario_id = (SELECT obter_usuario_atual_id()));

CREATE POLICY pol_gestao_presets_update
    ON gestao_presets FOR UPDATE
    USING (usuario_id = (SELECT obter_usuario_atual_id()))
    WITH CHECK (usuario_id = (SELECT obter_usuario_atual_id()));

CREATE POLICY pol_gestao_presets_delete
    ON gestao_presets FOR DELETE
    USING (usuario_id = (SELECT obter_usuario_atual_id()));
