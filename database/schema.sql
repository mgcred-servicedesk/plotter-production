-- ============================================================
-- Schema do Banco de Dados - MGCred Analise de Vendas
-- Supabase (PostgreSQL)
-- ============================================================
--
-- Script unico de criacao do banco. Inclui todas as tabelas,
-- views, funcoes, indices, RLS e dados iniciais.
-- Pode ser executado do zero (DROP/CREATE).
--
-- Tabelas:
--   1.  regioes            - Regioes de atuacao
--   2.  lojas              - Lojas/filiais
--   3.  consultores        - Consultores/vendedores
--   4.  supervisores       - Supervisores de loja
--   5.  periodos           - Periodos de referencia (mes/ano)
--   6.  categorias_produto - Categorias canonicas de produto
--   7.  produtos           - Catalogo de variantes de produto
--   8.  contratos          - Propostas e contratos
--   9.  metas              - Metas normalizadas por periodo
--   10. pontuacao          - Pontuacao mensal por categoria
--   11. usuarios           - Usuarios do sistema (login)
--   12. usuario_escopos    - Escopos de acesso por usuario
--
-- Views:
--   - contratos_pagos      - Contratos pagos (dashboard)
--   - v_pontuacao_efetiva  - Pontuacao com fallback temporal
--
-- Funcoes:
--   - atualizar_updated_at()
--   - obter_usuario_atual_id()
--   - obter_perfil_atual()
--   - obter_pontuacao_periodo(mes, ano)
--
-- ============================================================


-- ===========================================
-- 0. Extensoes e funcoes auxiliares
-- ===========================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- Funcao generica para atualizar updated_at
-- Reutilizada por triggers em varias tabelas
CREATE OR REPLACE FUNCTION atualizar_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


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
    'Periodos de referencia (mes/ano). '
    'Ex: mes=3, ano=2026, referencia=Mar/26.';


-- ===========================================
-- 6. categorias_produto
-- Camada canonica entre variantes de produto,
-- pontuacao mensal e grupos do dashboard/metas.
--
-- Substitui os dicionarios hardcoded:
--   settings.py → MAPEAMENTO_PRODUTOS,
--                  MAPEAMENTO_COLUNAS_META,
--                  LISTA_PRODUTOS,
--                  PRODUTOS_EMISSAO
--   pontuacao_loader.py →
--                  criar_mapeamento_tipo_produto()
--   business_rules.py →
--                  regras de exclusao valor/pontos
--
-- Registros esperados: ~15 (cresce raramente)
-- ===========================================

CREATE TABLE categorias_produto (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo           TEXT NOT NULL,
    nome             TEXT NOT NULL,
    grupo_dashboard  TEXT,
    grupo_meta       TEXT,
    conta_valor      BOOLEAN NOT NULL DEFAULT true,
    conta_pontuacao  BOOLEAN NOT NULL DEFAULT true,
    ordem            INTEGER NOT NULL DEFAULT 0,
    ativo            BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_categorias_produto_codigo UNIQUE (codigo)
);

COMMENT ON TABLE categorias_produto IS
    'Categorias canonicas de produto. Cada categoria agrupa '
    'variantes de produto (tabela produtos) e define como '
    'elas se relacionam com pontuacao, metas e o dashboard. '
    'Substitui dicionarios hardcoded no codigo Python.';
COMMENT ON COLUMN categorias_produto.codigo IS
    'Codigo unico da categoria. Usado como chave de negocio. '
    'Ex: CNC, FGTS, CARTAO, CONSIG_BMG.';
COMMENT ON COLUMN categorias_produto.nome IS
    'Nome de exibicao da categoria. '
    'Ex: CNC, FGTS, Cartao, Consig BMG.';
COMMENT ON COLUMN categorias_produto.grupo_dashboard IS
    'Grupo de produto no dashboard. Valores possiveis: '
    'CNC, SAQUE, CLT, CONSIGNADO, PACK. '
    'NULL para produtos especiais (emissao, seguros, super conta).';
COMMENT ON COLUMN categorias_produto.grupo_meta IS
    'Produto correspondente na tabela de metas. '
    'Ex: CNC, SAQUE, CLT, CONSIGNADO, FGTS, '
    'FGTS_ANT_BENEF_13, EMISSAO, SUPER_CONTA, '
    'VIDA_FAMILIAR, BMG_MED, MIX. '
    'NULL se nao tem meta associada.';
COMMENT ON COLUMN categorias_produto.conta_valor IS
    'Se true, o valor monetario desta categoria entra '
    'nos KPIs de valor. Emissao de cartao e seguros = false.';
COMMENT ON COLUMN categorias_produto.conta_pontuacao IS
    'Se true, esta categoria gera pontos nos KPIs. '
    'Emissao de cartao e seguros = false.';
COMMENT ON COLUMN categorias_produto.ordem IS
    'Ordem de exibicao no dashboard e relatorios.';

CREATE TRIGGER trg_categorias_produto_updated_at
    BEFORE UPDATE ON categorias_produto
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 7. produtos
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
    categoria_id   UUID REFERENCES categorias_produto (id)
                       ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_produtos_tabela UNIQUE (tabela)
);

COMMENT ON TABLE produtos IS
    'Catalogo de variantes de produto (tabela viva). '
    'Upsert por nome do produto (coluna tabela). '
    'Origem: Tabelas_{mes}_{ano}.xlsx. '
    'Dados mais recentes sobrescrevem.';
COMMENT ON COLUMN produtos.tabela IS
    'Nome/codigo da variante de produto. '
    'Chave de negocio para upsert. '
    'Ex: DEBITO EM CONTA, HELP CNC NOVO.';
COMMENT ON COLUMN produtos.tipo IS
    'Tipo do produto na planilha origem. '
    'Ex: CNC, FGTS, CONSIG, SAQUE. '
    'Usado para mapear a categoria_id.';
COMMENT ON COLUMN produtos.categoria_id IS
    'FK para categorias_produto. Substitui a antiga '
    'coluna produto_pts (TEXT). Vincula cada variante '
    'a sua categoria canonica de pontuacao.';

CREATE TRIGGER trg_produtos_updated_at
    BEFORE UPDATE ON produtos
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 8. contratos
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
    valor                     NUMERIC(15,2) NOT NULL DEFAULT 0,
    prazo                     TEXT,
    valor_parcela             NUMERIC(15,2) DEFAULT 0,
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
-- 8a. VIEW contratos_pagos
-- Filtra apenas contratos pagos.
-- Equivale as planilhas digitacao/{mes}_{ano}.xlsx
-- SECURITY INVOKER: RLS se aplica ao usuario
-- ===========================================

CREATE VIEW contratos_pagos
    WITH (security_invoker = on)
AS
SELECT *
FROM contratos
WHERE status_pagamento_cliente = 'PAGO AO CLIENTE';

COMMENT ON VIEW contratos_pagos IS
    'Contratos pagos ao cliente. Equivale as planilhas '
    'digitacao/{mes}_{ano}.xlsx. Usado pelo dashboard. '
    'SECURITY INVOKER: RLS de contratos se aplica.';


-- ===========================================
-- 9. metas
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
    valor       NUMERIC(15,2) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_metas_periodo_loja_prod_esc_niv
        UNIQUE (periodo_id, loja_id, produto, escopo, nivel),
    CONSTRAINT chk_metas_escopo
        CHECK (escopo IN ('LOJA', 'CONSULTOR')),
    CONSTRAINT chk_metas_nivel
        CHECK (nivel IS NULL
               OR nivel IN ('BRONZE', 'PRATA', 'OURO'))
);

COMMENT ON TABLE metas IS
    'Metas normalizadas por periodo. Cada linha representa '
    'uma meta especifica: loja + produto + escopo + nivel. '
    'Origem: metas/metas_{mes}.xlsx. '
    'O campo produto usa os valores de grupo_meta '
    'de categorias_produto (ex: CNC, SAQUE) ou GERAL '
    'para metas globais.';
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
-- 10. pontuacao
-- Origem: pontuacao/pontos_{mes}.xlsx
-- Pontuacao mensal por CATEGORIA de produto.
-- Pontos podem variar entre periodos.
-- Se o periodo atual nao tiver dados, usa-se
-- o periodo anterior (fallback via funcao SQL).
-- Registros esperados: ~12-15/mes
-- ===========================================

CREATE TABLE pontuacao (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id    UUID NOT NULL
                      REFERENCES periodos (id)
                      ON DELETE CASCADE,
    categoria_id  UUID NOT NULL
                      REFERENCES categorias_produto (id)
                      ON DELETE CASCADE,
    producao      INTEGER NOT NULL DEFAULT 1,
    pontos        NUMERIC(10,4) NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_pontuacao_periodo_categoria
        UNIQUE (periodo_id, categoria_id)
);

COMMENT ON TABLE pontuacao IS
    'Pontuacao mensal por categoria de produto. '
    'Pontos variam entre periodos (ex: Jan CNC=6, Fev CNC=5.5). '
    'Se o periodo atual nao tiver dados para uma categoria, '
    'a funcao obter_pontuacao_periodo() retorna o valor do '
    'periodo anterior mais recente (fallback). '
    'Origem: pontuacao/pontos_{mes}.xlsx.';
COMMENT ON COLUMN pontuacao.categoria_id IS
    'FK para categorias_produto. Substitui a antiga '
    'coluna produto (TEXT livre).';
COMMENT ON COLUMN pontuacao.pontos IS
    'Multiplicador de pontos. Calculo: VALOR * PONTOS.';

CREATE TRIGGER trg_pontuacao_updated_at
    BEFORE UPDATE ON pontuacao
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 10a. FUNCAO obter_pontuacao_periodo
-- Retorna pontuacao efetiva para um dado mes/ano.
-- Se nao houver dados para o periodo solicitado,
-- busca o periodo anterior mais recente que tenha
-- dados (fallback automatico).
-- ===========================================

CREATE OR REPLACE FUNCTION obter_pontuacao_periodo(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    categoria_id    UUID,
    categoria_codigo TEXT,
    categoria_nome  TEXT,
    pontos          NUMERIC(10,4),
    producao        INTEGER,
    periodo_origem  TEXT,
    is_fallback     BOOLEAN
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
    v_periodo_id UUID;
    v_tem_dados  BOOLEAN;
    v_mes_busca  INTEGER := p_mes;
    v_ano_busca  INTEGER := p_ano;
    v_tentativas INTEGER := 0;
BEGIN
    -- Buscar periodo solicitado ou anterior com dados
    LOOP
        SELECT p.id INTO v_periodo_id
        FROM public.periodos p
        WHERE p.mes = v_mes_busca AND p.ano = v_ano_busca;

        -- Se periodo existe, verificar se tem pontuacao
        IF v_periodo_id IS NOT NULL THEN
            SELECT EXISTS(
                SELECT 1
                FROM public.pontuacao pt
                WHERE pt.periodo_id = v_periodo_id
            ) INTO v_tem_dados;

            EXIT WHEN v_tem_dados;
        END IF;

        -- Retroceder um mes
        v_tentativas := v_tentativas + 1;
        IF v_tentativas > 24 THEN
            -- Evitar loop infinito (max 2 anos para tras)
            RETURN;
        END IF;

        v_mes_busca := v_mes_busca - 1;
        IF v_mes_busca < 1 THEN
            v_mes_busca := 12;
            v_ano_busca := v_ano_busca - 1;
        END IF;
    END LOOP;

    RETURN QUERY
    SELECT
        cp.id           AS categoria_id,
        cp.codigo       AS categoria_codigo,
        cp.nome         AS categoria_nome,
        pt.pontos       AS pontos,
        pt.producao     AS producao,
        per.referencia  AS periodo_origem,
        (v_mes_busca != p_mes
         OR v_ano_busca != p_ano) AS is_fallback
    FROM public.pontuacao pt
    JOIN public.categorias_produto cp
        ON cp.id = pt.categoria_id
    JOIN public.periodos per
        ON per.id = pt.periodo_id
    WHERE pt.periodo_id = v_periodo_id;
END;
$$;

COMMENT ON FUNCTION obter_pontuacao_periodo(INTEGER, INTEGER) IS
    'Retorna pontuacao efetiva para um mes/ano. '
    'Se o periodo solicitado nao tiver dados de pontuacao, '
    'busca automaticamente o periodo anterior mais recente '
    '(fallback). Retorna flag is_fallback=true quando '
    'os dados vem de um periodo diferente do solicitado.';


-- ===========================================
-- 10b. VIEW v_pontuacao_efetiva
-- Para cada periodo existente, mostra a pontuacao
-- efetiva (propria ou herdada do periodo anterior).
-- Util para consultas do dashboard.
-- ===========================================

CREATE VIEW v_pontuacao_efetiva
    WITH (security_invoker = on)
AS
SELECT
    per.id          AS periodo_id,
    per.mes,
    per.ano,
    per.referencia,
    cp.id           AS categoria_id,
    cp.codigo       AS categoria_codigo,
    cp.nome         AS categoria_nome,
    cp.grupo_dashboard,
    cp.grupo_meta,
    cp.conta_valor,
    cp.conta_pontuacao,
    COALESCE(
        pt_atual.pontos,
        pt_anterior.pontos,
        0
    )               AS pontos,
    COALESCE(
        pt_atual.producao,
        pt_anterior.producao,
        1
    )               AS producao,
    CASE
        WHEN pt_atual.id IS NOT NULL THEN false
        WHEN pt_anterior.id IS NOT NULL THEN true
        ELSE true
    END             AS is_fallback
FROM periodos per
CROSS JOIN categorias_produto cp
LEFT JOIN pontuacao pt_atual
    ON pt_atual.periodo_id = per.id
    AND pt_atual.categoria_id = cp.id
LEFT JOIN LATERAL (
    SELECT pt2.id, pt2.pontos, pt2.producao
    FROM pontuacao pt2
    JOIN periodos per2
        ON per2.id = pt2.periodo_id
    WHERE pt2.categoria_id = cp.id
      AND (per2.ano * 100 + per2.mes)
          < (per.ano * 100 + per.mes)
    ORDER BY per2.ano DESC, per2.mes DESC
    LIMIT 1
) pt_anterior ON pt_atual.id IS NULL
WHERE cp.ativo = true;

COMMENT ON VIEW v_pontuacao_efetiva IS
    'Pontuacao efetiva por periodo e categoria. '
    'Se um periodo nao tem pontuacao propria para uma '
    'categoria, herda automaticamente do periodo anterior '
    'mais recente (fallback). Flag is_fallback indica '
    'quando os pontos vem de outro periodo.';


-- ===========================================
-- 10c. VIEW v_contratos_dashboard
-- Contratos pagos + seguros liquidados com
-- joins resolvidos (flat). Substitui query
-- com joins aninhados do PostgREST no dashboard.
-- ===========================================

CREATE OR REPLACE VIEW v_contratos_dashboard AS
SELECT
    c.id,
    c.contrato_id,
    c.valor,
    c.prazo,
    c.valor_parcela,
    c.tipo_operacao,
    c.data_cadastro,
    c.status_banco,
    c.data_status_banco,
    c.status_pagamento_cliente,
    c.data_status_pagamento,
    c.banco,
    c.convenio,
    c.num_proposta,
    c.sub_status_banco,
    c.periodo_id,
    l.nome        AS loja,
    r.nome        AS regiao,
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.grupo_meta,
    cp.conta_valor,
    cp.conta_pontuacao
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN regioes r            ON r.id  = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_pagamento_cliente = 'PAGO AO CLIENTE'
    OR
    (c.sub_status_banco = 'Liquidada'
     AND c.tipo_operacao IN ('BMG MED', 'Seguro'));

COMMENT ON VIEW v_contratos_dashboard IS
    'Contratos pagos + seguros liquidados, com joins '
    'resolvidos (loja, regiao, consultor, produto, categoria). '
    'Usado pelo dashboard em substituicao a query com joins '
    'aninhados do PostgREST. Elimina paginacao manual.';


-- ===========================================
-- 10d. VIEW v_contratos_em_analise
-- Pipeline de contratos em analise com joins
-- resolvidos (flat). Exclui pagos, cancelados
-- e seguros liquidados.
-- ===========================================

CREATE OR REPLACE VIEW v_contratos_em_analise AS
SELECT
    c.id,
    c.contrato_id,
    c.valor,
    c.prazo,
    c.valor_parcela,
    c.tipo_operacao,
    c.data_cadastro,
    c.status_banco,
    c.data_status_banco,
    c.status_pagamento_cliente,
    c.data_status_pagamento,
    c.banco,
    c.convenio,
    c.num_proposta,
    c.sub_status_banco,
    l.nome        AS loja,
    r.nome        AS regiao,
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.conta_valor
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN regioes r            ON r.id  = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_pagamento_cliente != 'PAGO AO CLIENTE'
    AND c.status_banco         != 'CANCELADO'
    AND (c.sub_status_banco IS NULL
         OR c.sub_status_banco != 'Liquidada');

COMMENT ON VIEW v_contratos_em_analise IS
    'Pipeline de contratos em analise. Exclui pagos, '
    'cancelados e seguros liquidados. Joins resolvidos '
    '(loja, regiao, consultor, produto, categoria).';


-- ===========================================
-- 10e. FUNCAO obter_contratos_em_analise
-- Encapsula logica de datas (ultimos 30 dias
-- a partir da referencia do periodo) no banco.
-- ===========================================

CREATE OR REPLACE FUNCTION obter_contratos_em_analise(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    id                        UUID,
    contrato_id               BIGINT,
    valor                     NUMERIC(15,2),
    prazo                     TEXT,
    valor_parcela             NUMERIC(15,2),
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
    loja                      TEXT,
    regiao                    TEXT,
    consultor                 TEXT,
    produto                   TEXT,
    tipo_produto              TEXT,
    subtipo                   TEXT,
    categoria_codigo          TEXT,
    grupo_dashboard           TEXT,
    conta_valor               BOOLEAN
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
    v_data_ref    DATE;
    v_data_inicio DATE;
    v_hoje        DATE := current_date;
BEGIN
    IF p_mes = EXTRACT(MONTH FROM v_hoje)::INTEGER
       AND p_ano = EXTRACT(YEAR FROM v_hoje)::INTEGER
    THEN
        v_data_ref := v_hoje;
    ELSE
        v_data_ref := (make_date(p_ano, p_mes, 1)
                       + INTERVAL '1 month'
                       - INTERVAL '1 day')::DATE;
    END IF;

    v_data_inicio := v_data_ref - INTERVAL '30 days';

    RETURN QUERY
    SELECT
        v.id, v.contrato_id, v.valor, v.prazo,
        v.valor_parcela, v.tipo_operacao,
        v.data_cadastro, v.status_banco,
        v.data_status_banco,
        v.status_pagamento_cliente,
        v.data_status_pagamento,
        v.banco, v.convenio, v.num_proposta,
        v.sub_status_banco,
        v.loja, v.regiao, v.consultor,
        v.produto, v.tipo_produto, v.subtipo,
        v.categoria_codigo, v.grupo_dashboard,
        v.conta_valor
    FROM public.v_contratos_em_analise v
    WHERE v.data_cadastro >= v_data_inicio
      AND v.data_cadastro <= v_data_ref;
END;
$$;

COMMENT ON FUNCTION obter_contratos_em_analise(INTEGER, INTEGER) IS
    'Retorna contratos em analise dos ultimos 30 dias '
    'relativos ao periodo informado. Logica de datas '
    'encapsulada no banco (antes era calculada no Python).';


-- ===========================================
-- 10f. INDICES para performance das views
-- ===========================================

CREATE INDEX IF NOT EXISTS idx_contratos_periodo_status_pag
    ON contratos (periodo_id, status_pagamento_cliente);

CREATE INDEX IF NOT EXISTS idx_contratos_cadastro_status
    ON contratos (data_cadastro, status_pagamento_cliente, status_banco);

CREATE INDEX IF NOT EXISTS idx_contratos_sub_status
    ON contratos (sub_status_banco)
    WHERE sub_status_banco IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_contratos_tipo_operacao
    ON contratos (tipo_operacao)
    WHERE tipo_operacao IN ('BMG MED', 'Seguro');


-- ===========================================
-- 11. usuarios
-- Usuarios do sistema (login no dashboard)
-- ===========================================

CREATE TABLE usuarios (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario    TEXT NOT NULL,
    nome       TEXT NOT NULL,
    perfil     TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_usuarios_usuario UNIQUE (usuario),
    CONSTRAINT chk_usuarios_perfil
        CHECK (perfil IN (
            'admin', 'gestor',
            'gerente_comercial', 'supervisor'
        ))
);

COMMENT ON TABLE usuarios IS
    'Usuarios do sistema. Perfis: '
    'admin (acesso total + gerenciamento de usuarios), '
    'gestor (visao global sem gerenciamento), '
    'gerente_comercial (acesso por regiao), '
    'supervisor (acesso por loja).';
COMMENT ON COLUMN usuarios.usuario IS
    'Login do usuario. Unico no sistema.';
COMMENT ON COLUMN usuarios.perfil IS
    'Perfil de acesso: admin, gerente_comercial, supervisor.';
COMMENT ON COLUMN usuarios.senha_hash IS
    'Hash bcrypt da senha do usuario.';

CREATE TRIGGER trg_usuarios_updated_at
    BEFORE UPDATE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 12. usuario_escopos
-- Escopos de acesso por usuario
-- Relaciona usuarios a regioes ou lojas
-- ===========================================

CREATE TABLE usuario_escopos (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id UUID NOT NULL
                   REFERENCES usuarios (id)
                   ON DELETE CASCADE,
    regiao_id  UUID REFERENCES regioes (id)
                   ON DELETE CASCADE,
    loja_id    UUID REFERENCES lojas (id)
                   ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_escopo_exclusivo
        CHECK (
            (regiao_id IS NOT NULL AND loja_id IS NULL)
            OR
            (regiao_id IS NULL AND loja_id IS NOT NULL)
        ),
    CONSTRAINT uq_escopo_regiao
        UNIQUE (usuario_id, regiao_id),
    CONSTRAINT uq_escopo_loja
        UNIQUE (usuario_id, loja_id)
);

COMMENT ON TABLE usuario_escopos IS
    'Escopos de acesso por usuario. Cada linha vincula um '
    'usuario a uma regiao (gerente_comercial) ou loja '
    '(supervisor). Admin nao precisa de escopos.';
COMMENT ON COLUMN usuario_escopos.regiao_id IS
    'Regiao de acesso (para perfil gerente_comercial).';
COMMENT ON COLUMN usuario_escopos.loja_id IS
    'Loja de acesso (para perfil supervisor).';


-- ===========================================
-- FUNCOES AUXILIARES RLS
-- ===========================================

CREATE OR REPLACE FUNCTION obter_usuario_atual_id()
RETURNS UUID
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
BEGIN
    RETURN NULLIF(
        current_setting('app.current_user_id', true), ''
    )::UUID;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

COMMENT ON FUNCTION obter_usuario_atual_id() IS
    'Retorna o UUID do usuario logado, setado pela '
    'aplicacao via SET LOCAL app.current_user_id.';


CREATE OR REPLACE FUNCTION obter_perfil_atual()
RETURNS TEXT
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
BEGIN
    RETURN NULLIF(
        current_setting('app.current_user_perfil', true), ''
    );
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

COMMENT ON FUNCTION obter_perfil_atual() IS
    'Retorna o perfil do usuario logado, setado pela '
    'aplicacao via SET LOCAL app.current_user_perfil.';


-- ===========================================
-- ROW-LEVEL SECURITY (RLS)
-- Politicas para restringir acesso por perfil
-- ===========================================

-- ── contratos ────────────────────────────────
ALTER TABLE contratos ENABLE ROW LEVEL SECURITY;

CREATE POLICY pol_contratos_admin
    ON contratos FOR ALL
    USING (obter_perfil_atual() = 'admin');

CREATE POLICY pol_contratos_gestor
    ON contratos FOR SELECT
    USING (obter_perfil_atual() = 'gestor');

CREATE POLICY pol_contratos_gerente
    ON contratos FOR SELECT
    USING (
        obter_perfil_atual() = 'gerente_comercial'
        AND loja_id IN (
            SELECT l.id FROM lojas l
            JOIN usuario_escopos ue
                ON ue.regiao_id = l.regiao_id
            WHERE ue.usuario_id = obter_usuario_atual_id()
        )
    );

CREATE POLICY pol_contratos_supervisor
    ON contratos FOR SELECT
    USING (
        obter_perfil_atual() = 'supervisor'
        AND loja_id IN (
            SELECT ue.loja_id
            FROM usuario_escopos ue
            WHERE ue.usuario_id = obter_usuario_atual_id()
        )
    );

-- ── metas ────────────────────────────────────
ALTER TABLE metas ENABLE ROW LEVEL SECURITY;

CREATE POLICY pol_metas_admin
    ON metas FOR ALL
    USING (obter_perfil_atual() = 'admin');

CREATE POLICY pol_metas_gestor
    ON metas FOR SELECT
    USING (obter_perfil_atual() = 'gestor');

CREATE POLICY pol_metas_gerente
    ON metas FOR SELECT
    USING (
        obter_perfil_atual() = 'gerente_comercial'
        AND loja_id IN (
            SELECT l.id FROM lojas l
            JOIN usuario_escopos ue
                ON ue.regiao_id = l.regiao_id
            WHERE ue.usuario_id = obter_usuario_atual_id()
        )
    );

CREATE POLICY pol_metas_supervisor
    ON metas FOR SELECT
    USING (
        obter_perfil_atual() = 'supervisor'
        AND loja_id IN (
            SELECT ue.loja_id
            FROM usuario_escopos ue
            WHERE ue.usuario_id = obter_usuario_atual_id()
        )
    );

-- ── tabelas de referencia (leitura para todos) ──
ALTER TABLE regioes ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_regioes_leitura
    ON regioes FOR SELECT USING (true);

ALTER TABLE lojas ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_lojas_leitura
    ON lojas FOR SELECT USING (true);

ALTER TABLE consultores ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_consultores_leitura
    ON consultores FOR SELECT USING (true);

ALTER TABLE supervisores ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_supervisores_leitura
    ON supervisores FOR SELECT USING (true);

ALTER TABLE periodos ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_periodos_leitura
    ON periodos FOR SELECT USING (true);

ALTER TABLE categorias_produto ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_categorias_leitura
    ON categorias_produto FOR SELECT USING (true);

ALTER TABLE produtos ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_produtos_leitura
    ON produtos FOR SELECT USING (true);

ALTER TABLE pontuacao ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_pontuacao_leitura
    ON pontuacao FOR SELECT USING (true);

-- ── usuarios (apenas admin gerencia) ─────────
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;

CREATE POLICY pol_usuarios_admin
    ON usuarios FOR ALL
    USING (obter_perfil_atual() = 'admin');

CREATE POLICY pol_usuarios_proprio
    ON usuarios FOR SELECT
    USING (id = obter_usuario_atual_id());

ALTER TABLE usuario_escopos ENABLE ROW LEVEL SECURITY;

CREATE POLICY pol_escopos_admin
    ON usuario_escopos FOR ALL
    USING (obter_perfil_atual() = 'admin');

CREATE POLICY pol_escopos_proprio
    ON usuario_escopos FOR SELECT
    USING (usuario_id = obter_usuario_atual_id());


-- ===========================================
-- INDICES
-- ===========================================

-- contratos
CREATE INDEX idx_contratos_periodo_id
    ON contratos (periodo_id);
CREATE INDEX idx_contratos_loja_id
    ON contratos (loja_id);
CREATE INDEX idx_contratos_consultor_id
    ON contratos (consultor_id);
CREATE INDEX idx_contratos_produto_id
    ON contratos (produto_id);
CREATE INDEX idx_contratos_data_status_pagamento
    ON contratos (data_status_pagamento);
CREATE INDEX idx_contratos_status_pagamento
    ON contratos (status_pagamento_cliente);
CREATE INDEX idx_contratos_status_banco
    ON contratos (status_banco);
CREATE INDEX idx_contratos_data_cadastro
    ON contratos (data_cadastro);

-- metas
CREATE INDEX idx_metas_periodo_loja
    ON metas (periodo_id, loja_id);

-- pontuacao
CREATE INDEX idx_pontuacao_periodo_id
    ON pontuacao (periodo_id);
CREATE INDEX idx_pontuacao_categoria_id
    ON pontuacao (categoria_id);

-- produtos
CREATE INDEX idx_produtos_categoria_id
    ON produtos (categoria_id);
CREATE INDEX idx_produtos_tipo
    ON produtos (tipo);

-- usuarios
CREATE INDEX idx_usuarios_usuario
    ON usuarios (usuario);
CREATE INDEX idx_usuarios_perfil
    ON usuarios (perfil);

-- usuario_escopos
CREATE INDEX idx_usuario_escopos_usuario_id
    ON usuario_escopos (usuario_id);
CREATE INDEX idx_usuario_escopos_regiao_id
    ON usuario_escopos (regiao_id);
CREATE INDEX idx_usuario_escopos_loja_id
    ON usuario_escopos (loja_id);


-- ===========================================
-- DADOS INICIAIS: categorias_produto
--
-- Baseado nos dicionarios:
--   pontuacao_loader.py → criar_mapeamento_tipo_produto()
--   settings.py → MAPEAMENTO_PRODUTOS
--   settings.py → MAPEAMENTO_COLUNAS_META
--   business_rules.py → regras de exclusao
--
-- grupo_dashboard: agrupamento no dashboard
--   CNC, SAQUE, CLT, CONSIGNADO, PACK
--   NULL = produto especial (emissao, seguro, etc.)
--
-- grupo_meta: coluna correspondente na planilha de metas
--   CNC, SAQUE, CLT, CONSIGNADO, FGTS,
--   FGTS_ANT_BENEF_13, EMISSAO, SUPER_CONTA,
--   VIDA_FAMILIAR, BMG_MED, MIX
--
-- conta_valor / conta_pontuacao:
--   false para emissao cartao, seguros
--   (contam apenas por quantidade)
-- ===========================================

INSERT INTO categorias_produto
    (codigo, nome, grupo_dashboard, grupo_meta,
     conta_valor, conta_pontuacao, ordem)
VALUES
    -- Produtos que contam para valor e pontuacao
    ('CNC',             'CNC',
     'CNC',        'CNC',
     true,  true,  1),

    ('CNC_13',          'CNC 13',
     'PACK',       'FGTS_ANT_BENEF_13',
     true,  true,  2),

    ('FGTS',            'FGTS',
     'PACK',       'FGTS',
     true,  true,  3),

    ('ANT_BENEF',       'Ant. de Benef.',
     'PACK',       'FGTS_ANT_BENEF_13',
     true,  true,  4),

    ('SAQUE',           'Saque',
     'SAQUE',      'SAQUE',
     true,  true,  5),

    ('SAQUE_BENEFICIO', 'Saque Beneficio',
     'SAQUE',      'SAQUE',
     true,  true,  6),

    ('CONSIG_BMG',      'Consig BMG',
     'CONSIGNADO', 'CONSIGNADO',
     true,  true,  7),

    ('CONSIG_ITAU',     'Consig Itau',
     'CONSIGNADO', 'CONSIGNADO',
     true,  true,  8),

    ('CONSIG_C6',       'Consig C6',
     'CONSIGNADO', 'CONSIGNADO',
     true,  true,  9),

    ('CONSIG_PRIV',     'Consig Priv',
     'CLT',        'CLT',
     true,  true,  10),

    ('PORTABILIDADE',   'Portabilidade',
     'CONSIGNADO', 'CONSIGNADO',
     true,  true,  11),

    -- Produtos especiais: contam valor/pontos
    ('SUPER_CONTA',     'Super Conta',
     NULL,         'SUPER_CONTA',
     true,  true,  12),

    -- Produtos especiais: NAO contam valor/pontos
    -- (contam apenas por quantidade)
    ('CARTAO',          'Cartao',
     NULL,         'EMISSAO',
     false, false, 13),

    ('BMG_MED',         'BMG Med',
     NULL,         'BMG_MED',
     false, false, 14),

    ('SEGURO_VIDA',     'Seguro Vida Familiar',
     NULL,         'VIDA_FAMILIAR',
     false, false, 15);


-- ===========================================
-- REFERENCIA: Mapeamento TIPO_PRODUTO →
-- categoria_id (para importacao de produtos)
-- ===========================================

-- Ao importar dados da planilha Tabelas_{mes}_{ano}.xlsx,
-- o campo TIPO (coluna tipo no banco) deve ser mapeado
-- para categoria_id usando esta correspondencia:
--
-- tipo (planilha) → codigo (categorias_produto)
-- ------------------------------------------------
-- CNC             → CNC
-- CNC 13º / CNC 13 → CNC_13
-- CNC ANT         → ANT_BENEF
-- SAQUE           → SAQUE
-- SAQUE BENEFICIO → SAQUE_BENEFICIO
-- CONSIG / CONSIG BMG → CONSIG_BMG
-- CONSIG ITAU     → CONSIG_ITAU
-- CONSIG C6       → CONSIG_C6
-- CONSIG PRIV     → CONSIG_PRIV
-- FGTS            → FGTS
-- EMISSAO / EMISSAO CB / EMISSAO CC → CARTAO
-- Portabilidade   → PORTABILIDADE
-- BMG MED         → BMG_MED
-- Seguro          → SEGURO_VIDA
-- (SUBTIPO = SUPER CONTA) → SUPER_CONTA


-- ===========================================
-- REFERENCIA: Mapeamento de Metas
-- Desnormalizacao: colunas da planilha →
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
