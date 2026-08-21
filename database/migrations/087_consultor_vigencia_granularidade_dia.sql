-- =====================================================
-- Migracao 087: consultor_vigencia em granularidade de DIA
--               + correcao das tres sujeiras do backfill da 086
--
-- Motivo:
-- A 086 criou o ledger com janelas ancoradas em MES (`date_trunc`).
-- Isso bastava para a pergunta dela ("a pessoa estava ativa na
-- competencia C?"), mas nao basta para as regras aprovadas em
-- 2026-08-20, que passam a pesar presenca por DIA:
--
--   R1  admissao = data do PRIMEIRO CONTRATO DIGITADO (a coluna DESDE
--       que a 086 previa para a 088 fica CANCELADA; supervisor mantem
--       a logica propria das 076/082);
--   R2  peso da pessoa na competencia = du_presentes / du_total, com
--       piso de 50% em mes PARCIAL; ausencia declarada de mes inteiro
--       pesa 0; ausencia apenas INFERIDA (silencio) pesa 1,0;
--   R3  peso por loja = peso_pessoa x (du na loja / du presentes), de
--       modo que a soma entre lojas devolva UMA pessoa.
--
-- Nenhuma dessas contas fecha com janela que so conhece o mes. Esta
-- migration reconstroi o backfill resolvendo as FRONTEIRAS por dia.
--
-- ESTAGIO 1 CONTINUA: nada le `consultor_vigencia` ainda (os leitores
-- entram na 089/090). Por isso o rebuild aqui e um DELETE+INSERT
-- barato, e nenhum numero publicado muda. Depois que os leitores
-- entrarem, a mesma correcao exigiria rematerializar os snapshots da
-- 080 — esta e a ultima janela em que sai de graca.
--
--
-- DESENHO: mes decide QUAL loja, dia decide QUANDO troca
-- ------------------------------------------------------
-- Resolver a loja contrato a contrato quebraria o ledger: quem digita
-- um contrato avulso para outra loja abriria uma janela de um dia. A
-- 086 protegia disso com a loja DOMINANTE do mes, e essa protecao fica.
-- O que muda e a fronteira: quando ha troca real, a data sai do dia.
--
-- O discriminador entre TRANSFERENCIA e DIGITACAO AVULSA nao e um
-- limiar arbitrario, e a sobreposicao das janelas de dias. Medido em
-- 2026-08-20 sobre os 38 pares (pessoa, competencia) com mais de uma
-- loja no mesmo mes:
--
--   25 (66%) tem janelas DISJUNTAS — todos os contratos da loja A, e
--            so depois os da loja B. Transferencia real, com data
--            inequivoca: a fronteira e o primeiro contrato em B.
--   13 (34%) tem janelas SOBREPOSTAS — e sao justamente as de minoria
--            infima (286/4, 96/1, 93/4 contratos). Digitacao avulsa; a
--            loja dominante leva o mes inteiro, como na 086.
--
-- Regra final: mes com mais de uma loja e SEM sobreposicao vira um
-- segmento por loja; qualquer outro mes vira um segmento unico na loja
-- dominante. Segmentos consecutivos na mesma loja colapsam em ilha,
-- como na 086 — e mes sem contrato SEGUE nao fechando janela (ferias e
-- afastamento nao sao desligamento; e o periodo 09/2025 nao existe na
-- base).
--
--
-- FRONTEIRAS: exatas quando VERIFICADAS, de mes quando INFERIDAS
-- --------------------------------------------------------------
-- A assimetria de R2 vale tambem aqui — producao prova presenca, a
-- falta dela nao prova ausencia:
--
--   * ENTRADA (1o contrato da pessoa) -> data EXATA. E presenca
--     comprovada naquele dia. O mes de entrada fica parcial, e o piso
--     de 50% da R2 limita o erro dos dias de treinamento que nao
--     deixam rastro.
--   * TRANSFERENCIA -> data EXATA do primeiro contrato na loja nova.
--     A janela antiga fecha no mesmo dia (meio-aberta, emenda sem vago
--     nem sobreposicao).
--   * SAIDA sem data do RH -> fim do MES do ultimo contrato, como na
--     086. Fechar no dia seguinte ao ultimo contrato encolheria o
--     denominador por inferencia: quem vendeu dia 10 e trabalhou ate
--     dia 30 sumiria de 20 dias uteis. Ate a 088 trazer desligamento
--     declarado, o mes de saida conta inteiro.
--
--
-- AS TRES CORRECOES
-- -----------------
-- (a) CONTRATOS ORFAOS DE 2020. A 086 afirma que `contratos` comeca em
--     05/2025. Nao comeca: ha 3 contratos em 2020 e 2 em 03/2025. Os de
--     2020 estao a 4,7 anos do contrato seguinte da base e sao
--     tipograficos quase com certeza (2020 por 2025):
--
--       2020-06-08  LUDYMILA PEREIRA MACHADO           Desligado (a)
--       2020-06-24  MATHEUS PHELIPE BANDEIRA DA SILVA  Ativo (a)
--       2020-07-08  TAIS DA SILVA BARRETO              Desligado (a)
--
--     Eles abriram janelas com inicio em 2020-06 e 2020-07 que seguem
--     ABERTAS no ledger — as pessoas contam em TODAS as competencias.
--     Piso do backfill em 2025-01-01: descarta so os tres, preserva os
--     2 contratos de 03/2025 (LETYCIA, mesmo dia) e os 179 de 04/2025,
--     que nao ha por que julgar falsos.
--
-- (b) OS `BACKFILL_PISO` COM 2020-01-01. Ativo que nunca digitou
--     recebia piso 2020-01-01 e passava a contar nas 14 competencias —
--     exatamente o bug de reescrita retroativa que a 086 veio corrigir,
--     reintroduzido pela porta dos fundos. `consultores.created_at` nao
--     serve como admissao no geral (239 das 425 linhas nasceram na
--     carga inicial de 2026-03-21), mas para quem entrou nas cargas
--     INCREMENTAIS posteriores ele e um limite superior confiavel.
--     Regra: created_at quando posterior a carga inicial; senao o
--     inicio da base (2025-05-01), que e o conservador — silencio nao
--     prova ausencia.
--
-- (c) ADMISSAO CENSURADA. 124 das 297 pessoas (42%) tem o primeiro
--     contrato em 03-05/2025, ou seja, no comeco da base. Para elas
--     "primeiro contrato" NAO e admissao: e onde o dado comeca. Sob R1
--     isso fica aceito de forma permanente, mas deixa de ser invisivel:
--     ganham `origem = 'BACKFILL_CENSURADO'` e inicio no 1o dia do mes
--     (precisao de dia seria falsa ali). Consequencia registrada: a
--     competencia 05/2025 subestima o headcount para sempre, porque
--     quem ja trabalhava e nao vendeu naquele mes nao deixou rastro.
--
--
-- EFEITO MEDIDO (simulado sobre os dados de 2026-08-20, sem
-- supervisores, para ser comparavel a tabela da 086):
--
--   comp      086    087   produtores  folga
--   05/2025   102    101          101      0
--   06/2025   106    109          102      7
--   07/2025   106    107           99      8
--   08/2025   111    112          101     11
--   09/2025     —     96            0     96
--   10/2025   120    121          116      5
--   11/2025   113    115          110      5
--   12/2025   128    129          127      2
--   01/2026   124    125          123      2
--   02/2026   120    121          119      2
--   03/2026   127    129          125      4
--   04/2026   131    133          130      3
--   05/2026   127    130          125      5
--   06/2026   127    129          124      5
--   07/2026   118    118          116      2
--
-- O POPULACIONAL muda pouco (0 a 3 pessoas) — e o esperado: a 087 nao
-- reescreve quem estava ativo, ela precisa as datas em que entrou,
-- trocou de loja e saiu. O ganho e a base para R2/R3, nao um numero
-- diferente. A invariante central da 086 continua de pe nas 15
-- competencias: nenhum produtor fica fora do ledger.
--
-- Executar no Supabase SQL Editor, depois da 086.
-- =====================================================


-- ===========================================
-- 1. Novo valor de origem
--
-- BACKFILL_CENSURADO distingue "comecou aqui" de "o dado comeca aqui".
-- A 088 pode sobrescrever essas linhas com data real sem tocar nas
-- demais; nenhuma outra origem carrega essa licenca.
-- ===========================================

ALTER TABLE consultor_vigencia
    DROP CONSTRAINT IF EXISTS chk_cv_origem;

ALTER TABLE consultor_vigencia
    ADD CONSTRAINT chk_cv_origem CHECK (
        origem IN ('BACKFILL_PRODUCAO', 'BACKFILL_CENSURADO',
                   'BACKFILL_PISO', 'ETL', 'MANUAL')
    );

COMMENT ON COLUMN consultor_vigencia.origem IS
    'Procedencia da linha: BACKFILL_PRODUCAO (janela com data exata derivada '
    'de `contratos`), BACKFILL_CENSURADO (primeiro contrato no inicio da base '
    '— a admissao real e anterior e desconhecida; inicio no 1o dia do mes), '
    'BACKFILL_PISO (ativo sem nenhum contrato), ETL (import da '
    'HC_Colaboradores) ou MANUAL (correcao). Serve para distinguir o que e '
    'FATO informado do que e INFERENCIA.';


-- ===========================================
-- 2. Rebuild do backfill
--
-- Apaga so as linhas de backfill: correcao MANUAL ou carga do ETL, se
-- existirem quando isto rodar, sobrevivem. Em 2026-08-20 nao ha
-- nenhuma (as 390 linhas sao 387 PRODUCAO + 3 PISO).
-- ===========================================

BEGIN;

DELETE FROM consultor_vigencia
WHERE origem LIKE 'BACKFILL%';

INSERT INTO consultor_vigencia (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
WITH
cadastro_recente AS (
    -- 1 linha por PESSOA: a de updated_at mais recente (desligamento
    -- novo vence 'Ativo (a)' antigo). Mesma regra da 073/085/086.
    SELECT DISTINCT ON (n.nome_normalizado)
        n.nome_normalizado,
        c.nome,
        c.loja_id           AS loja_atual_id,
        c.created_at::date  AS cadastrado_em,
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
contratos_validos AS (
    -- Piso de 2025-01-01: correcao (a). `contratos`, nao
    -- `v_contratos_dashboard` — a view e so de PAGOS, e a pergunta aqui
    -- e PRESENCA, nao producao. Data e `data_cadastro` (registro do
    -- contrato), nunca `data_status_pagamento`: pagamento arrasta
    -- depois da saida.
    SELECT
        upper(regexp_replace(
            btrim(cs.nome), '[[:space:]]+', ' ', 'g')) AS nome_normalizado,
        ct.loja_id,
        ct.data_cadastro::date AS dia
    FROM public.contratos ct
    JOIN public.consultores cs ON cs.id = ct.consultor_id
    WHERE ct.data_cadastro >= DATE '2025-01-01'
      AND ct.loja_id IS NOT NULL
      AND btrim(coalesce(cs.nome, '')) <> ''
),
loja_mes AS (
    SELECT
        nome_normalizado,
        date_trunc('month', dia)::date AS mes,
        loja_id,
        min(dia)  AS d_ini,
        max(dia)  AS d_fim,
        count(*)  AS qtd
    FROM contratos_validos
    GROUP BY 1, 2, 3
),
mes_total AS (
    SELECT
        nome_normalizado, mes,
        min(d_ini)  AS m_ini,
        max(d_fim)  AS m_fim,
        count(*)    AS n_lojas
    FROM loja_mes
    GROUP BY 1, 2
),
ordenado AS (
    -- d_fim_ant = maior d_fim entre TODAS as lojas anteriores (nao so a
    -- imediatamente anterior): com 3+ lojas no mes, a terceira pode
    -- sobrepor a primeira sem sobrepor a segunda.
    SELECT
        lm.*,
        max(lm.d_fim) OVER (
            PARTITION BY lm.nome_normalizado, lm.mes
            ORDER BY lm.d_ini, lm.d_fim
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS d_fim_ant
    FROM loja_mes lm
),
mes_tipo AS (
    SELECT
        nome_normalizado, mes,
        bool_or(d_fim_ant IS NOT NULL AND d_ini <= d_fim_ant) AS sobrepoe
    FROM ordenado
    GROUP BY 1, 2
),
segmentos AS (
    -- (i) troca LIMPA: um segmento por loja, na ordem dos dias
    SELECT
        o.nome_normalizado, o.mes, o.loja_id, o.d_ini, o.d_fim,
        row_number() OVER (PARTITION BY o.nome_normalizado, o.mes
                           ORDER BY o.d_ini, o.d_fim) AS ord
    FROM ordenado o
    JOIN mes_tipo  t ON t.nome_normalizado = o.nome_normalizado AND t.mes = o.mes
    JOIN mes_total m ON m.nome_normalizado = o.nome_normalizado AND m.mes = o.mes
    WHERE m.n_lojas > 1
      AND NOT t.sobrepoe

    UNION ALL

    -- (ii) loja unica, ou digitacao avulsa: a DOMINANTE leva o mes
    -- inteiro, e o segmento cobre do 1o ao ultimo contrato do mes
    -- (qualquer loja) — a pessoa esteve presente esses dias.
    SELECT
        d.nome_normalizado, d.mes, d.loja_id, m.m_ini, m.m_fim, 1 AS ord
    FROM (
        SELECT DISTINCT ON (lm.nome_normalizado, lm.mes)
            lm.nome_normalizado, lm.mes, lm.loja_id
        FROM loja_mes lm
        JOIN mes_tipo  t  ON t.nome_normalizado  = lm.nome_normalizado AND t.mes  = lm.mes
        JOIN mes_total mt ON mt.nome_normalizado = lm.nome_normalizado AND mt.mes = lm.mes
        WHERE mt.n_lojas = 1 OR t.sobrepoe
        -- empate desempata pelo loja_id, para o resultado nao depender
        -- da ordem fisica das linhas
        ORDER BY lm.nome_normalizado, lm.mes, lm.qtd DESC, lm.loja_id
    ) d
    JOIN mes_total m ON m.nome_normalizado = d.nome_normalizado AND m.mes = d.mes
),
marcado AS (
    SELECT
        s.*,
        CASE WHEN s.loja_id IS DISTINCT FROM
                  lag(s.loja_id) OVER (PARTITION BY s.nome_normalizado
                                       ORDER BY s.mes, s.ord)
             THEN 1 ELSE 0 END AS troca
    FROM segmentos s
),
ilhas AS (
    SELECT
        m.*,
        sum(m.troca) OVER (PARTITION BY m.nome_normalizado
                           ORDER BY m.mes, m.ord
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ilha
    FROM marcado m
),
janelas AS (
    SELECT
        nome_normalizado, loja_id, ilha,
        min(d_ini) AS dia_ini,
        max(d_fim) AS dia_fim
    FROM ilhas
    GROUP BY nome_normalizado, loja_id, ilha
),
janelas_ord AS (
    SELECT
        j.*,
        row_number() OVER (PARTITION BY j.nome_normalizado ORDER BY j.dia_ini)      AS rn,
        row_number() OVER (PARTITION BY j.nome_normalizado ORDER BY j.dia_ini DESC) AS rn_desc,
        min(j.dia_ini) OVER (PARTITION BY j.nome_normalizado)                       AS primeiro_dia
    FROM janelas j
),
com_inicio AS (
    -- correcao (c): a primeira janela de quem aparece no comeco da base
    -- nao ganha precisao de dia, ganha rotulo de censurada.
    SELECT
        jo.*,
        (jo.rn = 1 AND jo.primeiro_dia < DATE '2025-06-01') AS censurado,
        CASE WHEN jo.rn = 1 AND jo.primeiro_dia < DATE '2025-06-01'
             THEN date_trunc('month', jo.dia_ini)::date
             ELSE jo.dia_ini
        END AS vigencia_inicio
    FROM janelas_ord jo
),
com_fim AS (
    SELECT
        ci.*,
        lead(ci.vigencia_inicio) OVER (PARTITION BY ci.nome_normalizado
                                       ORDER BY ci.vigencia_inicio) AS prox_inicio
    FROM com_inicio ci
),
derivadas AS (
    SELECT
        cr.nome,
        cf.loja_id,
        cf.vigencia_inicio,
        CASE
            -- transferencia: emenda exata, sem vago nem sobreposicao
            WHEN cf.prox_inicio IS NOT NULL THEN cf.prox_inicio
            -- ultima janela de quem segue ativo na mesma loja: ABERTA
            WHEN cf.rn_desc = 1
             AND cr.eh_ativo
             AND cf.loja_id IS NOT DISTINCT FROM cr.loja_atual_id THEN NULL
            -- saida inferida: o mes de saida conta inteiro
            ELSE (date_trunc('month', cf.dia_fim) + INTERVAL '1 month')::date
        END AS vigencia_fim,
        CASE WHEN cf.censurado THEN 'BACKFILL_CENSURADO'
             ELSE 'BACKFILL_PRODUCAO' END AS origem
    FROM com_fim cf
    JOIN cadastro_recente cr ON cr.nome_normalizado = cf.nome_normalizado
),
transferidos AS (
    -- ativo hoje numa loja diferente da ultima em que digitou: a
    -- producao ainda nao mostrou a transferencia. Sem data verificada,
    -- a janela nova comeca no mes seguinte (nao no dia seguinte).
    SELECT
        cr.nome,
        cr.loja_atual_id AS loja_id,
        (date_trunc('month', cf.dia_fim) + INTERVAL '1 month')::date AS vigencia_inicio,
        NULL::date       AS vigencia_fim,
        'BACKFILL_PRODUCAO'::text AS origem
    FROM com_fim cf
    JOIN cadastro_recente cr ON cr.nome_normalizado = cf.nome_normalizado
    WHERE cf.rn_desc = 1
      AND cr.eh_ativo
      AND cr.loja_atual_id IS NOT NULL
      AND cf.loja_id IS DISTINCT FROM cr.loja_atual_id
),
sem_contrato AS (
    -- correcao (b): nada de 2020-01-01.
    SELECT
        cr.nome,
        cr.loja_atual_id AS loja_id,
        CASE WHEN cr.cadastrado_em > DATE '2026-03-21'
             THEN cr.cadastrado_em          -- carga incremental: data confiavel
             ELSE DATE '2025-05-01'         -- carga inicial: inicio da base
        END AS vigencia_inicio,
        NULL::date       AS vigencia_fim,
        'BACKFILL_PISO'::text AS origem
    FROM cadastro_recente cr
    WHERE cr.eh_ativo
      AND cr.loja_atual_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM janelas j
          WHERE j.nome_normalizado = cr.nome_normalizado
      )
    -- desligado que nunca digitou: NENHUMA linha (nunca apareceu em
    -- competencia alguma; janela fechada so poluiria o ledger).
)
SELECT * FROM derivadas
UNION ALL
SELECT * FROM transferidos
UNION ALL
SELECT * FROM sem_contrato;

COMMIT;


-- ===========================================
-- Verificacao (apos executar)
--
-- Valores esperados apurados em 2026-08-20 sobre a base real. Se o
-- cadastro tiver mudado entre a apuracao e a execucao, os totais
-- deslocam — as INVARIANTES (2, 4, 5, 6) e que nao podem falhar.
-- ===========================================
-- 1) Volume do rebuild:
--
--    SELECT origem, count(*) AS linhas,
--           count(*) FILTER (WHERE vigencia_fim IS NULL) AS abertas
--    FROM consultor_vigencia GROUP BY origem ORDER BY origem;
--    -- Esperado:
--    --   BACKFILL_CENSURADO  124 linhas,  45 abertas
--    --   BACKFILL_PISO         1 linha,    1 aberta
--    --   BACKFILL_PRODUCAO   271 linhas, 122 abertas
--    -- (396 linhas / 297 pessoas; 71 com mais de uma janela.)
--    -- A 086 tinha 390 / 296, com 3 PISO — dois daqueles ja digitaram
--    -- contrato desde entao e viraram janela derivada.
--
-- 2) INVARIANTE — a linha aberta espelha o cadastro ativo, 1 por pessoa:
--
--    SELECT
--      (SELECT count(DISTINCT nome_normalizado) FROM consultor_vigencia
--       WHERE vigencia_fim IS NULL) AS abertas,
--      (SELECT count(*) FROM (
--          SELECT DISTINCT ON (upper(regexp_replace(btrim(c.nome),'[[:space:]]+',' ','g')))
--                 c.status
--          FROM consultores c WHERE btrim(coalesce(c.nome,'')) <> ''
--          ORDER BY 1, c.updated_at DESC NULLS LAST, c.id DESC
--       ) x WHERE btrim(coalesce(x.status,'')) = ''
--            OR upper(btrim(x.status)) LIKE 'ATIVO%') AS cadastro_ativo;
--    -- Esperado: iguais (168 em 2026-08-20).
--
-- 3) A correcao (a) funcionou — nenhuma janela anterior a 2025:
--
--    SELECT count(*) FROM consultor_vigencia
--    WHERE vigencia_inicio < DATE '2025-01-01';
--    -- Esperado: 0. (A 086 tinha 5: tres PISO em 2020-01-01 e duas
--    --  janelas derivadas dos contratos orfaos de 2020.)
--
-- 4) INVARIANTE — nenhuma sobreposicao de janela na mesma pessoa (o
--    ledger tem de ser uma particao do tempo):
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
-- 5) INVARIANTE CENTRAL (herdada da 086) — nenhuma competencia conta
--    menos gente do que a que comprovadamente digitou nela. Agora pela
--    leitura por INTERVALO, que e a que a 089 usa (a janela cobre
--    qualquer dia da competencia), nao mais pela ancora do ultimo dia:
--
--    WITH c(ini, fim) AS (VALUES (DATE '2026-07-01', DATE '2026-08-01')),
--    no_ledger AS (
--        SELECT DISTINCT v.nome_normalizado
--        FROM consultor_vigencia v CROSS JOIN c
--        WHERE v.vigencia_inicio < c.fim
--          AND (v.vigencia_fim IS NULL OR v.vigencia_fim > c.ini)
--    ),
--    produziram AS (
--        SELECT DISTINCT upper(regexp_replace(btrim(cs.nome),'[[:space:]]+',' ','g')) AS nn
--        FROM contratos ct
--        JOIN consultores cs ON cs.id = ct.consultor_id
--        CROSS JOIN c
--        WHERE ct.data_cadastro >= c.ini AND ct.data_cadastro < c.fim
--    )
--    SELECT p.nn FROM produziram p
--    WHERE NOT EXISTS (SELECT 1 FROM no_ledger l WHERE l.nome_normalizado = p.nn);
--    -- Esperado: 0 linhas, em TODAS as competencias (verificado nas 15
--    -- de 05/2025 a 07/2026).
--
-- 6) INVARIANTE — a fronteira de transferencia emenda: janela que fecha
--    por troca de loja fecha exatamente onde a seguinte abre.
--
--    WITH seq AS (
--        SELECT nome_normalizado, vigencia_fim,
--               lead(vigencia_inicio) OVER (PARTITION BY nome_normalizado
--                                           ORDER BY vigencia_inicio) AS prox
--        FROM consultor_vigencia
--    )
--    SELECT count(*) FROM seq
--    WHERE prox IS NOT NULL AND vigencia_fim IS DISTINCT FROM prox;
--    -- Esperado: 0.
--
-- 7) A granularidade de dia existe de fato (a prova de que o rebuild
--    valeu): janelas que NAO comecam no dia 1o.
--
--    SELECT count(*) FILTER (WHERE extract(day FROM vigencia_inicio) <> 1) AS dia_exato,
--           count(*) AS total
--    FROM consultor_vigencia;
--    -- Esperado: dia_exato > 0 (na 086 era exatamente 0 — todas as
--    -- janelas comecavam no dia 1o).
--
-- 8) O headcount segue variando por competencia (nao voltou a achatar):
--
--    SELECT c.ini,
--           count(DISTINCT v.nome_normalizado) AS headcount
--    FROM (VALUES (DATE '2025-05-01', DATE '2025-06-01'),
--                 (DATE '2025-12-01', DATE '2026-01-01'),
--                 (DATE '2026-03-01', DATE '2026-04-01'),
--                 (DATE '2026-07-01', DATE '2026-08-01')) AS c(ini, fim)
--    JOIN consultor_vigencia v
--      ON v.vigencia_inicio < c.fim
--     AND (v.vigencia_fim IS NULL OR v.vigencia_fim > c.ini)
--    GROUP BY c.ini ORDER BY c.ini;
--    -- Esperado (com supervisores, sem filtro de loja): valores
--    -- diferentes entre si, proximos de 123 / 174 / 172 / 160.
--
-- Reversao (estagio 1 nao tem consumidor — seguro):
--    Reexecutar a secao 2 da migration 086 depois de
--    DELETE FROM consultor_vigencia WHERE origem LIKE 'BACKFILL%';
--    e restaurar o CHECK sem 'BACKFILL_CENSURADO'.
-- =====================================================
