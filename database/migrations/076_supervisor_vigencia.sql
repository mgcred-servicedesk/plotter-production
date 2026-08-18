-- =====================================================
-- Migracao 076: supervisor_vigencia
--               (versionamento temporal do papel de supervisor)
--
-- Motivo:
-- A tabela `supervisores` e uma FOTO DO PRESENTE — a 063
-- (fn_supervisores_replace) reforcou isso: foto unica, quem sai da
-- planilha deixa de existir. Mas ela e usada como filtro RETROATIVO
-- sobre toda a historia (excluir_supervisores, headcount do Caderno),
-- entao o papel de hoje reescreve os meses passados. O erro e
-- bidirecional:
--
--   1. PROMOCAO (consultor -> supervisor): ao entrar na planilha, os
--      meses em que a pessoa vendia como consultor somem das visoes
--      consultor-level. O headcount da loja cai em 1 NOS MESES
--      PASSADOS e a media por consultor daqueles meses infla.
--   2. SAIDA DA SUPERVISAO: ao sair da planilha, os meses em que ela
--      ERA supervisor voltam a poluir o ranking de consultores.
--
-- A direcao (2) ja aconteceu em producao: os 5 ex-supervisores que o
-- progress doc 2026-07-08 mandava explicitamente NAO deletar foram
-- removidos pelo replace da 063 — 86 contratos entre 05/2025 e 03/2026
-- voltaram a contar como producao de consultor. O mesmo doc previa o
-- desfecho: "aí seria caso de vigencia temporal, como
-- loja_regiao_vigencia".
--
-- Desenho (reusa o que o projeto ja validou em 043 -> 049, em vez de
-- inventar outro):
--   * `supervisores` PERMANECE como ponteiro do organograma ATUAL
--     (mesmo papel de lojas.regiao_id). A linha ABERTA daqui
--     (vigencia_fim IS NULL) espelha `supervisores`.
--   * supervisor_vigencia guarda o par (pessoa, loja) vigente em cada
--     janela de tempo. A invariante e mantida pelas funcoes da 077.
--
-- Leitura point-in-time: e supervisor na competencia C quem tem uma
-- linha cobrindo o 1o DIA de C. Ancora decidida com o usuario em
-- 2026-08-18: o papel vigente no dia 1o vale para o mes inteiro — uma
-- regra so para producao e headcount, sem mes pela metade (promovido em
-- 20/jul => julho fecha como consultor, agosto e o 1o mes como
-- supervisor).
--
-- ESTAGIO 1 do rollout (no-op observavel): apos o backfill, todo
-- supervisor atual tem UMA linha aberta com piso 2020-01-01, entao a
-- resolucao via vigencia reproduz exatamente o comportamento de hoje.
-- NADA consome esta tabela ainda — as funcoes de manutencao entram na
-- 077, as correcoes de historia na 078 e os leitores na 079.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela supervisor_vigencia
--
-- Chave de identidade = NOME NORMALIZADO, nao FK: e a moeda que o
-- codebase inteiro ja usa (`supervisores` nunca teve vinculo com
-- `consultores` — ver business-rules.md, "Nao existe FK
-- supervisor->consultor"). A coluna e GERADA a partir de `nome`, entao
-- as duas nunca divergem e o match deixa de depender do ETL uniformizar
-- espacos/caixa (follow-up pendente do progress doc 2026-07-09).
--
-- regiao_id NAO existe aqui de proposito: a regiao point-in-time ja vem
-- de loja_regiao_vigencia (043) via loja. Replicar aqui criaria uma
-- segunda fonte de verdade — a 063 ja tinha centralizado isso em
-- lojas.regiao_id.
-- ===========================================

CREATE TABLE IF NOT EXISTS supervisor_vigencia (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome             TEXT NOT NULL,
    nome_normalizado TEXT GENERATED ALWAYS AS (
                         upper(regexp_replace(
                             btrim(nome), '[[:space:]]+', ' ', 'g'))
                     ) STORED,
    loja_id          UUID REFERENCES lojas (id)
                          ON DELETE SET NULL,
    vigencia_inicio  DATE NOT NULL,
    vigencia_fim     DATE,   -- NULL = vigente (linha aberta)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- fim (quando definido) sempre depois do inicio
    CONSTRAINT chk_sv_vigencia_ordem CHECK (
        vigencia_fim IS NULL OR vigencia_fim > vigencia_inicio
    ),
    CONSTRAINT chk_sv_nome_nao_vazio CHECK (btrim(nome) <> '')
);

COMMENT ON TABLE supervisor_vigencia IS
    'Ledger historico (SCD2) do papel de supervisor por janela de tempo, '
    'na granularidade (pessoa, loja) — a mesma de uq_supervisores_nome_loja, '
    'porque supervisor multi-loja e regra documentada. A linha aberta '
    '(vigencia_fim IS NULL) espelha `supervisores` (organograma atual). '
    'Usado para responder "era supervisor na competencia C" sem reescrever '
    'o historico quando alguem e promovido, remanejado ou sai da supervisao. '
    'Resolucao por competencia: linha que cobre o 1o dia do mes.';

COMMENT ON COLUMN supervisor_vigencia.nome_normalizado IS
    'Gerada a partir de `nome` (upper + colapso de espacos). Chave de match '
    'com consultores.nome / v_contratos_dashboard.consultor.';

DROP TRIGGER IF EXISTS trg_sv_updated_at ON supervisor_vigencia;
CREATE TRIGGER trg_sv_updated_at
    BEFORE UPDATE ON supervisor_vigencia
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 2. Indices / invariantes
-- ===========================================

-- No maximo UMA linha aberta por (pessoa, loja) — espelha
-- uq_supervisores_nome_loja. NAO e por pessoa: "supervisor multi-loja
-- soma os consultores de todas as suas lojas" (business-rules.md), logo
-- duas linhas abertas da mesma pessoa em lojas diferentes sao validas.
--
-- coalesce no loja_id: `supervisores.loja_id` e nullable (a 063 ainda
-- reporta `sem_loja` no retorno) e UNIQUE com NULLS DISTINCT nao
-- dispara — foi exatamente assim que o import antigo duplicava linhas
-- de loja nula a cada carga. O sentinela zerado faz NULL se comportar
-- como valor.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sv_supervisor_loja_aberta
    ON supervisor_vigencia (
        nome_normalizado,
        (coalesce(loja_id, '00000000-0000-0000-0000-000000000000'::uuid))
    )
    WHERE vigencia_fim IS NULL;

-- Resolucao por range (pessoa + janela de vigencia).
CREATE INDEX IF NOT EXISTS idx_sv_nome_periodo
    ON supervisor_vigencia (nome_normalizado, vigencia_inicio, vigencia_fim);


-- ===========================================
-- 3. Backfill: uma linha aberta por supervisor atual
--
-- Piso de vigencia = 2020-01-01 (mesmo limite inferior de periodos.ano
-- e o mesmo piso da 043), seguramente antes de qualquer contrato.
-- Decisao do usuario em 2026-08-18: "congelar + corrigir casos
-- conhecidos" — o piso reproduz exatamente o numero publicado hoje, e a
-- correcao de historia (promocoes conhecidas + reabertura dos 5
-- ex-supervisores, que NAO estao mais em `supervisores` e por isso nao
-- sao alcancados por este backfill) vem na 078, com datas reais.
--
-- Idempotente: so insere para pares (pessoa, loja) que ainda nao tem
-- nenhuma linha de vigencia.
-- ===========================================

INSERT INTO supervisor_vigencia (nome, loja_id, vigencia_inicio)
SELECT s.nome, s.loja_id, DATE '2020-01-01'
FROM supervisores s
WHERE btrim(coalesce(s.nome, '')) <> ''
  AND NOT EXISTS (
      SELECT 1 FROM supervisor_vigencia v
      WHERE v.nome_normalizado = upper(regexp_replace(
                btrim(s.nome), '[[:space:]]+', ' ', 'g'))
        AND coalesce(v.loja_id, '00000000-0000-0000-0000-000000000000'::uuid)
          = coalesce(s.loja_id, '00000000-0000-0000-0000-000000000000'::uuid)
  );


-- ===========================================
-- 4. RLS + leitura: tabela-dimensao, legivel globalmente
--
-- Mesmo padrao de 043 (loja_regiao_vigencia) e das tabelas de
-- referencia do schema.sql: RLS HABILITADA (exigencia do Supabase p/
-- tabelas do schema public expostas via API) com policy permissiva de
-- SELECT. `supervisores` ja e globalmente legivel
-- (pol_supervisores_leitura) e esta tabela nao acrescenta nada
-- sensivel — e a base do recorte, nao o recorte, e os nomes servem
-- so para EXCLUSAO (nunca sao renderizados; ver progress 2026-07-09).
-- Sem policy de escrita: backfill e funcoes da 077 rodam via
-- service_role/owner, que ignoram RLS.
-- ===========================================

ALTER TABLE supervisor_vigencia ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_sv_leitura ON supervisor_vigencia;
CREATE POLICY pol_sv_leitura
    ON supervisor_vigencia FOR SELECT USING (true);

GRANT SELECT ON supervisor_vigencia TO anon, authenticated;


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- 1) Backfill cobriu todo supervisor atual, 1 linha aberta cada:
--
--    SELECT count(*) AS vigencias_abertas
--    FROM supervisor_vigencia WHERE vigencia_fim IS NULL;
--    -- Esperado: igual a `SELECT count(*) FROM supervisores`
--    --           (47 linhas em 2026-08-18).
--
-- 2) Nenhum supervisor atual ficou de fora:
--
--    SELECT s.nome, s.loja_id
--    FROM supervisores s
--    WHERE NOT EXISTS (
--        SELECT 1 FROM supervisor_vigencia v
--        WHERE v.nome_normalizado = upper(regexp_replace(
--                  btrim(s.nome), '[[:space:]]+', ' ', 'g'))
--          AND v.vigencia_fim IS NULL
--    );
--    -- Esperado: 0 linhas.
--
-- 3) No-op observavel — a resolucao point-in-time em QUALQUER
--    competencia devolve exatamente a lista de hoje (piso 2020-01-01):
--
--    SELECT count(DISTINCT nome_normalizado)
--    FROM supervisor_vigencia
--    WHERE vigencia_inicio <= DATE '2025-05-01'
--      AND (vigencia_fim IS NULL OR vigencia_fim > DATE '2025-05-01');
--    -- Esperado: 47 — mesmo numero de nomes distintos de `supervisores`.
--
-- 4) Coluna gerada normalizando de fato:
--
--    SELECT nome, nome_normalizado FROM supervisor_vigencia LIMIT 5;
--
-- Reversao (estagio 1 nao tem consumidor — seguro):
--    DROP TABLE supervisor_vigencia;
-- =====================================================
