-- =====================================================
-- Migracao 110: promocao de HUGO a supervisor de HELP MADUREIRA
-- Data: 2026-09-08
-- Depende de: 076 (supervisor_vigencia), 087 (consultor_vigencia diaria)
--
-- Fato confirmado pela operacao:
--   * HUGO SANTOS BENTO DA SILVA era CONSULTOR em HELP BANGU;
--   * tornou-se SUPERVISOR de HELP MADUREIRA em 01/09/2026;
--   * BARBARA DE SOUZA PECANHA saiu da supervisao de HELP MADUREIRA na
--     mesma data — HUGO a substituiu. Ela PERMANECE consultora da loja.
--
-- Detectado junto com o caso da 109: o ETL de contratos criou o cadastro
-- (HUGO, HELP MADUREIRA) em 03/09 as 15:24:07 ao gravar 2 ADEs de 02/09,
-- e nenhum dos dois ledgers soube da mudanca. A loja do cadastro estava
-- CERTA — o que faltava era o papel.
--
--
-- POR QUE DUAS ESCRITAS EM consultor_vigencia, E NAO SO A SAIDA
-- -------------------------------------------------------------
-- Supervisor NAO deixa de ter janela de consultor neste modelo. Medido
-- em 2026-09-08: as 47 janelas de supervisao abertas pertencem a 47
-- pessoas, e TODAS as 47 tem tambem `consultor_vigencia` aberta na
-- propria loja. A exclusao dos rankings acontece na LEITURA
-- (`_fetch_vinculos_consultores` filtra por `carregar_supervisores`),
-- nunca pela ausencia da janela. Entao HUGO fecha BANGU e abre
-- MADUREIRA como consultor, exatamente como os outros 47.
--
--
-- FRONTEIRA E ANCORA
-- ------------------
-- `carregar_supervisores` resolve o papel pelo ULTIMO DIA da
-- competencia, com janela meio-aberta [inicio, fim). Com o corte em
-- 2026-09-01:
--
--   08/2026 (ancora 31/08): BARBARA ainda e supervisora
--                           (fim 01/09 > 31/08); HUGO ainda nao
--                           (inicio 01/09 > 31/08). Historia intacta —
--                           os 1.563 contratos dele em BANGU seguem
--                           sendo producao de CONSULTOR.
--   09/2026 (ancora 30/09): HUGO e supervisor; BARBARA nao
--                           (fim 01/09 nao e > 30/09).
--
--
-- EFEITO NUMERICO — LER ANTES DE APLICAR
-- ---------------------------------------
-- 1. HUGO sai do denominador de consultores de 09/2026 e os 2 contratos
--    dele em MADUREIRA (02/09, R$ 0,00 e R$ 754,06) viram producao de
--    supervisor: continuam no total da loja (`paidEffective`), saem do
--    numerador e dos rankings (`paidByConsultants`). Mesma regra que a
--    106 aplicou a Patricia.
-- 2. BARBARA ENTRA no denominador de consultores de MADUREIRA a partir
--    de 09/2026 — ela ja tem `consultor_vigencia` aberta na loja desde
--    2025-10-06, e o filtro de supervisor deixa de exclui-la. Ela tem
--    ZERO contratos desde 08/2026, entao entra como cabeca sem
--    producao e dilui a produtividade da loja.
--
--    Se ela na verdade foi desligada (e nao apenas devolvida a
--    consultoria), o certo NAO e esta migration: e fechar tambem a
--    `consultor_vigencia` dela com a data real de saida. Esta migration
--    grava o que foi confirmado — que ela permanece — e deixa o efeito
--    visivel de proposito.
--
-- `supervisor_vigencia` nao tem coluna `origem` (so `consultor_vigencia`
-- tem), entao a procedencia MANUAL e marcada apenas do lado do
-- consultor.
--
-- Executar no Supabase SQL Editor, depois da 109.
-- =====================================================

BEGIN;

LOCK TABLE public.supervisor_vigencia IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.consultor_vigencia  IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_bangu_id      UUID;
    v_madureira_id  UUID;
    v_janela_id     UUID;
    v_quantidade    INTEGER;
    v_conflito      INTEGER;
    v_hugo    CONSTANT TEXT := 'HUGO SANTOS BENTO DA SILVA';
    v_barbara CONSTANT TEXT := 'BARBARA DE SOUZA PECANHA';
    v_corte   CONSTANT DATE := DATE '2026-09-01';
BEGIN
    -- ---- 1. Resolucao das lojas ----
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_bangu_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP BANGU';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 110: HELP BANGU ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_madureira_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP MADUREIRA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 110: HELP MADUREIRA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    -- ---- 2. Pre-condicao: a producao respeita o corte de 01/09 ----
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_hugo
       AND ct.loja_id = v_bangu_id
       AND ct.data_cadastro >= v_corte;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 110: % contrato(s) de Hugo em BANGU a partir de 01/09/2026 — a fronteira nao e limpa',
            v_quantidade;
    END IF;

    -- ---- 3. Supervisao: fecha BARBARA em MADUREIRA ----
    -- Guarda de invariante: hoje nenhuma das 47 lojas tem dois
    -- supervisores abertos, e o indice `uq_sv_supervisor_loja_aberta` e
    -- por (pessoa, loja) — nao impede dois. Se MADUREIRA ja tiver algo
    -- diferente do esperado, para aqui.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.supervisor_vigencia s
     WHERE s.loja_id = v_madureira_id
       AND s.vigencia_fim IS NULL;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 110: HELP MADUREIRA ja tem % supervisores abertos antes da troca',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(s.id))[1]
      INTO v_quantidade, v_janela_id
      FROM public.supervisor_vigencia s
     WHERE s.nome_normalizado = v_barbara
       AND s.loja_id = v_madureira_id
       AND s.vigencia_fim IS NULL;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 110: % janelas de supervisao abertas de Barbara em Madureira (esperado 0 ou 1)',
            v_quantidade;
    END IF;

    IF v_quantidade = 1 THEN
        SELECT count(*)::integer
          INTO v_conflito
          FROM public.supervisor_vigencia s
         WHERE s.id = v_janela_id
           AND s.vigencia_inicio >= v_corte;

        IF v_conflito <> 0 THEN
            RAISE EXCEPTION
                'Migration 110: janela de Barbara comeca em ou depois de 01/09/2026 — fechar violaria chk_sv_vigencia_ordem';
        END IF;

        UPDATE public.supervisor_vigencia s
           SET vigencia_fim = v_corte
         WHERE s.id = v_janela_id;
    END IF;

    -- ---- 4. Supervisao: abre HUGO em MADUREIRA ----
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.supervisor_vigencia s
     WHERE s.nome_normalizado = v_hugo;

    IF v_quantidade = 0 THEN
        INSERT INTO public.supervisor_vigencia
            (nome, loja_id, vigencia_inicio, vigencia_fim)
        VALUES
            (v_hugo, v_madureira_id, v_corte, NULL);
    ELSE
        -- Ja existe alguma janela dele: so aceita se for exatamente a
        -- que esta migration cria (reexecucao).
        SELECT count(*)::integer
          INTO v_conflito
          FROM public.supervisor_vigencia s
         WHERE s.nome_normalizado = v_hugo
           AND s.loja_id = v_madureira_id
           AND s.vigencia_inicio = v_corte
           AND s.vigencia_fim IS NULL;

        IF v_conflito <> v_quantidade THEN
            RAISE EXCEPTION
                'Migration 110: Hugo ja tem % janela(s) de supervisao, % delas compativeis com a promocao',
                v_quantidade, v_conflito;
        END IF;
    END IF;

    -- ---- 5. Consultor: fecha BANGU ----
    SELECT count(*), (array_agg(v.id))[1]
      INTO v_quantidade, v_janela_id
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_hugo
       AND v.loja_id = v_bangu_id
       AND v.vigencia_fim IS NULL;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 110: % janelas abertas de Hugo em Bangu (esperado 0 ou 1)',
            v_quantidade;
    END IF;

    IF v_quantidade = 1 THEN
        SELECT count(*)::integer
          INTO v_conflito
          FROM public.consultor_vigencia v
         WHERE v.id = v_janela_id
           AND v.vigencia_inicio >= v_corte;

        IF v_conflito <> 0 THEN
            RAISE EXCEPTION
                'Migration 110: janela de Bangu comeca em ou depois de 01/09/2026 — fechar violaria chk_cv_vigencia_ordem';
        END IF;

        UPDATE public.consultor_vigencia v
           SET vigencia_fim = v_corte,
               origem       = 'MANUAL'
         WHERE v.id = v_janela_id;
    END IF;

    -- ---- 6. Consultor: abre MADUREIRA ----
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_hugo
       AND v.loja_id = v_madureira_id;

    IF v_quantidade = 0 THEN
        INSERT INTO public.consultor_vigencia
            (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
        VALUES
            (v_hugo, v_madureira_id, v_corte, NULL, 'MANUAL');
    ELSIF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 110: % janelas de Hugo em Madureira (esperado 0 ou 1)',
            v_quantidade;
    END IF;

    -- ---- 7. Pos-condicoes ----
    -- MADUREIRA tem exatamente um supervisor aberto, e e HUGO.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.supervisor_vigencia s
     WHERE s.loja_id = v_madureira_id
       AND s.vigencia_fim IS NULL
       AND s.nome_normalizado = v_hugo;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 110: pos-condicao falhou — Hugo nao e o unico supervisor aberto de Madureira';
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.supervisor_vigencia s
     WHERE s.loja_id = v_madureira_id
       AND s.vigencia_fim IS NULL;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 110: pos-condicao falhou — HELP MADUREIRA ficou com % supervisores abertos',
            v_quantidade;
    END IF;

    -- HUGO tem exatamente uma janela de consultor aberta, em MADUREIRA.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_hugo
       AND v.vigencia_fim IS NULL
       AND v.loja_id = v_madureira_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 110: pos-condicao falhou — a janela de consultor aberta de Hugo nao e Madureira';
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_hugo
       AND v.vigencia_fim IS NULL;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 110: pos-condicao falhou — Hugo ficou com % janelas de consultor abertas',
            v_quantidade;
    END IF;

    -- Emenda sem vago nem sobreposicao na linha do tempo dele.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM (
          SELECT v.vigencia_inicio,
                 lag(v.vigencia_fim) OVER (ORDER BY v.vigencia_inicio) AS fim_ant
            FROM public.consultor_vigencia v
           WHERE v.nome_normalizado = v_hugo
      ) t
     WHERE t.fim_ant IS NOT NULL
       AND t.vigencia_inicio <> t.fim_ant;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 110: pos-condicao falhou — % emenda(s) com vago ou sobreposicao na linha do tempo de Hugo',
            v_quantidade;
    END IF;

    -- BARBARA continua consultora de MADUREIRA: a janela dela NAO foi
    -- tocada. Se esta contagem der 0, alguem fechou junto por engano.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_barbara
       AND v.loja_id = v_madureira_id
       AND v.vigencia_fim IS NULL;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 110: pos-condicao falhou — Barbara perdeu a janela de consultora em Madureira (% abertas)',
            v_quantidade;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) A troca de supervisao em MADUREIRA, sem vago nem sobreposicao:
--
--    SELECT s.nome, s.vigencia_inicio, s.vigencia_fim
--      FROM supervisor_vigencia s
--      JOIN lojas l ON l.id = s.loja_id
--     WHERE l.nome = 'HELP MADUREIRA'
--     ORDER BY s.vigencia_inicio;
--
--    -- esperado:
--    --   BARBARA DE SOUZA PECANHA     2020-01-01   2026-09-01
--    --   HUGO SANTOS BENTO DA SILVA   2026-09-01   NULL
--
-- 2) A linha do tempo de consultor do Hugo:
--
--    SELECT l.nome, v.vigencia_inicio, v.vigencia_fim, v.origem
--      FROM consultor_vigencia v
--      JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado = 'HUGO SANTOS BENTO DA SILVA'
--     ORDER BY v.vigencia_inicio;
--
--    -- esperado:
--    --   HELP BANGU       2025-04-01   2026-09-01   MANUAL
--    --   HELP MADUREIRA   2026-09-01   NULL         MANUAL
--
-- 3) O papel muda de mes para mes, e a historia de agosto fica intacta:
--
--    -- 08/2026 deve listar BARBARA em MADUREIRA; 09/2026, HUGO.
--    -- Conferir pela aba de gestao ou por carregar_supervisores(8, 2026)
--    -- e carregar_supervisores(9, 2026).
--
-- 4) Os 2 contratos do Hugo em 09/2026 deixam de contar como producao de
--    consultor. `fn_contar_pagamentos_sem_vinculo_origem(9, 2026)` os
--    EXCLUI (a funcao ja filtra supervisores), entao o contador tende a
--    cair alem dos 5 da 109 — conferir antes/depois em vez de assumir.
