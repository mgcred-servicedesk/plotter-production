-- =====================================================
-- Migracao 086: consultor_vigencia
--               (versionamento temporal do cadastro de consultor)
--
-- Motivo:
-- `consultores` e uma FOTO DO PRESENTE — nao tem vigencia temporal.
-- Mas o headcount do Caderno (073 -> 085) a le como se descrevesse a
-- competencia, entao o cadastro de HOJE reescreve todos os meses. O
-- efeito foi medido em 2026-08-18 sobre os 14 snapshots publicados:
--
--   `activeRegistered`  = 163 em TODAS as competencias (05/2025 a 07/2026);
--   `activeConsultants` = 119 em 13 das 14.
--
-- Um headcount identico por 14 meses nao descreve mes nenhum. O erro
-- tem quatro direcoes, todas da mesma causa:
--
--   1. CONTRATACAO: quem entrou depois conta no passado. Em 07/2026,
--      5 pessoas cadastradas entre 11 e 18/08 ja contavam em julho —
--      e tambem em 05/2025. Em 03/2026, 29 dos 121 contados (24%)
--      so entraram no cadastro depois do mes fechar.
--   2. DESLIGAMENTO: quem saiu some do passado. Em 07/2026, 7 pessoas
--      que venderam no mes ficaram fora do denominador por constarem
--      'Desligado (a)' hoje.
--   3. TRANSFERENCIA: 77 das 326 pessoas do cadastro (24%) tem mais de
--      uma loja. So a loja atual vence, entao um quarto do quadro esta
--      atribuido a loja de hoje nos 14 meses — isso desloca a
--      PRODUTIVIDADE POR LOJA, que e o capitulo principal do Caderno.
--   4. LOJA FECHADA: `lojas.ativo` tambem e foto do presente. Os 11
--      PDVs inativos hoje derrubam do headcount quem trabalhava neles
--      em 2025, quando estavam abertos.
--
-- Desenho: mesmo SCD2 que a 076 validou para `supervisor_vigencia`,
-- na granularidade (pessoa, loja) — que e a granularidade do
-- headcount_loja da 085.
--   * `consultores` PERMANECE como o cadastro atual (status + loja de
--     hoje). A linha ABERTA daqui espelha o cadastro ativo.
--   * consultor_vigencia guarda a janela em que a pessoa esteve
--     vinculada aquela loja.
--
-- Leitura point-in-time: esta ativo na competencia C quem tem linha
-- cobrindo o ULTIMO DIA de C — mesma ancora da 085, para que headcount
-- e producao nunca discordem sobre o mesmo mes.
--
-- BACKFILL DERIVADO DA PRODUCAO (decisao do usuario em 2026-08-18).
-- A alternativa era o piso 2020-01-01 da 076, que reproduz o numero de
-- hoje e so melhora quando alguem digitar datas. Aqui as janelas saem
-- de `contratos` (139.527 linhas, `consultor_id`/`loja_id`/
-- `data_cadastro` sem nenhum nulo): a pessoa estava naquela loja nos
-- meses em que registrou contrato ali. Usa `contratos`, nao
-- `v_contratos_dashboard`, porque a view e so de PAGOS — 105.705
-- linhas. Quem registrou 20 contratos cancelados naquele mes estava
-- trabalhando do mesmo jeito, e a pergunta aqui e presenca, nao
-- producao. A data e `data_cadastro` (registro do contrato), nunca
-- `data_status_pagamento`: pagamento arrasta depois da saida.
--
-- LIMITE CONHECIDO: `contratos` comeca em 05/2025, entao ninguem tem
-- inicio anterior a isso e as competencias de 2025 ficam SUBESTIMADAS
-- (quem ja trabalhava e nao vendeu naquele mes nao deixa rastro). A
-- folga sobre os produtores cai de +3..+5 nos meses recentes para +2
-- em 05/2025. Corrigir isso exige data real de admissao — e o que a
-- coluna DESDE da 088 passa a trazer, como a 082 fez para supervisor.
--
-- ESTAGIO 1 do rollout: NADA le esta tabela ainda. As funcoes de
-- manutencao entram na 087, a coluna DESDE na 088 e os leitores
-- (obter_caderno_fechamento + carregar_consultores_ativos) na 089.
-- Nenhum numero publicado muda com esta migration.
--
-- Efeito medido do backfill (simulado sobre os dados de 2026-08-18,
-- resolvendo pela ancora da 085 e sem o filtro de loja ativa, que a
-- 089 remove por causa da direcao 4 acima):
--
--   comp      publicado  ledger     delta   produtores   folga
--   05/2025         119     102       -17          100      +2
--   06/2025         119     106       -13          100      +6
--   07/2025         119     106       -13           99      +7
--   08/2025         119     111        -8          100     +11
--   10/2025         119     120        +1          114      +6
--   11/2025         119     113        -6          108      +5
--   12/2025         119     128        +9          125      +3
--   01/2026         119     124        +5          121      +3
--   02/2026         119     120        +1          117      +3
--   03/2026         119     127        +8          123      +4
--   04/2026         119     131       +12          128      +3
--   05/2026         119     127        +8          123      +4
--   06/2026         119     127        +8          122      +5
--   07/2026         118     118        +0          114      +4
--
-- O headcount passa a VARIAR (102 -> 131 -> 118) em vez do 119
-- achatado, e a invariante `ledger >= produtores` vale nas 14
-- competencias — nenhum mes conta menos gente do que a que
-- comprovadamente vendeu. A folga positiva e o que o denominador
-- deveria capturar desde sempre: o ativo que nao vendeu nada.
--
-- Executar no Supabase SQL Editor, depois da 085.
-- =====================================================


-- ===========================================
-- 1. Tabela consultor_vigencia
--
-- Chave de identidade = NOME NORMALIZADO, como na 076. `contratos` tem
-- FK real (`consultor_id`), mas ela aponta para UMA LINHA de
-- `consultores`, e a mesma pessoa tem varias (422 linhas para 326
-- nomes distintos — uma por loja em que passou). O nome normalizado e
-- a unica chave estavel de PESSOA no schema, e e a moeda que
-- excluir_supervisores/headcount ja usam. Verificado em 2026-08-18:
-- 0 de 289 nomes divergem entre contratos e cadastro.
--
-- Coluna GERADA, entao `nome` e `nome_normalizado` nunca divergem e o
-- match deixa de depender de o ETL uniformizar caixa/espacos.
-- ===========================================

CREATE TABLE IF NOT EXISTS consultor_vigencia (
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
    origem           TEXT NOT NULL DEFAULT 'BACKFILL_PRODUCAO',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_cv_vigencia_ordem CHECK (
        vigencia_fim IS NULL OR vigencia_fim > vigencia_inicio
    ),
    CONSTRAINT chk_cv_nome_nao_vazio CHECK (btrim(nome) <> ''),
    CONSTRAINT chk_cv_origem CHECK (
        origem IN ('BACKFILL_PRODUCAO', 'BACKFILL_PISO', 'ETL', 'MANUAL')
    )
);

COMMENT ON TABLE consultor_vigencia IS
    'Ledger historico (SCD2) do vinculo consultor->loja por janela de tempo. '
    'A linha aberta (vigencia_fim IS NULL) espelha o cadastro ativo de '
    '`consultores`. Responde "estava ativo, e em qual loja, na competencia C" '
    'sem que contratacao, desligamento ou transferencia reescrevam o passado. '
    'Resolucao por competencia: linha que cobre o ULTIMO dia do mes (ancora '
    'da migration 085, a mesma de supervisor_vigencia).';

COMMENT ON COLUMN consultor_vigencia.origem IS
    'Procedencia da linha: BACKFILL_PRODUCAO (janela inferida de `contratos` '
    'na 086), BACKFILL_PISO (ativo sem nenhum contrato — piso 2020-01-01), '
    'ETL (import da HC_Colaboradores) ou MANUAL (correcao). Serve para '
    'distinguir o que e FATO informado do que e INFERENCIA, e para a 088 '
    'saber quais linhas pode sobrescrever com a data real da coluna DESDE.';

COMMENT ON COLUMN consultor_vigencia.nome_normalizado IS
    'Gerada a partir de `nome` (upper + colapso de espacos). Chave de match '
    'com consultores.nome, supervisor_vigencia.nome_normalizado e '
    'v_contratos_dashboard.consultor.';

DROP TRIGGER IF EXISTS trg_cv_updated_at ON consultor_vigencia;
CREATE TRIGGER trg_cv_updated_at
    BEFORE UPDATE ON consultor_vigencia
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 2. Indices / invariantes
--
-- No maximo UMA linha aberta por (pessoa, loja). Nao e por pessoa: a
-- transferencia abre a janela nova antes que se saiba a data real de
-- fim da antiga em alguns fluxos, e o ledger de supervisor ja provou
-- que travar por pessoa engessa o ETL. O sentinela no coalesce faz
-- NULL se comportar como valor (UNIQUE com NULLS DISTINCT nao dispara)
-- — mesma armadilha que duplicava linhas de loja nula na 076.
-- ===========================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_cv_consultor_loja_aberta
    ON consultor_vigencia (
        nome_normalizado,
        (coalesce(loja_id, '00000000-0000-0000-0000-000000000000'::uuid))
    )
    WHERE vigencia_fim IS NULL;

CREATE INDEX IF NOT EXISTS idx_cv_nome_periodo
    ON consultor_vigencia (nome_normalizado, vigencia_inicio, vigencia_fim);

-- Resolucao do headcount por loja numa competencia (a 089 agrupa por
-- loja_id filtrando pela janela).
CREATE INDEX IF NOT EXISTS idx_cv_loja_periodo
    ON consultor_vigencia (loja_id, vigencia_inicio, vigencia_fim);


-- ===========================================
-- 3. Backfill derivado de `contratos`
--
-- Idempotente: so roda se a tabela estiver vazia. Reexecutar a
-- migration inteira nao duplica janela.
--
-- Algoritmo:
--   (a) loja DOMINANTE por (pessoa, mes) — mais contratos registrados
--       naquele mes vence; empate desempata pelo nome da loja, para o
--       resultado nao depender da ordem fisica das linhas;
--   (b) meses consecutivos na MESMA loja colapsam numa janela (ilhas).
--       A troca de loja e o unico corte: mes sem contrato NAO fecha
--       janela. Isso e essencial — nao existe periodo 09/2025 no banco
--       e ferias/afastamento nao sao desligamento;
--   (c) a ultima janela fica ABERTA se a pessoa esta ativa no cadastro
--       E a loja da janela e a loja atual dela; caso contrario fecha no
--       1o dia do mes seguinte ao ultimo mes com contrato;
--   (d) ativo hoje numa loja diferente da ultima em que registrou
--       contrato => a janela antiga fecha e abre uma nova na loja
--       atual, emendada (sem vago nem sobreposicao);
--   (e) ativo que NUNCA registrou contrato => piso 2020-01-01 aberto na
--       loja atual (3 pessoas em 2026-08-18), marcado BACKFILL_PISO;
--   (f) desligado que nunca registrou contrato => NENHUMA linha. Nunca
--       apareceu em competencia nenhuma; criar janela fechada so
--       poluiria o ledger (30 pessoas em 2026-08-18).
--
-- Janela meio-aberta [inicio, fim): fim = 1o dia do mes SEGUINTE ao
-- ultimo mes com contrato. Sob a ancora do ultimo dia (085), quem
-- registrou contrato ate 07/2026 tem fim 2026-08-01, cobre 2026-07-31
-- e nao cobre 2026-08-31 — julho conta, agosto nao.
-- ===========================================

INSERT INTO consultor_vigencia (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
WITH
cadastro_recente AS (
    -- 1 linha por PESSOA: a de updated_at mais recente (desligamento
    -- novo vence 'Ativo (a)' antigo). Mesma regra da 073/085.
    SELECT DISTINCT ON (n.nome_normalizado)
        n.nome_normalizado,
        c.nome,
        c.loja_id AS loja_atual_id,
        (btrim(coalesce(c.status, '')) = ''
         OR upper(btrim(c.status)) LIKE 'ATIVO%') AS eh_ativo
    FROM public.consultores c
    CROSS JOIN LATERAL (
        SELECT upper(regexp_replace(
            btrim(coalesce(c.nome, '')), '[[:space:]]+', ' ', 'g')) AS nome_normalizado
    ) n
    WHERE n.nome_normalizado <> ''
    ORDER BY n.nome_normalizado, c.updated_at DESC NULLS LAST, c.id DESC
),
contratos_mes AS (
    SELECT
        upper(regexp_replace(
            btrim(cs.nome), '[[:space:]]+', ' ', 'g')) AS nome_normalizado,
        ct.loja_id,
        date_trunc('month', ct.data_cadastro)::date AS mes,
        count(*) AS qtd
    FROM public.contratos ct
    JOIN public.consultores cs ON cs.id = ct.consultor_id
    WHERE ct.data_cadastro IS NOT NULL
      AND ct.loja_id IS NOT NULL
      AND btrim(coalesce(cs.nome, '')) <> ''
    GROUP BY 1, 2, 3
),
loja_dominante AS (
    SELECT DISTINCT ON (nome_normalizado, mes)
        nome_normalizado, mes, loja_id
    FROM contratos_mes
    ORDER BY nome_normalizado, mes, qtd DESC, loja_id
),
marcado AS (
    SELECT
        nome_normalizado, mes, loja_id,
        CASE WHEN loja_id IS DISTINCT FROM
                  lag(loja_id) OVER (PARTITION BY nome_normalizado ORDER BY mes)
             THEN 1 ELSE 0 END AS troca
    FROM loja_dominante
),
ilhas AS (
    SELECT
        nome_normalizado, mes, loja_id,
        sum(troca) OVER (PARTITION BY nome_normalizado ORDER BY mes
                         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ilha
    FROM marcado
),
janelas AS (
    SELECT
        nome_normalizado, loja_id, ilha,
        min(mes) AS mes_ini,
        max(mes) AS mes_fim,
        row_number() OVER (PARTITION BY nome_normalizado
                           ORDER BY min(mes) DESC) AS rn_desc
    FROM ilhas
    GROUP BY nome_normalizado, loja_id, ilha
),
-- (c) janelas derivadas: a ultima fica aberta so se casar com o cadastro
derivadas AS (
    SELECT
        cr.nome,
        j.loja_id,
        j.mes_ini AS vigencia_inicio,
        CASE
            WHEN j.rn_desc = 1
             AND cr.eh_ativo
             AND j.loja_id IS NOT DISTINCT FROM cr.loja_atual_id
            THEN NULL
            ELSE (j.mes_fim + INTERVAL '1 month')::date
        END AS vigencia_fim,
        'BACKFILL_PRODUCAO'::text AS origem
    FROM janelas j
    JOIN cadastro_recente cr USING (nome_normalizado)
),
-- (d) transferencia que a producao ainda nao mostrou
transferidos AS (
    SELECT
        cr.nome,
        cr.loja_atual_id AS loja_id,
        (j.mes_fim + INTERVAL '1 month')::date AS vigencia_inicio,
        NULL::date AS vigencia_fim,
        'BACKFILL_PRODUCAO'::text AS origem
    FROM janelas j
    JOIN cadastro_recente cr USING (nome_normalizado)
    WHERE j.rn_desc = 1
      AND cr.eh_ativo
      AND cr.loja_atual_id IS NOT NULL
      AND j.loja_id IS DISTINCT FROM cr.loja_atual_id
),
-- (e) ativo sem nenhum contrato: piso, para nao sumir do denominador
sem_contrato AS (
    SELECT
        cr.nome,
        cr.loja_atual_id AS loja_id,
        DATE '2020-01-01' AS vigencia_inicio,
        NULL::date AS vigencia_fim,
        'BACKFILL_PISO'::text AS origem
    FROM cadastro_recente cr
    WHERE cr.eh_ativo
      AND cr.loja_atual_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM janelas j
          WHERE j.nome_normalizado = cr.nome_normalizado
      )
)
SELECT * FROM derivadas
UNION ALL
SELECT * FROM transferidos
UNION ALL
SELECT * FROM sem_contrato
WHERE NOT EXISTS (SELECT 1 FROM consultor_vigencia);


-- ===========================================
-- 4. RLS + leitura: tabela-dimensao, legivel globalmente
--
-- Mesmo padrao de 043 (loja_regiao_vigencia) e 076
-- (supervisor_vigencia). Escrita fica com service_role/owner, que
-- ignoram RLS: o backfill acima e as funcoes da 087.
-- ===========================================

ALTER TABLE consultor_vigencia ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_cv_leitura ON consultor_vigencia;
CREATE POLICY pol_cv_leitura
    ON consultor_vigencia FOR SELECT USING (true);

GRANT SELECT ON consultor_vigencia TO anon, authenticated;


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- 1) Volume do backfill:
--
--    SELECT origem, count(*) AS linhas,
--           count(*) FILTER (WHERE vigencia_fim IS NULL) AS abertas
--    FROM consultor_vigencia GROUP BY origem ORDER BY origem;
--    -- Esperado em 2026-08-18:
--    --   BACKFILL_PISO       3 linhas,   3 abertas
--    --   BACKFILL_PRODUCAO 387 linhas, 162 abertas
--    -- (390 linhas / 296 pessoas; 69 com mais de uma janela.)
--
-- 2) A linha aberta espelha o cadastro ativo — 1 por pessoa ativa:
--
--    SELECT count(DISTINCT nome_normalizado)
--    FROM consultor_vigencia WHERE vigencia_fim IS NULL;
--    -- Esperado: 165 (= cadastro ativo deduplicado em 2026-08-18).
--
-- 3) Nenhum ativo do cadastro ficou sem janela aberta:
--
--    WITH cad AS (
--        SELECT DISTINCT ON (upper(regexp_replace(btrim(c.nome),'[[:space:]]+',' ','g')))
--               upper(regexp_replace(btrim(c.nome),'[[:space:]]+',' ','g')) AS nn,
--               c.status
--        FROM consultores c
--        WHERE btrim(coalesce(c.nome,'')) <> ''
--        ORDER BY 1, c.updated_at DESC NULLS LAST, c.id DESC
--    )
--    SELECT cad.nn FROM cad
--    WHERE (btrim(coalesce(cad.status,'')) = '' OR upper(btrim(cad.status)) LIKE 'ATIVO%')
--      AND NOT EXISTS (SELECT 1 FROM consultor_vigencia v
--                      WHERE v.nome_normalizado = cad.nn AND v.vigencia_fim IS NULL);
--    -- Esperado: 0 linhas.
--
-- 4) Nenhuma sobreposicao de janela na mesma pessoa (o ledger tem de
--    ser uma particao do tempo, nao um conjunto de intervalos soltos):
--
--    SELECT a.nome, a.vigencia_inicio, a.vigencia_fim,
--           b.vigencia_inicio, b.vigencia_fim
--    FROM consultor_vigencia a
--    JOIN consultor_vigencia b
--      ON b.nome_normalizado = a.nome_normalizado
--     AND b.id <> a.id
--     AND a.vigencia_inicio < coalesce(b.vigencia_fim, DATE '9999-12-31')
--     AND coalesce(a.vigencia_fim, DATE '9999-12-31') > b.vigencia_inicio;
--    -- Esperado: 0 linhas.
--
-- 5) INVARIANTE CENTRAL — nenhuma competencia conta menos gente do que
--    a que comprovadamente registrou contrato nela. Rodar para cada
--    competencia publicada; 07/2026 abaixo:
--
--    WITH ancora AS (SELECT DATE '2026-07-31' AS dia),
--    no_ledger AS (
--        SELECT DISTINCT v.nome_normalizado
--        FROM consultor_vigencia v CROSS JOIN ancora a
--        WHERE v.vigencia_inicio <= a.dia
--          AND (v.vigencia_fim IS NULL OR v.vigencia_fim > a.dia)
--    ),
--    produziram AS (
--        SELECT DISTINCT upper(regexp_replace(btrim(cs.nome),'[[:space:]]+',' ','g')) AS nn
--        FROM contratos ct
--        JOIN consultores cs ON cs.id = ct.consultor_id
--        WHERE ct.data_cadastro >= DATE '2026-07-01'
--          AND ct.data_cadastro <  DATE '2026-08-01'
--    )
--    SELECT p.nn FROM produziram p
--    WHERE NOT EXISTS (SELECT 1 FROM no_ledger l WHERE l.nome_normalizado = p.nn);
--    -- Esperado: 0 linhas, em TODAS as competencias.
--
-- 6) O headcount deixou de ser achatado (a prova de que a migration
--    resolve o problema). Resolucao por competencia, sem supervisores:
--
--    SELECT c.dia,
--           count(DISTINCT v.nome_normalizado) AS headcount
--    FROM (VALUES (DATE '2025-05-31'), (DATE '2025-12-31'),
--                 (DATE '2026-03-31'), (DATE '2026-07-31')) AS c(dia)
--    JOIN consultor_vigencia v
--      ON v.vigencia_inicio <= c.dia
--     AND (v.vigencia_fim IS NULL OR v.vigencia_fim > c.dia)
--    WHERE NOT EXISTS (
--        SELECT 1 FROM supervisor_vigencia s
--        WHERE s.nome_normalizado = v.nome_normalizado
--          AND s.vigencia_inicio <= c.dia
--          AND (s.vigencia_fim IS NULL OR s.vigencia_fim > c.dia)
--    )
--    GROUP BY c.dia ORDER BY c.dia;
--    -- Esperado (sem filtro de loja ativa e sem excluir VAI E VEM,
--    -- que a 089 aplica): valores DIFERENTES entre si, proximos de
--    -- 102 / 128 / 127 / 118 — nao 119 quatro vezes.
--
-- Reversao (estagio 1 nao tem consumidor — seguro):
--    DROP TABLE consultor_vigencia;
-- =====================================================
