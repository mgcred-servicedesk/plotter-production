-- ============================================================
-- Schema do Banco de Dados - MGCred Analise de Vendas
-- Supabase (PostgreSQL)
-- ============================================================
--
-- Este script cria o schema relacional para o projeto de
-- analise de vendas, substituindo as planilhas Excel como
-- fonte de dados.
--
-- Tabelas:
--   1. regioes          - Regioes de atuacao
--   2. lojas            - Lojas/filiais
--   3. consultores      - Consultores/vendedores
--   4. supervisores     - Supervisores de loja
--   5. periodos         - Periodos de referencia (mes/ano)
--   6. produtos         - Catalogo de produtos (tabela viva)
--   7. contratos        - Propostas e contratos (todos os status)
--   8. metas            - Metas normalizadas por periodo
--   9. pontuacao        - Pontuacao mensal por produto
--
-- Views:
--   - contratos_pagos   - Contratos pagos (dashboard atual)
--
-- ============================================================


-- ===========================================
-- 0. Extensoes e funcoes auxiliares
-- ===========================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- Funcao generica para atualizar updated_at
-- Reutilizada por triggers em varias tabelas
CREATE OR REPLACE FUNCTION atualizar_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ===========================================
-- 1. regioes
-- Origem: configuracao/loja_regiao.xlsx (coluna REGIAO)
-- Registros esperados: ~5
-- ===========================================

CREATE TABLE regioes (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_regioes_nome UNIQUE (nome)
);

COMMENT ON TABLE regioes IS
    'Regioes de atuacao. Cada regiao agrupa um conjunto de lojas.';

CREATE TRIGGER trg_regioes_updated_at
    BEFORE UPDATE ON regioes
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 2. lojas
-- Origem: configuracao/loja_regiao.xlsx
-- Registros esperados: ~47
-- ===========================================

CREATE TABLE lojas (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome       TEXT NOT NULL,
    cod_bmg    INTEGER,
    regiao_id  UUID REFERENCES regioes (id)
                   ON DELETE SET NULL,
    gerente    TEXT,
    perfil     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_lojas_nome UNIQUE (nome)
);

COMMENT ON TABLE lojas IS
    'Lojas/filiais da empresa. Cada loja pertence a uma regiao.';

CREATE TRIGGER trg_lojas_updated_at
    BEFORE UPDATE ON lojas
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 3. consultores
-- Origem: configuracao/HC_Colaboradores.xlsx
-- Registros esperados: ~239
-- ===========================================

CREATE TABLE consultores (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome       TEXT NOT NULL,
    loja_id    UUID REFERENCES lojas (id)
                   ON DELETE SET NULL,
    status     TEXT NOT NULL DEFAULT 'Ativo (a)',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_consultores_nome_loja UNIQUE (nome, loja_id)
);

COMMENT ON TABLE consultores IS
    'Consultores/vendedores. Origem: HC_Colaboradores.xlsx.';

CREATE TRIGGER trg_consultores_updated_at
    BEFORE UPDATE ON consultores
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 4. supervisores
-- Origem: configuracao/Supervisores.xlsx
-- Registros esperados: ~56
-- ===========================================

CREATE TABLE supervisores (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome       TEXT NOT NULL,
    loja_id    UUID REFERENCES lojas (id)
                   ON DELETE SET NULL,
    regiao_id  UUID REFERENCES regioes (id)
                   ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_supervisores_nome_loja UNIQUE (nome, loja_id)
);

COMMENT ON TABLE supervisores IS
    'Supervisores de loja. Colunas: LOJA, SUPERVISOR, REGIAO.';

CREATE TRIGGER trg_supervisores_updated_at
    BEFORE UPDATE ON supervisores
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 5. periodos
-- Tabela de referencia temporal (mes/ano)
-- ===========================================

CREATE TABLE periodos (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mes        INTEGER NOT NULL,
    ano        INTEGER NOT NULL,
    referencia TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_periodos_mes_ano UNIQUE (mes, ano),
    CONSTRAINT chk_periodos_mes CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT chk_periodos_ano CHECK (ano BETWEEN 2020 AND 2100)
);

COMMENT ON TABLE periodos IS
    'Periodos de referencia (mes/ano). Ex: mes=3, ano=2026, referencia=Mar/26.';


-- ===========================================
-- 6. produtos
-- Origem: tabelas/Tabelas_{mes}_{ano}.xlsx
-- Tabela "viva": upsert por coluna tabela.
-- Dados novos atualizam existentes.
-- Registros esperados: ~886 (cresce com o tempo)
-- ===========================================

CREATE TABLE produtos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tabela         TEXT NOT NULL,
    tipo_operacao  TEXT,
    tipo           TEXT,
    subtipo        TEXT,
    banco          TEXT,
    produto_pts    TEXT,
    pts            NUMERIC NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_produtos_tabela UNIQUE (tabela)
);

COMMENT ON TABLE produtos IS
    'Catalogo de produtos (tabela viva). Upsert por nome do produto. '
    'Origem: Tabelas_{mes}_{ano}.xlsx. Dados mais recentes sobrescrevem.';
COMMENT ON COLUMN produtos.tabela IS
    'Nome/codigo do produto. Chave de negocio para upsert.';
COMMENT ON COLUMN produtos.produto_pts IS
    'Categoria de pontuacao do produto (ex: CNC, FGTS, CARTAO).';

CREATE TRIGGER trg_produtos_updated_at
    BEFORE UPDATE ON produtos
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 7. contratos
-- Origem: Planilha completa de contratos
-- Inclui TODOS os status: EM ANALISE,
-- CANCELADO, PAGO AO CLIENTE, NAO PAGO
-- Registros esperados: ~16k/mes
-- ===========================================

CREATE TABLE contratos (
    id                        UUID PRIMARY KEY
                                  DEFAULT gen_random_uuid(),
    periodo_id                UUID REFERENCES periodos (id)
                                  ON DELETE SET NULL,
    loja_id                   UUID NOT NULL
                                  REFERENCES lojas (id)
                                  ON DELETE RESTRICT,
    consultor_id              UUID REFERENCES consultores (id)
                                  ON DELETE SET NULL,
    produto_id                UUID REFERENCES produtos (id)
                                  ON DELETE SET NULL,
    contrato_id               BIGINT NOT NULL,
    cliente                   TEXT,
    valor                     NUMERIC NOT NULL DEFAULT 0,
    prazo                     TEXT,
    valor_parcela             NUMERIC DEFAULT 0,
    tipo_operacao             TEXT,
    data_cadastro             DATE,
    status_banco              TEXT,
    data_status_banco         DATE,
    status_pagamento_cliente  TEXT,
    data_status_pagamento     DATE,
    banco                     TEXT,
    convenio                  TEXT,
    num_proposta              TEXT,
    sub_status_banco          TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_contratos_contrato_id
        UNIQUE (contrato_id)
);

COMMENT ON TABLE contratos IS
    'Propostas e contratos com todos os status '
    '(EM ANALISE, CANCELADO, PAGO AO CLIENTE, NAO PAGO AO CLIENTE). '
    'periodo_id e derivado de data_status_pagamento (NULL se nao pago). '
    'O dashboard atual consome apenas a view contratos_pagos.';
COMMENT ON COLUMN contratos.periodo_id IS
    'Periodo de pagamento. Derivado de data_status_pagamento. '
    'NULL quando status_pagamento_cliente != PAGO AO CLIENTE.';
COMMENT ON COLUMN contratos.contrato_id IS
    'ID do contrato no sistema origem. Usado para deduplicacao.';
COMMENT ON COLUMN contratos.status_banco IS
    'Status do banco: EM ANALISE, CANCELADO, etc.';
COMMENT ON COLUMN contratos.status_pagamento_cliente IS
    'Status de pagamento: PAGO AO CLIENTE, NAO PAGO AO CLIENTE.';
COMMENT ON COLUMN contratos.data_status_pagamento IS
    'Data do pagamento ao cliente. Determina o periodo de apuracao.';


-- ===========================================
-- 7a. VIEW contratos_pagos
-- Filtra apenas contratos pagos.
-- Equivale as planilhas digitacao/{mes}_{ano}.xlsx
-- ===========================================

CREATE VIEW contratos_pagos AS
SELECT *
FROM contratos
WHERE status_pagamento_cliente = 'PAGO AO CLIENTE';

COMMENT ON VIEW contratos_pagos IS
    'Contratos pagos ao cliente. Equivale aos dados das planilhas '
    'digitacao/{mes}_{ano}.xlsx. Usado pelo dashboard atual.';


-- ===========================================
-- 8. metas
-- Origem: metas/metas_{mes}.xlsx
-- Normalizacao das ~40 colunas em linhas
-- (loja + produto + escopo + nivel + periodo)
-- ===========================================

CREATE TABLE metas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id  UUID NOT NULL
                    REFERENCES periodos (id)
                    ON DELETE CASCADE,
    loja_id     UUID NOT NULL
                    REFERENCES lojas (id)
                    ON DELETE CASCADE,
    produto     TEXT NOT NULL,
    escopo      TEXT NOT NULL,
    nivel       TEXT,
    valor       NUMERIC NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_metas_periodo_loja_prod_esc_niv
        UNIQUE (periodo_id, loja_id, produto, escopo, nivel),
    CONSTRAINT chk_metas_escopo
        CHECK (escopo IN ('LOJA', 'CONSULTOR')),
    CONSTRAINT chk_metas_nivel
        CHECK (nivel IS NULL OR nivel IN ('BRONZE', 'PRATA', 'OURO'))
);

COMMENT ON TABLE metas IS
    'Metas normalizadas por periodo. Cada linha representa '
    'uma meta especifica: loja + produto + escopo + nivel. '
    'Origem: metas/metas_{mes}.xlsx (desnormalizacao das ~40 colunas).';
COMMENT ON COLUMN metas.produto IS
    'Tipo de produto da meta: GERAL, CNC, SAQUE, EMISSAO, '
    'SUPER_CONTA, VIDA_FAMILIAR, FGTS, CLT, FGTS_ANT_BENEF_13, '
    'BMG_MED, MIX, CONSIGNADO.';
COMMENT ON COLUMN metas.escopo IS
    'Escopo da meta: LOJA ou CONSULTOR.';
COMMENT ON COLUMN metas.nivel IS
    'Nivel da meta: BRONZE, PRATA, OURO ou NULL (meta unica).';

CREATE TRIGGER trg_metas_updated_at
    BEFORE UPDATE ON metas
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 9. pontuacao
-- Origem: pontuacao/pontos_{mes}.xlsx
-- Tabela de pontuacao mensal por produto
-- Registros esperados: ~12/mes
-- ===========================================

CREATE TABLE pontuacao (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id  UUID NOT NULL
                    REFERENCES periodos (id)
                    ON DELETE CASCADE,
    produto     TEXT NOT NULL,
    producao    INTEGER NOT NULL DEFAULT 1,
    pontos      NUMERIC NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_pontuacao_periodo_produto
        UNIQUE (periodo_id, produto)
);

COMMENT ON TABLE pontuacao IS
    'Pontuacao mensal por produto. Pontos variam mensalmente. '
    'Origem: pontuacao/pontos_{mes}.xlsx.';
COMMENT ON COLUMN pontuacao.produto IS
    'Nome do produto de pontuacao: CNC, CNC 13, CARTAO, FGTS, '
    'CONSIG ITAU, CONSIG BMG, CONSIG C6, CONSIG PRIV, '
    'ANT. DE BENEF., SAQUE, SAQUE BENEFICIO, PORTABILIDADE.';
COMMENT ON COLUMN pontuacao.pontos IS
    'Multiplicador de pontos. Calculo: VALOR * PONTOS.';

CREATE TRIGGER trg_pontuacao_updated_at
    BEFORE UPDATE ON pontuacao
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- INDICES
-- ===========================================

-- contratos: filtro por periodo (mes)
CREATE INDEX idx_contratos_periodo_id
    ON contratos (periodo_id);

-- contratos: agregacoes por loja
CREATE INDEX idx_contratos_loja_id
    ON contratos (loja_id);

-- contratos: rankings de consultores
CREATE INDEX idx_contratos_consultor_id
    ON contratos (consultor_id);

-- contratos: evolucao diaria + determinacao de periodo
CREATE INDEX idx_contratos_data_status_pagamento
    ON contratos (data_status_pagamento);

-- contratos: filtro pagos vs nao pagos (view contratos_pagos)
CREATE INDEX idx_contratos_status_pagamento
    ON contratos (status_pagamento_cliente);

-- contratos: filtro em analise vs cancelado (KPIs futuros)
CREATE INDEX idx_contratos_status_banco
    ON contratos (status_banco);

-- contratos: KPIs futuros - digitacao por dia
CREATE INDEX idx_contratos_data_cadastro
    ON contratos (data_cadastro);

-- metas: consulta principal por periodo + loja
CREATE INDEX idx_metas_periodo_loja
    ON metas (periodo_id, loja_id);

-- pontuacao: carga mensal
CREATE INDEX idx_pontuacao_periodo_id
    ON pontuacao (periodo_id);


-- ===========================================
-- PADRAO DE UPSERT PARA PRODUTOS
-- (referencia para importacao)
-- ===========================================

-- Exemplo de upsert para a tabela produtos:
--
-- INSERT INTO produtos (
--     tabela, tipo_operacao, tipo, subtipo,
--     banco, produto_pts, pts
-- )
-- VALUES (
--     'DEBITO EM CONTA', 'NORMAL', 'CNC', 'NOVO',
--     'HELP', 'CNC', 5.0
-- )
-- ON CONFLICT (tabela) DO UPDATE SET
--     tipo_operacao = EXCLUDED.tipo_operacao,
--     tipo          = EXCLUDED.tipo,
--     subtipo       = EXCLUDED.subtipo,
--     banco         = EXCLUDED.banco,
--     produto_pts   = EXCLUDED.produto_pts,
--     pts           = EXCLUDED.pts;


-- ===========================================
-- MAPEAMENTO DE METAS (referencia)
-- Desnormalizacao: colunas da planilha ->
-- registros na tabela metas
-- ===========================================

-- Coluna Original             | produto           | escopo     | nivel
-- ----------------------------|-------------------|------------|--------
-- BRONZE LOJA                 | GERAL             | LOJA       | BRONZE
-- PRATA LOJA                  | GERAL             | LOJA       | PRATA
-- OURO LOJA                   | GERAL             | LOJA       | OURO
-- BRONZE CONSULTOR            | GERAL             | CONSULTOR  | BRONZE
-- PRATA CONSULTOR             | GERAL             | CONSULTOR  | PRATA
-- OURO CONSULTOR              | GERAL             | CONSULTOR  | OURO
-- CNC LOJA                    | CNC               | LOJA       | NULL
-- CNC CONSULTOR               | CNC               | CONSULTOR  | NULL
-- SAQUE LOJA                  | SAQUE             | LOJA       | NULL
-- SAQUE CONSULTOR             | SAQUE             | CONSULTOR  | NULL
-- EMISSAO                     | EMISSAO           | LOJA       | NULL
-- EMISSAO CONSULTOR BRONZE    | EMISSAO           | CONSULTOR  | BRONZE
-- EMISSAO CONSULTOR PRATA     | EMISSAO           | CONSULTOR  | PRATA
-- EMISSAO CONSULTOR OURO      | EMISSAO           | CONSULTOR  | OURO
-- SUPER CONTA                 | SUPER_CONTA       | LOJA       | NULL
-- SUPER CONTA CONS. BRONZE    | SUPER_CONTA       | CONSULTOR  | BRONZE
-- SUPER CONTA CONS. PRATA     | SUPER_CONTA       | CONSULTOR  | PRATA
-- SUPER CONTA CONS. OURO      | SUPER_CONTA       | CONSULTOR  | OURO
-- VIDA FAMILIAR               | VIDA_FAMILIAR     | LOJA       | NULL
-- VIDA FAMILIAR BRONZE        | VIDA_FAMILIAR     | CONSULTOR  | BRONZE
-- VIDA FAMILIAR PRATA         | VIDA_FAMILIAR     | CONSULTOR  | PRATA
-- VIDA FAMILIAR OURO          | VIDA_FAMILIAR     | CONSULTOR  | OURO
-- META FGTS                   | FGTS              | LOJA       | NULL
-- META FGTS (CONSULTOR)       | FGTS              | CONSULTOR  | NULL
-- CLT                         | CLT               | LOJA       | NULL
-- CLT CONSULTOR               | CLT               | CONSULTOR  | NULL
-- META LOJA FGTS & ANT BEN 13 | FGTS_ANT_BENEF_13 | LOJA      | NULL
-- META /FGTS/ANT BENEF 13     | FGTS_ANT_BENEF_13 | CONSULTOR | NULL
-- BMG MED                     | BMG_MED           | LOJA       | NULL
-- BMG MED CONSULTOR BRONZE    | BMG_MED           | CONSULTOR  | BRONZE
-- BMG MED CONSULTOR PRATA     | BMG_MED           | CONSULTOR  | PRATA
-- BMG MED CONSULTOR OURO      | BMG_MED           | CONSULTOR  | OURO
-- MIX LOJA                    | MIX               | LOJA       | NULL
-- CONSIGNADO                  | CONSIGNADO        | LOJA       | NULL
-- CONSIG TOTAL CONSULTOR      | CONSIGNADO        | CONSULTOR  | NULL
