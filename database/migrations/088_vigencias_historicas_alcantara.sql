-- =====================================================
-- Migracao 088: correcao historica do eixo ALCANTARA
--               (ERICA, MARIANA) nos dois ledgers
--
-- Caso relatado pelo usuario em 2026-08-20, confirmado contra o banco.
-- A historia real da ERICA CRISTINA MARINS DA SILVA:
--
--   1. supervisora de HELP ALCANTARA (inicio anterior ao comeco da base);
--   2. entra em licenca (ultimo contrato dela: 27/11/2025);
--   3. MARIANA DE OLIVEIRA RODRIGUES assume HELP ALCANTARA em 13/01/2026;
--   4. ERICA retorna como CONSULTORA de HELP ALCANTARA CARREFOUR em
--      19/06/2026;
--   5. EMANUELE LIGIA DE AZEVEDO e desligada em 15/07/2026 e ERICA
--      assume a supervisao de HELP ALCANTARA CARREFOUR.
--
-- Os passos 4 e 5 ja estao corretos no banco (a 081 registrou o 5). Os
-- passos 1 e 3 NAO EXISTEM em ledger nenhum, e e isso que esta migration
-- conserta.
--
--
-- POR QUE A 081 NAO BASTOU
-- ------------------------
-- A 081 corrigiu o piso 2020-01-01 da ERICA movendo o inicio para
-- 15/07/2026, sob a premissa registrada no cabecalho dela: "so assumiu
-- em 15/07/2026". A premissa estava INCOMPLETA — ela ja tinha sido
-- supervisora de HELP ALCANTARA antes da licenca. A correcao acertou a
-- janela de CARREFOUR e, junto, apagou a de ALCANTARA.
--
-- O piso 2020-01-01 volta aqui, mas agora com a loja certa e com FIM:
-- ele significa "nao se sabe desde quando, e anterior ao inicio da
-- base", que e exatamente o caso — a admissao dela e anterior a 05/2025
-- e o afastamento da EMANUELE que a levou a ALCANTARA tambem.
--
--
-- O DEFEITO DA MARIANA (este muda numero publicado)
-- --------------------------------------------------
-- MARIANA esta com piso 2020-01-01 em HELP ALCANTARA — o backfill da
-- 076, que significa "nao sei desde quando". Agora se sabe: 13/01/2026.
-- Antes disso ela era CONSULTORA da loja, e a producao dela mostra isso
-- sem ambiguidade:
--
--   mai/25  jun  ago  out  nov  dez | jan/26  fev  mar  abr  mai  jun
--       64   69   80  191   93  114 |     26    7    5    2    1    6
--
-- 64 a 191 contratos/mes e producao de consultora de ponta; supervisor
-- nesta base produz de 1 a 22. O desabamento entre dez/2025 e jan/2026
-- e a assinatura da promocao, e bate com a data informada.
--
-- EFEITO MEDIDO (ancora do ultimo dia, migration 085 — o leitor atual):
--
--   competencia   MARIANA entra   ERICA sai   produtores ALCANTARA
--   05/2025               +64           0     2 -> 3
--   06/2025               +69           0     2 -> 3
--   08/2025               +80           0     2 -> 3
--   10/2025              +191          -3     3 -> 3
--   11/2025               +93          -2     3 -> 3
--   12/2025             +114            0     3 -> 4
--   ------------------------------------------------
--   TOTAL                 611          -5
--
-- 611 contratos de producao REAL de consultora voltam ao eixo consultor
-- em 6 competencias, e 5 contratos de supervisora saem. Em 01/2026 a
-- MARIANA e supervisora o mes inteiro sob a ancora do ultimo dia, entao
-- os 26 contratos dela naquele mes seguem excluidos; quando a 090 trocar
-- a ancora pela leitura proporcional, os 19 contratos anteriores a
-- 13/01 passam a contar (nao ha o que fazer aqui por isso agora).
--
-- ATENCAO: 6 competencias FECHADAS mudam. Os snapshots da 080 precisam
-- ser REMATERIALIZADOS para 05, 06, 08, 10, 11 e 12/2025, senao o
-- Caderno publicado diverge do dashboard. Ver secao 4.
--
--
-- O QUE ESTE CASO PROVOU SOBRE O DESENHO
-- --------------------------------------
-- A janela de consultora da ERICA em CARREFOUR (19/06 a 15/07/2026) e
-- invisivel para qualquer backfill derivado de producao: ela trabalhou
-- o periodo inteiro e digitou ZERO contrato. O primeiro contrato dela na
-- loja e de 20/07 — CINCO DIAS DEPOIS de ja ter virado supervisora.
--
-- Consequencia registrada: a 087, mais precisa que a 086 em todo o
-- resto, e MAIS ERRADA aqui (dataria o vinculo em 20/07 em vez de
-- 01/07). Nao invalida a 087 — mostra o limite do sinal: producao prova
-- presenca, mas nao prova EM QUE LOJA nem EM QUE PAPEL. Por isso o
-- ledger precisa aceitar entrada manual, e por isso a exclusao de
-- supervisor tem de ser feita pelo LEITOR (subtraindo a janela de
-- supervisao), nunca no backfill.
--
-- Executar no Supabase SQL Editor, DEPOIS da 087 (o rebuild da 087
-- apaga linhas 'BACKFILL%' e recriaria os vinculos derivados; as
-- correcoes abaixo gravam origem 'MANUAL' e nao devem ser rodadas
-- antes dele).
-- =====================================================

BEGIN;

-- ===========================================
-- 0. Guarda de ordem: a 087 TEM de ter rodado antes
--
-- Rodar esta migration primeiro nao corrompe dado, mas quebra a 087
-- depois: as correcoes abaixo gravam origem 'MANUAL', que o rebuild da
-- 087 nao apaga, e o INSERT dela recriaria uma segunda janela ABERTA da
-- ERICA em CARREFOUR — violando uq_cv_consultor_loja_aberta. A 087
-- falharia inteira. Melhor barrar aqui, com mensagem, do que depois.
--
-- Deteccao: 'BACKFILL_CENSURADO' so existe se a 087 rodou.
-- ===========================================

DO $guarda$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.consultor_vigencia
        WHERE origem = 'BACKFILL_CENSURADO'
    ) THEN
        RAISE EXCEPTION
            'Migration 087 precisa rodar ANTES da 088 (nenhuma linha '
            'BACKFILL_CENSURADO em consultor_vigencia).';
    END IF;
END
$guarda$;


-- ===========================================
-- 1. supervisor_vigencia: a passagem da ERICA por HELP ALCANTARA
--
-- Piso 2020-01-01 = "inicio anterior ao comeco da base, desconhecido",
-- mesma convencao da 076. Fim em 13/01/2026, emendando exatamente com a
-- entrada da MARIANA (secao 2) — sem vago nem sobreposicao.
--
-- O piso e SEGURO aqui e PERIGOSO no ledger de consultor, e a diferenca
-- e a direcao do efeito: piso em supervisor_vigencia EXCLUI a pessoa das
-- visoes consultor-level nas competencias antigas (conservador — no
-- maximo tira quem talvez devesse contar); piso em consultor_vigencia
-- INCLUI a pessoa no headcount de todas elas, inflando denominador. Foi
-- por isso que a 087 aboliu o piso de la (correcao (b)) e ele continua
-- valendo aqui. Sem efeito pratico neste caso, alias: o vinculo de
-- consultora da ERICA so comeca em 10/2025.
--
-- A janela de CARREFOUR dela (15/07/2026, aberta) NAO e tocada.
-- ===========================================

INSERT INTO public.supervisor_vigencia (nome, loja_id, vigencia_inicio, vigencia_fim)
SELECT
    'ERICA CRISTINA MARINS DA SILVA',
    l.id,
    DATE '2020-01-01',
    DATE '2026-01-13'
FROM public.lojas l
WHERE upper(btrim(l.nome)) = 'HELP ALCANTARA'
  AND NOT EXISTS (
      SELECT 1 FROM public.supervisor_vigencia v
      WHERE v.nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA'
        AND v.loja_id = l.id
  );


-- ===========================================
-- 2. supervisor_vigencia: MARIANA assume em 13/01/2026
--
-- Troca o piso da 076 pela data real. So a linha de HELP ALCANTARA, e
-- so se ainda estiver com o piso — reexecutar nao desfaz nada.
-- ===========================================

UPDATE public.supervisor_vigencia v
SET vigencia_inicio = DATE '2026-01-13'
FROM public.lojas l
WHERE l.id = v.loja_id
  AND upper(btrim(l.nome)) = 'HELP ALCANTARA'
  AND v.nome_normalizado = 'MARIANA DE OLIVEIRA RODRIGUES'
  AND v.vigencia_inicio = DATE '2020-01-01';


-- ===========================================
-- 3. consultor_vigencia: o vinculo da ERICA muda de loja em 19/06/2026
--
-- A 087 deriva a fronteira do primeiro contrato em CARREFOUR
-- (2026-07-20). A data real e 19/06/2026, informada pelo usuario. As
-- duas janelas emendam nessa data.
--
-- origem passa a 'MANUAL': marca que a janela e FATO informado, nao
-- inferencia — e protege a correcao de um eventual rebuild, que apaga
-- apenas linhas 'BACKFILL%'.
--
-- NOTA: o vinculo com ALCANTARA segue CONTINUO durante a licenca (ela
-- era funcionaria da loja, afastada). O peso 0 do periodo nao sai daqui
-- — sai do ledger de afastamento da 089. Enquanto ele nao existir, esta
-- janela conta a ERICA como cabeca inteira em ALCANTARA entre 01/2026 e
-- 06/2026. Isso NAO afeta numero publicado (nada le consultor_vigencia
-- antes da 090), mas e BLOQUEADOR para a 090.
-- ===========================================

UPDATE public.consultor_vigencia v
SET vigencia_fim = DATE '2026-06-19',
    origem       = 'MANUAL'
FROM public.lojas l
WHERE l.id = v.loja_id
  AND upper(btrim(l.nome)) = 'HELP ALCANTARA'
  AND v.nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA';

UPDATE public.consultor_vigencia v
SET vigencia_inicio = DATE '2026-06-19',
    origem          = 'MANUAL'
FROM public.lojas l
WHERE l.id = v.loja_id
  AND upper(btrim(l.nome)) = 'HELP ALCANTARA CARREFOUR'
  AND v.nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA';

COMMIT;


-- ===========================================
-- 4. Rematerializacao obrigatoria dos snapshots
--
-- As 6 competencias abaixo mudam de headcount e de producao no eixo
-- consultor. Rodar a funcao de materializacao da 080 para cada uma:
--
--    SELECT fn_materializar_caderno(5,  2025);
--    SELECT fn_materializar_caderno(6,  2025);
--    SELECT fn_materializar_caderno(8,  2025);
--    SELECT fn_materializar_caderno(10, 2025);
--    SELECT fn_materializar_caderno(11, 2025);
--    SELECT fn_materializar_caderno(12, 2025);
--
-- Assinatura: fn_materializar_caderno(p_mes, p_ano) — mes primeiro.
-- Exige service_role (a 080 revogou de anon/authenticated).
-- ===========================================


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- 1) A linha do tempo de HELP ALCANTARA nao tem vago nem sobreposicao:
--
--    SELECT v.nome, v.vigencia_inicio, v.vigencia_fim
--    FROM supervisor_vigencia v JOIN lojas l ON l.id = v.loja_id
--    WHERE upper(btrim(l.nome)) = 'HELP ALCANTARA'
--    ORDER BY v.vigencia_inicio;
--    -- Esperado, exatamente 2 linhas:
--    --   ERICA CRISTINA MARINS DA SILVA   2020-01-01   2026-01-13
--    --   MARIANA DE OLIVEIRA RODRIGUES    2026-01-13   NULL
--
-- 2) A ERICA tem as DUAS passagens, sem sobreposicao entre elas:
--
--    SELECT l.nome AS loja, v.vigencia_inicio, v.vigencia_fim
--    FROM supervisor_vigencia v LEFT JOIN lojas l ON l.id = v.loja_id
--    WHERE v.nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA'
--    ORDER BY v.vigencia_inicio;
--    -- Esperado:
--    --   HELP ALCANTARA             2020-01-01   2026-01-13
--    --   HELP ALCANTARA CARREFOUR   2026-07-15   NULL
--    -- O intervalo 13/01 a 15/07/2026 e o periodo em que ela NAO era
--    -- supervisora (licenca + volta como consultora). Correto.
--
-- 3) O vinculo de loja da ERICA emenda em 19/06:
--
--    SELECT l.nome AS loja, v.vigencia_inicio, v.vigencia_fim, v.origem
--    FROM consultor_vigencia v LEFT JOIN lojas l ON l.id = v.loja_id
--    WHERE v.nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA'
--    ORDER BY v.vigencia_inicio;
--    -- Esperado:
--    --   HELP ALCANTARA             2025-10-01   2026-06-19   MANUAL
--    --   HELP ALCANTARA CARREFOUR   2026-06-19   NULL         MANUAL
--
-- 4) INVARIANTE da 077 (foto == linhas abertas) continua de pe:
--
--    SELECT
--      (SELECT count(*) FROM supervisor_vigencia WHERE vigencia_fim IS NULL)
--        AS abertas,
--      (SELECT count(*) FROM supervisores) AS foto;
--    -- Esperado: iguais. Esta migration nao abre nem fecha nenhuma
--    -- janela vigente — a da ERICA que ela cria ja nasce FECHADA.
--
-- 5) A producao da MARIANA voltou ao eixo consultor:
--
--    SELECT count(*) FROM contratos ct
--    JOIN consultores cs ON cs.id = ct.consultor_id
--    WHERE upper(regexp_replace(btrim(cs.nome),'[[:space:]]+',' ','g'))
--          = 'MARIANA DE OLIVEIRA RODRIGUES'
--      AND ct.data_cadastro < DATE '2026-01-01';
--    -- Esperado: 611 — e nenhum deles cai mais na exclusao de
--    -- supervisor, porque a vigencia dela agora comeca em 13/01/2026.
-- =====================================================
