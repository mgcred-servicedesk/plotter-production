-- ============================================================
-- Migracao 028: Reconquista v2 — nova tabela `reconquista`
--
-- Contexto: o modelo de Reconquista mudou de snapshots
-- periodicos (reconquista_snapshot + macicas + flags) para um
-- EXPORT unico, 1 linha por cliente (co_adesao), ja classificado
-- pelo banco na coluna de_status_reconquista. As regras de
-- negocio sao validadas pelas datas do proprio arquivo:
--
--   * EFETIVADA       -> dt_macica > dt_fim_relacionamento
--   * PROMESSA        -> (dt_dna  > dt_fim_relacionamento OR
--                         dt_producao > dt_fim_relacionamento)
--                        e nao-efetivada  (aceite DNA / producao
--                        CNC, exceto antecipacao, apos o fim)
--   * SEM RECONQUISTA -> demais (a trabalhar)
--
-- Apuracao MENSAL pelo mes de dt_fim_relacionamento, com
-- DEFASAGEM de 1 mes: o mes de apuracao M exibe os contratos
-- cujo dt_fim_relacionamento caiu em M-1 (os de M so entram na
-- esteira no mes seguinte). A defasagem e aplicada no loader.
--
-- Esta tabela e a fonte unica do dashboard. A cada carga ela e
-- TRUNCADA e realimentada (ver fn_importar_reconquista, 029).
-- Resolve loja_id (cod_bmg + sucessora) e consultor_id (nome
-- completo + loja) no momento do import.
--
-- NOTA LGPD: nu_matricula NAO e armazenada (dado de beneficio).
-- co_adesao identifica o contrato, nao a pessoa.
--
-- Os objetos v1 (macicas, reconquista_snapshot, views/RPCs
-- v_reconquista_*/fn_macica_ativa/fn_importar_reconquista_snapshot,
-- sucessao no import) permanecem intactos e ficam SINALIZADOS
-- para deprecacao — remover apenas apos confirmacao.
--
-- Depende de: lojas, consultores, regioes (ja existentes).
-- Executar no Supabase SQL Editor.
-- ============================================================

CREATE TABLE reconquista (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    co_adesao             BIGINT NOT NULL,
    status                TEXT   NOT NULL,

    -- Datas que dirigem a classificacao (auditoria das regras)
    dt_fim_relacionamento DATE,
    dt_macica             DATE,
    dt_dna                DATE,
    dt_producao           DATE,

    subproduto            TEXT,

    -- Origem / hierarquia (texto bruto do arquivo + FK resolvida)
    no_franquia           TEXT,
    cod_bmg               INTEGER,
    loja_id               UUID REFERENCES lojas(id)       ON DELETE SET NULL,
    consultor_nome        TEXT,
    consultor_id          UUID REFERENCES consultores(id) ON DELETE SET NULL,
    gerente_regional      TEXT,
    gerente_loja          TEXT,
    coordenador_loja      TEXT,

    banco_origem          TEXT,
    banco_destino         TEXT,
    saldo_contabil        NUMERIC(15, 2),
    dias_atraso           INTEGER,
    faixa_atraso          TEXT,
    tipo_pagamento        TEXT,
    qt_fim_relacionamento INTEGER,

    link_aceite           TEXT,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_reconquista_co_adesao UNIQUE (co_adesao),
    CONSTRAINT chk_reconquista_status
        CHECK (status IN ('EFETIVADA', 'PROMESSA', 'SEM RECONQUISTA'))
);

COMMENT ON TABLE reconquista IS
    'Reconquista v2. Export unico, 1 linha por cliente (co_adesao), '
    'truncado e realimentado a cada carga (fn_importar_reconquista). '
    'status = de_status_reconquista do arquivo (EFETIVADA/PROMESSA/'
    'SEM RECONQUISTA). Apuracao mensal por dt_fim_relacionamento com '
    'defasagem de 1 mes aplicada no loader.';
COMMENT ON COLUMN reconquista.co_adesao IS
    'Codigo do contrato (ADE). Identifica o contrato, nao a pessoa.';
COMMENT ON COLUMN reconquista.status IS
    'EFETIVADA (dt_macica > dt_fim_relacionamento) | PROMESSA (aceite '
    'DNA ou producao CNC apos dt_fim_relacionamento) | SEM RECONQUISTA.';
COMMENT ON COLUMN reconquista.dt_fim_relacionamento IS
    'Referencia da maciça. Determina o mes de apuracao (com defasagem '
    'de 1 mes: dt_fim em M -> apuracao em M+1).';
COMMENT ON COLUMN reconquista.dt_macica IS
    'Data da maciça do cliente. dt_macica > dt_fim => EFETIVADA.';
COMMENT ON COLUMN reconquista.loja_id IS
    'FK lojas, resolvida no import via cod_bmg (prefixo de no_franquia) '
    'com COALESCE(sucessora_id, id). Ja vem resolvida — views nao '
    're-resolvem sucessora.';
COMMENT ON COLUMN reconquista.consultor_id IS
    'FK consultores, resolvida no import por nome completo + loja. '
    'consultor_nome guarda sempre o nome bruto para rastreabilidade.';
COMMENT ON COLUMN reconquista.link_aceite IS
    'de_link_aceite — link de aceite do reconquista (uso analitico).';

-- Indices para o dashboard (filtro mensal + agregacoes)
CREATE INDEX idx_reconquista_dt_fim    ON reconquista (dt_fim_relacionamento);
CREATE INDEX idx_reconquista_status    ON reconquista (status);
CREATE INDEX idx_reconquista_loja      ON reconquista (loja_id);
CREATE INDEX idx_reconquista_consultor ON reconquista (consultor_id);
