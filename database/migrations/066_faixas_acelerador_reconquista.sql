-- =====================================================
-- Migracao 066: faixas do acelerador combinado
--               Reconquista + Cobranca Consignavel
--
-- Adiciona:
--   - faixas_acelerador_reconquista        (tabela de config)
--   - obter_faixa_acelerador_reconquista() (RPC de lookup)
--   - seed das 4 faixas vigentes em 08/2026
--
-- MOTIVACAO
-- A partir de 08/2026 o dashboard passa a calcular oficialmente
-- o acelerador combinado de consultor/supervisor:
--     total = reconquistas EFETIVADAS + Cobranca Consignavel
-- e mapear esse total para uma FAIXA de atingimento:
--
--     0 a 2 | 3 a 5 | 6 a 8 | 9 ou mais
--
-- Os limites das faixas podem mudar de um mes para o outro. Por
-- isso NAO sao hardcoded em Python (como o
-- _faixa_premio_conversao de src/dashboard/loaders.py, que e por
-- percentual e tem limites fixos): viram dado, editavel por SQL,
-- sem deploy de codigo.
--
-- PADRAO SEGUIDO: `pontuacao` + obter_pontuacao_periodo()
-- (migration 013). Vigencia por `periodo_id` (FK para periodos,
-- mesma relacao de pontuacao.periodo_id) e fallback TEMPORAL na
-- RPC: se o periodo pedido nao tem faixas cadastradas, retrocede
-- ate 24 meses buscando o periodo anterior mais recente que
-- tenha. Decisao de negocio: vigencia por periodo, nao por
-- intervalo de datas (nao precisa do SCD2 de
-- loja_regiao_vigencia).
--
-- SEM VALOR DE PREMIO — DE PROPOSITO
-- A tabela guarda apenas o ROTULO da faixa. Decisao explicita do
-- usuario: o dashboard exibe a faixa atingida ("3 a 5"), nunca o
-- premio/deflator em R$ ou %. O valor e resolvido fora do
-- dashboard. Nao adicionar coluna de premio aqui sem revisitar
-- essa decisao.
--
-- `is_deflator` NAO e valor de premio: e um FLAG de natureza da
-- faixa (a faixa de desconto vs. as de premio positivo), para que
-- a UI saiba destacar a faixa negativa sem hardcodar o limiar em
-- Python/JS. Continua sem quanto — so qual.
--
-- "MAIOR QUE 9" = qtd_max NULL, e a comparacao e >= 9 (o 9 exato
-- entra na ultima faixa) — confirmado pelo usuario. Isso fecha a
-- lacuna que existiria entre "6 a 8" e um ">9" estrito.
--
-- ALCANCE REAL DA RLS AQUI (mesmo caveat da migration 064)
-- O dashboard conecta com uma chave unica de service_role, que
-- tem BYPASSRLS: a policy abaixo NAO e executada por ele. Ela
-- vale como defense-in-depth para acessos com chave
-- anon/authenticated. Uma faixa e limiar de contagem + rotulo:
-- nenhum dado pessoal, nenhum valor de contrato, nenhum valor de
-- premio. Por isso a leitura e ampla — identica ao tratamento de
-- `pontuacao` (schema.sql: pol_pontuacao_leitura, SELECT
-- USING (true), sem policy de escrita). Ver docs/agents/rls.md.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela
-- ===========================================

CREATE TABLE IF NOT EXISTS faixas_acelerador_reconquista (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id  UUID NOT NULL
                    REFERENCES periodos (id)
                    ON DELETE CASCADE,
    qtd_min     INTEGER NOT NULL,
    qtd_max     INTEGER,
    rotulo      TEXT NOT NULL,
    ordem       INTEGER NOT NULL,
    is_deflator BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_faixas_acel_reconq_periodo_ordem
        UNIQUE (periodo_id, ordem),
    CONSTRAINT chk_faixas_acel_reconq_qtd_min
        CHECK (qtd_min >= 0),
    CONSTRAINT chk_faixas_acel_reconq_qtd_max
        CHECK (qtd_max IS NULL OR qtd_max >= qtd_min),
    CONSTRAINT chk_faixas_acel_reconq_rotulo
        CHECK (length(btrim(rotulo)) > 0)
);

-- Idempotencia: cobre uma execucao anterior deste mesmo arquivo,
-- que criava a tabela sem `is_deflator` (o CREATE TABLE acima e
-- IF NOT EXISTS e nao adiciona colunas a uma tabela ja existente).
ALTER TABLE faixas_acelerador_reconquista
    ADD COLUMN IF NOT EXISTS is_deflator BOOLEAN NOT NULL DEFAULT false;

COMMENT ON TABLE faixas_acelerador_reconquista IS
    'Faixas de atingimento do acelerador combinado '
    '(reconquistas EFETIVADAS + Cobranca Consignavel) por '
    'consultor/supervisor, vigentes por periodo. Configuracao '
    'editavel por SQL, sem deploy: os limites podem mudar de um '
    'mes para o outro. Guarda apenas o ROTULO da faixa — o '
    'premio/deflator em R$ e resolvido fora do dashboard e '
    'NUNCA e exibido por ele (decisao de negocio). Consultada '
    'via obter_faixa_acelerador_reconquista(), que aplica '
    'fallback temporal no mesmo espirito de '
    'obter_pontuacao_periodo().';

COMMENT ON COLUMN faixas_acelerador_reconquista.periodo_id IS
    'Periodo de vigencia da faixa (FK para periodos, mesma '
    'relacao de pontuacao.periodo_id). Um periodo sem nenhuma '
    'linha aqui faz a RPC retroceder para o periodo anterior '
    'mais recente que tenha faixas.';

COMMENT ON COLUMN faixas_acelerador_reconquista.qtd_min IS
    'Limite inferior INCLUSIVO da contagem combinada.';

COMMENT ON COLUMN faixas_acelerador_reconquista.qtd_max IS
    'Limite superior INCLUSIVO da contagem combinada. NULL = '
    'sem limite superior — e o caso da faixa "9 ou mais", '
    'cadastrada como qtd_min=9 / qtd_max=NULL (ou seja, >= 9: '
    'o 9 exato entra nesta faixa, sem lacuna com "6 a 8"). '
    'Rotulo "9 ou mais", nao "Maior que 9" — a tabela de negocio '
    'original dizia "Maior que 9", mas o 9 exato foi confirmado '
    'como incluso nesta faixa; o rotulo evita a contradicao.';

COMMENT ON COLUMN faixas_acelerador_reconquista.rotulo IS
    'Texto exibido no dashboard (ex: "3 a 5"). Unica saida da '
    'RPC — nao existe coluna de premio nesta tabela.';

COMMENT ON COLUMN faixas_acelerador_reconquista.ordem IS
    'Ordem de avaliacao/exibicao dentro do periodo. Desempata '
    'faixas sobrepostas: a RPC retorna a de menor ordem.';

COMMENT ON COLUMN faixas_acelerador_reconquista.is_deflator IS
    'TRUE na faixa que representa DESCONTO (deflator) sobre o '
    'premio total; FALSE nas faixas de premio positivo. Nao e '
    'valor: e a natureza da faixa, para a UI destacar a faixa '
    'negativa sem hardcodar o limiar (hoje "0 a 2"). Se os '
    'limites mudarem, basta mover a flag de linha — nenhum '
    'deploy de codigo.';


-- ===========================================
-- 2. RLS
--
-- Replica o tratamento de `pontuacao` (schema.sql, secao
-- "tabelas de referencia"): leitura liberada, nenhuma policy de
-- escrita — a manutencao das faixas e feita por SQL Editor /
-- service_role, nao pela UI. Fail-closed para escrita: com RLS
-- ligada e sem policy de INSERT/UPDATE/DELETE, nenhum papel
-- sujeito a RLS consegue gravar.
-- ===========================================

ALTER TABLE faixas_acelerador_reconquista ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_faixas_acel_reconq_leitura
    ON faixas_acelerador_reconquista;

CREATE POLICY pol_faixas_acel_reconq_leitura
    ON faixas_acelerador_reconquista FOR SELECT
    USING (true);


-- ===========================================
-- 3. Seed — 4 faixas vigentes a partir de 08/2026
--
-- O periodo 08/2026 e criado se ainda nao existir (mesmo
-- ON CONFLICT (mes, ano) documentado em database/INTEGRACAO.md;
-- referencia = abreviacao de 3 letras + /AA).
-- Idempotente: o seed usa ON CONFLICT sobre
-- (periodo_id, ordem) e nao sobrescreve ajustes manuais.
-- ===========================================

INSERT INTO periodos (mes, ano, referencia)
VALUES (8, 2026, 'Ago/26')
ON CONFLICT (mes, ano) DO NOTHING;

-- So a primeira faixa e deflator (desconto sobre o premio total);
-- as demais sao premio positivo.
INSERT INTO faixas_acelerador_reconquista
    (periodo_id, qtd_min, qtd_max, rotulo, ordem, is_deflator)
SELECT p.id, f.qtd_min, f.qtd_max, f.rotulo, f.ordem, f.is_deflator
FROM periodos p
CROSS JOIN (
    VALUES
        (0, 2,    '0 a 2',      1, true),
        (3, 5,    '3 a 5',      2, false),
        (6, 8,    '6 a 8',      3, false),
        (9, NULL, '9 ou mais',  4, false)
) AS f (qtd_min, qtd_max, rotulo, ordem, is_deflator)
WHERE p.mes = 8 AND p.ano = 2026
ON CONFLICT ON CONSTRAINT uq_faixas_acel_reconq_periodo_ordem
DO NOTHING;


-- ===========================================
-- 4. RPC obter_faixa_acelerador_reconquista
--
-- Espelha obter_pontuacao_periodo (013):
--   - LANGUAGE plpgsql STABLE, SET search_path = '' (tudo
--     qualificado com public.), SECURITY INVOKER implicito —
--     herda a RLS do chamador.
--   - Fallback temporal: retrocede ate 24 meses ate achar um
--     periodo com pelo menos uma faixa cadastrada.
--   - is_fallback = TRUE sinaliza que o rotulo veio de um
--     periodo anterior ao pedido.
--   - is_deflator repassa a natureza da faixa (desconto x premio
--     positivo), para o consumidor nao reimplementar o limiar.
--
-- Retorna ZERO linhas (recurso "desligado" para o chamador)
-- quando:
--   a) nenhum periodo nos ultimos 24 meses tem faixas — ex.:
--      apuracao anterior a 08/2026, antes da vigencia da regra;
--   b) p_qtd e NULL;
--   c) p_qtd nao cai em nenhuma faixa cadastrada.
-- O consumidor deve tratar "sem linha" como "sem faixa" e nao
-- exibir o bloco — nunca inventar uma faixa default.
--
-- COALESCE(qtd_max, 2147483647): faixa aberta no topo. Usa o
-- maximo do INTEGER em vez de um teto arbitrario, para que
-- nenhuma contagem real fique de fora.
-- ===========================================

-- DROP antes do CREATE: o RETURNS TABLE ganhou `is_deflator`, e
-- CREATE OR REPLACE nao muda o tipo de retorno de uma funcao ja
-- existente. Sem efeito numa base que nunca aplicou esta migracao.
DROP FUNCTION IF EXISTS obter_faixa_acelerador_reconquista(
    INTEGER, INTEGER, INTEGER
);

CREATE OR REPLACE FUNCTION obter_faixa_acelerador_reconquista(
    p_qtd INTEGER,
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    rotulo      TEXT,
    is_fallback BOOLEAN,
    is_deflator BOOLEAN
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
    -- Sem contagem nao ha faixa a resolver.
    IF p_qtd IS NULL THEN
        RETURN;
    END IF;

    -- Fallback temporal: retroceder ate achar periodo com pelo
    -- menos uma faixa cadastrada.
    LOOP
        SELECT p.id INTO v_periodo_id
        FROM public.periodos p
        WHERE p.mes = v_mes_busca AND p.ano = v_ano_busca;

        IF v_periodo_id IS NOT NULL THEN
            SELECT EXISTS(
                SELECT 1
                FROM public.faixas_acelerador_reconquista f
                WHERE f.periodo_id = v_periodo_id
            ) INTO v_tem_dados;

            EXIT WHEN v_tem_dados;
        END IF;

        v_tentativas := v_tentativas + 1;
        IF v_tentativas > 24 THEN
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
        f.rotulo,
        (v_mes_busca <> p_mes
         OR v_ano_busca <> p_ano)              AS is_fallback,
        f.is_deflator
    FROM public.faixas_acelerador_reconquista f
    WHERE f.periodo_id = v_periodo_id
      AND p_qtd BETWEEN f.qtd_min
                    AND COALESCE(f.qtd_max, 2147483647)
    ORDER BY f.ordem
    LIMIT 1;
END;
$$;

COMMENT ON FUNCTION obter_faixa_acelerador_reconquista(INTEGER, INTEGER, INTEGER) IS
    'Resolve a faixa do acelerador combinado (reconquistas '
    'EFETIVADAS + Cobranca Consignavel) para uma contagem e um '
    'periodo. Fallback temporal identico ao de '
    'obter_pontuacao_periodo: se o periodo pedido nao tem faixas '
    'cadastradas, retrocede ate 24 meses e sinaliza '
    'is_fallback=true. Retorna 0 linhas quando nao ha faixa '
    'aplicavel (periodo anterior a vigencia da regra, p_qtd NULL '
    'ou contagem fora das faixas) — o consumidor NAO deve '
    'assumir faixa default. Devolve rotulo + is_deflator (natureza '
    'da faixa): o VALOR do premio/deflator nao existe nesta tabela '
    'e nao e exibido pelo dashboard.';


-- ===========================================
-- 5. Validacao pos-migracao
-- ===========================================
-- 1) Seed aplicado (4 linhas para Ago/26, so a 1a com deflator):
--
--   SELECT p.referencia, f.ordem, f.qtd_min, f.qtd_max, f.rotulo,
--          f.is_deflator
--   FROM faixas_acelerador_reconquista f
--   JOIN periodos p ON p.id = f.periodo_id
--   ORDER BY p.ano, p.mes, f.ordem;
--   -- Esperado: is_deflator = true so na ordem 1 ("0 a 2")
--
-- 2) Bordas de faixa (08/2026):
--
--   SELECT q, (SELECT rotulo
--              FROM obter_faixa_acelerador_reconquista(q, 8, 2026))
--   FROM generate_series(0, 12) AS q;
--   -- Esperado: 0-2 -> "0 a 2"; 3-5 -> "3 a 5"; 6-8 -> "6 a 8";
--   --           9,10,11,12 -> "9 ou mais"
--
-- 2b) Flag de deflator vinda da RPC (nao da UI):
--
--   SELECT q, (SELECT is_deflator
--              FROM obter_faixa_acelerador_reconquista(q, 8, 2026))
--   FROM generate_series(0, 12) AS q;
--   -- Esperado: true para 0,1,2; false do 3 em diante
--
-- 3) Fallback temporal (periodo posterior sem faixas proprias):
--
--   SELECT * FROM obter_faixa_acelerador_reconquista(4, 9, 2026);
--   -- Esperado: rotulo = "3 a 5", is_fallback = true,
--   --           is_deflator = false
--
-- 4) Antes da vigencia (nenhum periodo <= 07/2026 tem faixas):
--
--   SELECT count(*) FROM obter_faixa_acelerador_reconquista(4, 7, 2026);
--   -- Esperado: 0 linhas
--
-- 5) RLS ligada com leitura ampla e sem policy de escrita:
--
--   SELECT relrowsecurity FROM pg_class
--   WHERE relname = 'faixas_acelerador_reconquista';   -- true
--
--   SELECT policyname, cmd FROM pg_policies
--   WHERE tablename = 'faixas_acelerador_reconquista';
--   -- Esperado: apenas pol_faixas_acel_reconq_leitura / SELECT
