-- ============================================================
-- Migracao 021: Sucessao de lojas (carteira herdada)
--
-- Contexto: ao longo do tempo lojas PDV foram desativadas e
-- suas carteiras transferidas para uma loja HELP. Modelamos
-- isso com:
--   - lojas.ativo            (false = loja nao recebe mais novo)
--   - lojas.sucessora_id     (loja que herdou a carteira)
--
-- Aplicado em: angry-man (importacao "Sucessao de Lojas") e
-- usado por: fn_importar_reconquista_snapshot (migracao 022).
--
-- Decisoes:
--   - 1-para-1 e final: uma loja PDV → uma loja HELP herdeira.
--   - Manter o registro da predecessora preserva histórico
--     de contratos antigos; somente novos imports respeitam
--     a sucessora.
--   - sucessora_id pode formar cadeia (A → B → C) mas a
--     resolucao no import segue apenas um nivel (COALESCE
--     simples). Se houver cadeia futura, atualizar a RPC.
--
-- Executar no Supabase SQL Editor.
-- ============================================================

ALTER TABLE lojas
    ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS sucessora_id UUID
        REFERENCES lojas(id)
        ON DELETE SET NULL;

COMMENT ON COLUMN lojas.ativo IS
    'Falso quando a loja foi desativada (PDV antigo). Imports '
    'novos devem ignorar ou redirecionar para a sucessora.';
COMMENT ON COLUMN lojas.sucessora_id IS
    'Loja que herdou a carteira desta. Usado por '
    'fn_importar_reconquista_snapshot para atribuir o snapshot '
    'a loja correta quando o arquivo traz o cod_bmg antigo.';

-- Integridade: loja nao pode ser sucessora de si mesma.
ALTER TABLE lojas
    DROP CONSTRAINT IF EXISTS chk_lojas_sucessora_nao_self;
ALTER TABLE lojas
    ADD CONSTRAINT chk_lojas_sucessora_nao_self
        CHECK (sucessora_id IS NULL OR sucessora_id <> id);

-- Indice para o lookup de sucessora.
CREATE INDEX IF NOT EXISTS idx_lojas_sucessora
    ON lojas (sucessora_id)
    WHERE sucessora_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_lojas_ativo
    ON lojas (ativo)
    WHERE ativo = false;
