-- ============================================================
-- Migracao 018: Projeto Reconquista MG CRED
--
-- Adiciona:
--   - macicas              (campanhas de reconquista)
--   - reconquista_snapshot (estado de cada cliente por envio)
--
-- Depende de: lojas, consultores, regioes (existentes).
--
-- RLS espelha o padrao de `contratos` (migracao 011): SELECT
-- consolidado por perfil em uma unica policy, com escritas
-- restritas a admin. Importacao via angry-man usa service_role
-- (BYPASSRLS), entao as policies nao bloqueiam o ETL.
--
-- LGPD: nenhuma coluna armazena CPF. Cruzamento entre macicas
-- e feito por COD_ADE (contrato), nao por pessoa.
-- Ver docs/RECONQUISTA_MIGRATION.md secao 2.
--
-- Executar no Supabase SQL Editor.
-- ============================================================


-- ============================================================
-- 1. macicas
-- ============================================================

CREATE TABLE macicas (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo             TEXT NOT NULL,
    descricao          TEXT,
    dat_primeiro_envio DATE NOT NULL,
    dat_ultimo_envio   DATE,
    meta_retencao      NUMERIC(5,2) NOT NULL DEFAULT 30.0,
    ativo              BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_macicas_codigo UNIQUE (codigo),
    CONSTRAINT chk_macicas_meta  CHECK (meta_retencao BETWEEN 0 AND 100)
);

COMMENT ON TABLE macicas IS
    'Campanhas de reconquista MG CRED. Cada maciça agrupa '
    'múltiplos envios de arquivos Excel no mesmo período. '
    'A maciça muda aproximadamente no dia 20 do mês.';
COMMENT ON COLUMN macicas.codigo IS
    'Código no formato AAAAMM. Ex: 202604, 202605.';
COMMENT ON COLUMN macicas.dat_primeiro_envio IS
    'Data do primeiro arquivo xlsx recebido nesta campanha.';
COMMENT ON COLUMN macicas.dat_ultimo_envio IS
    'Data do último arquivo xlsx recebido. Atualizado a cada carga.';
COMMENT ON COLUMN macicas.meta_retencao IS
    'Meta de taxa de reconquista em %. Padrão: 30.0';

CREATE TRIGGER trg_macicas_updated_at
    BEFORE UPDATE ON macicas
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ============================================================
-- 2. reconquista_snapshot
-- ============================================================

CREATE TABLE reconquista_snapshot (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    macica_id        UUID NOT NULL
                         REFERENCES macicas(id)
                         ON DELETE CASCADE,
    dat_envio        DATE NOT NULL,
    cod_ade          BIGINT NOT NULL,
    loja_id          UUID REFERENCES lojas(id)
                         ON DELETE SET NULL,
    consultor_id     UUID REFERENCES consultores(id)
                         ON DELETE SET NULL,
    subproduto       TEXT,
    saldo_contabil   NUMERIC(15, 2),
    dias_atraso      INTEGER,
    faixa_atraso     TEXT,
    mot_ipd_operar   TEXT,
    flag_cnc         SMALLINT NOT NULL DEFAULT 0,
    flag_consignado  SMALLINT NOT NULL DEFAULT 0,
    flag_cartao      SMALLINT NOT NULL DEFAULT 0,
    flag_dna         SMALLINT NOT NULL DEFAULT 0,
    flag_reconquista SMALLINT NOT NULL DEFAULT 0,
    flag_rl          SMALLINT NOT NULL DEFAULT 0,
    tipo_pgto        TEXT,
    tipo_conta       TEXT,
    regra_pgto       TEXT,
    dat_fim_relac    DATE,
    banco_origem     TEXT,
    banco_destino    TEXT,
    qtd_fdr          INTEGER,
    link             TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_reconquista_snapshot
        UNIQUE (macica_id, dat_envio, cod_ade),
    CONSTRAINT chk_rsnap_flag_cnc         CHECK (flag_cnc IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_consignado  CHECK (flag_consignado IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_cartao      CHECK (flag_cartao IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_dna         CHECK (flag_dna IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_reconquista CHECK (flag_reconquista IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_rl          CHECK (flag_rl IN (0, 1))
);

COMMENT ON TABLE reconquista_snapshot IS
    'Snapshot do estado de cada cliente (COD_ADE) a cada envio '
    'de arquivo Excel da campanha. Nao e cumulativo. '
    'FLAG_RECONQUISTA pode reverter (FLAG_DNA e reversivel).';
COMMENT ON COLUMN reconquista_snapshot.cod_ade IS
    'Codigo do contrato (= contratos.num_proposta). '
    'Identifica o CONTRATO, nao a pessoa.';
COMMENT ON COLUMN reconquista_snapshot.flag_reconquista IS
    'Metrica principal. OR de flag_cnc/consignado/cartao/dna. '
    'Valor do momento do envio — pode reverter.';
COMMENT ON COLUMN reconquista_snapshot.flag_dna IS
    'Reversivel. Representa estado de processo DNA no sistema '
    'de origem. Confirmado: 8 reversoes em 14-20/04/2026.';
COMMENT ON COLUMN reconquista_snapshot.flag_cnc IS
    'Irreversivel. Novo contrato CNC pago — fato contabil.';

CREATE INDEX idx_rsnap_macica
    ON reconquista_snapshot (macica_id);

CREATE INDEX idx_rsnap_dat_envio
    ON reconquista_snapshot (macica_id, dat_envio);

CREATE INDEX idx_rsnap_cod_ade
    ON reconquista_snapshot (cod_ade);

CREATE INDEX idx_rsnap_loja
    ON reconquista_snapshot (loja_id);

CREATE INDEX idx_rsnap_consultor
    ON reconquista_snapshot (consultor_id);

CREATE INDEX idx_rsnap_flag
    ON reconquista_snapshot (macica_id, flag_reconquista);


-- ============================================================
-- 3. RLS — macicas
--
-- Leitura aberta a todos os perfis autenticados (metadados de
-- campanha, sem dado pessoal). Escrita: admin only.
-- ============================================================

ALTER TABLE macicas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_macicas_select       ON macicas;
DROP POLICY IF EXISTS pol_macicas_admin_insert ON macicas;
DROP POLICY IF EXISTS pol_macicas_admin_update ON macicas;
DROP POLICY IF EXISTS pol_macicas_admin_delete ON macicas;

CREATE POLICY pol_macicas_select
    ON macicas FOR SELECT
    USING (
        (SELECT obter_perfil_atual()) IN (
            'admin', 'gestor', 'gerente_comercial',
            'supervisor', 'consultor'
        )
    );

CREATE POLICY pol_macicas_admin_insert
    ON macicas FOR INSERT
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_macicas_admin_update
    ON macicas FOR UPDATE
    USING ((SELECT obter_perfil_atual()) = 'admin')
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_macicas_admin_delete
    ON macicas FOR DELETE
    USING ((SELECT obter_perfil_atual()) = 'admin');


-- ============================================================
-- 4. RLS — reconquista_snapshot
--
-- Espelha pol_contratos_select (migracao 011): SELECT
-- consolidado por perfil, escritas admin-only.
-- ============================================================

ALTER TABLE reconquista_snapshot ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_rsnap_select       ON reconquista_snapshot;
DROP POLICY IF EXISTS pol_rsnap_admin_insert ON reconquista_snapshot;
DROP POLICY IF EXISTS pol_rsnap_admin_update ON reconquista_snapshot;
DROP POLICY IF EXISTS pol_rsnap_admin_delete ON reconquista_snapshot;

CREATE POLICY pol_rsnap_select
    ON reconquista_snapshot FOR SELECT
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

CREATE POLICY pol_rsnap_admin_insert
    ON reconquista_snapshot FOR INSERT
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_rsnap_admin_update
    ON reconquista_snapshot FOR UPDATE
    USING ((SELECT obter_perfil_atual()) = 'admin')
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_rsnap_admin_delete
    ON reconquista_snapshot FOR DELETE
    USING ((SELECT obter_perfil_atual()) = 'admin');
