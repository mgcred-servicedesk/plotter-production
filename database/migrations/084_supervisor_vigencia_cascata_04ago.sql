-- =====================================================
-- Migracao 084: cascata de 04/08/2026
--               (LETICIA -> MARIANA -> DJANE -> RAIANE)
--
-- Depende da 076 (tabela), 082 (acao CORRIGIR_INICIO) e 083 (RAIANE).
--
-- Relatado pelo usuario em 2026-08-18, tudo com data efetiva
-- 04/08/2026:
--   LETICIA ALVARENGA GOMES FREITAS desligada de HELP BELFORD ROXO SAO
--   JOSE -> MARIANA CARLA LAMIN DA SILVA transferida de HELP RAMOS para
--   cobri-la -> DJANE MARIA PEREIRA DOS SANTOS transferida de HELP
--   COPACABANA NOVA para cobrir RAMOS -> RAIANE ALMEIDA SOUZA assume
--   COPACABANA NOVA (18/08, ja registrado na 083).
--
-- POR QUE NAO DA PARA USAR 'REMANEJAMENTO': a acao fecha a vigencia
-- aberta e abre outra na loja nova. Aqui isso produziria historia
-- ERRADA, porque o backfill da 076 nao colocou a MARIANA e a DJANE na
-- loja de origem — colocou cada uma na loja ATUAL desde 2020-01-01. Um
-- REMANEJAMENTO da MARIANA fecharia uma janela dizendo que ela
-- supervisionou BELFORD ROXO SAO JOSE de 2020 a 2026, quando ela estava
-- em RAMOS. A correcao precisa INSERIR a janela de origem (loja certa) e
-- so entao mover o inicio da janela aberta.
--
-- Evidencia de que a origem esta certa: a MARIANA produziu em HELP RAMOS
-- de 01/2026 a 07/2026 (321 contratos / R$ 339.770,86 no total dela),
-- enquanto o ledger a dava em BELFORD ROXO SAO JOSE desde 2020.
--
-- LETICIA e mais um caso EMANUELE (081): saiu da planilha antes da 076,
-- entao nao tem linha nenhuma e a producao dela como supervisora (8
-- contratos / R$ 838,83) conta como producao de consultora.
--
-- Ancora do dia 1o — em 08/2026 (ancora 01/08, anterior a 04/08):
--   * LETICIA ainda e supervisora (sem efeito pratico: 'Desligado (a)'
--     no RH, fora do universo ativo, e sem producao em agosto);
--   * MARIANA e DJANE seguem supervisoras, atribuidas as lojas de
--     ORIGEM. Setembro e o primeiro mes nas lojas novas.
--
-- Efeito no numero publicado:
--   * Caderno: NENHUM em competencia alguma. MARIANA e DJANE continuam
--     supervisoras em todo mes passado (so muda a loja, e headcount
--     exclui supervisor independentemente da loja); LETICIA esta
--     desligada, fora do universo ativo. Nao e preciso republicar.
--   * Dashboard: os 8 contratos da LETICIA saem das visoes
--     consultor-level nas competencias ate 07/2026.
--
-- Continuidade resultante:
--   BELFORD ROXO SAO JOSE : LETICIA ate 04/08 -> MARIANA a partir de 04/08
--   RAMOS                 : MARIANA ate 04/08 -> DJANE   a partir de 04/08
--   COPACABANA NOVA       : DJANE   ate 04/08 -> (vago) -> RAIANE em 18/08
-- O vao de 14 dias em COPACABANA NOVA e real, nao erro: a loja ficou sem
-- supervisor ate a contratacao da RAIANE.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

-- ===========================================
-- 1. Janelas de ORIGEM (historia que faltava)
--
-- Idempotente: cada INSERT so dispara se a pessoa ainda nao tiver linha
-- naquela loja especifica.
-- ===========================================

-- LETICIA: supervisora de BELFORD ROXO SAO JOSE ate o desligamento.
-- Nao esta em `supervisores` (saiu na planilha), entao nao ha vigencia
-- aberta para fechar — entra ja fechada, como a EMANUELE na 081.
INSERT INTO public.supervisor_vigencia
    (nome, loja_id, vigencia_inicio, vigencia_fim)
SELECT 'LETICIA ALVARENGA GOMES FREITAS', l.id,
       DATE '2020-01-01', DATE '2026-08-04'
FROM public.lojas l
WHERE l.nome = 'HELP BELFORD ROXO SAO JOSE'
  AND NOT EXISTS (
      SELECT 1 FROM public.supervisor_vigencia v
      WHERE v.nome_normalizado = 'LETICIA ALVARENGA GOMES FREITAS'
        AND v.loja_id = l.id
  );

-- MARIANA: supervisionava HELP RAMOS ate a transferencia.
INSERT INTO public.supervisor_vigencia
    (nome, loja_id, vigencia_inicio, vigencia_fim)
SELECT 'MARIANA CARLA LAMIN DA SILVA', l.id,
       DATE '2020-01-01', DATE '2026-08-04'
FROM public.lojas l
WHERE l.nome = 'HELP RAMOS'
  AND NOT EXISTS (
      SELECT 1 FROM public.supervisor_vigencia v
      WHERE v.nome_normalizado = 'MARIANA CARLA LAMIN DA SILVA'
        AND v.loja_id = l.id
  );

-- DJANE: supervisionava HELP COPACABANA NOVA ate a transferencia.
INSERT INTO public.supervisor_vigencia
    (nome, loja_id, vigencia_inicio, vigencia_fim)
SELECT 'DJANE MARIA PEREIRA DOS SANTOS', l.id,
       DATE '2020-01-01', DATE '2026-08-04'
FROM public.lojas l
WHERE l.nome = 'HELP COPACABANA NOVA'
  AND NOT EXISTS (
      SELECT 1 FROM public.supervisor_vigencia v
      WHERE v.nome_normalizado = 'DJANE MARIA PEREIRA DOS SANTOS'
        AND v.loja_id = l.id
  );

COMMIT;


-- ===========================================
-- 2. Mover o inicio das janelas ABERTAS (lojas de destino)
--
-- A guarda de sobreposicao do CORRIGIR_INICIO compara por (pessoa,
-- LOJA): as janelas de origem inseridas acima sao de outra loja, entao
-- nao bloqueiam — que e o comportamento correto, ja que a pessoa esteve
-- em duas lojas distintas em periodos distintos.
--
-- Idempotente: reexecutar devolve 'no-op'.
-- ===========================================

SELECT public.fn_aplicar_mudanca_supervisor(
    'MARIANA CARLA LAMIN DA SILVA', 'HELP BELFORD ROXO SAO JOSE',
    DATE '2026-08-04', 'CORRIGIR_INICIO');

SELECT public.fn_aplicar_mudanca_supervisor(
    'DJANE MARIA PEREIRA DOS SANTOS', 'HELP RAMOS',
    DATE '2026-08-04', 'CORRIGIR_INICIO');


-- ===========================================
-- Validacao (apos executar)
-- ===========================================
-- 1) Continuidade das tres lojas da cascata:
--
--    SELECT l.nome AS loja, v.nome, v.vigencia_inicio, v.vigencia_fim
--    FROM supervisor_vigencia v
--    JOIN lojas l ON l.id = v.loja_id
--    WHERE l.nome IN ('HELP BELFORD ROXO SAO JOSE', 'HELP RAMOS',
--                     'HELP COPACABANA NOVA')
--    ORDER BY l.nome, v.vigencia_inicio;
--    -- Esperado:
--    --   BELFORD ROXO SAO JOSE  LETICIA  2020-01-01 -> 2026-08-04
--    --   BELFORD ROXO SAO JOSE  MARIANA  2026-08-04 -> aberta
--    --   COPACABANA NOVA        DJANE    2020-01-01 -> 2026-08-04
--    --   COPACABANA NOVA        RAIANE   2026-08-18 -> aberta
--    --   RAMOS                  MARIANA  2020-01-01 -> 2026-08-04
--    --   RAMOS                  DJANE    2026-08-04 -> aberta
--
-- 2) Ninguem com duas janelas ABERTAS na mesma loja, e nenhuma
--    sobreposicao por pessoa:
--
--    SELECT nome_normalizado, count(*)
--    FROM supervisor_vigencia WHERE vigencia_fim IS NULL
--    GROUP BY nome_normalizado HAVING count(*) > 1;
--    -- Esperado: 0 linhas (nenhum supervisor multi-loja hoje).
--
-- 3) Invariante da 077 intacta — a 084 so mexe em historia:
--
--    SELECT
--      (SELECT count(*) FROM supervisor_vigencia WHERE vigencia_fim IS NULL)
--        AS abertas,
--      (SELECT count(*) FROM supervisores) AS foto;
--    -- Esperado: iguais (47).
--
-- 4) Caderno intocado (nao precisa republicar):
--
--    SELECT obter_caderno_publicado(6, 2026) -> 'summary'
--             -> 'headcountDiagnostics' ->> 'supervisorsExcluded';
--    -- Esperado: inalterado. MARIANA e DJANE seguem supervisoras em
--    -- todo mes passado (mudou a loja, nao o papel) e LETICIA esta
--    -- 'Desligado (a)', fora do universo ativo.
-- =====================================================
