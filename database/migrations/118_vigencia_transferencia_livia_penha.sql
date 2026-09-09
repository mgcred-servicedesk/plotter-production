-- =====================================================
-- Migracao 118: transferencia de LIVIA para HELP PENHA
-- Data: 2026-09-09
-- Depende de: 087 (ledger em granularidade de dia)
--
-- Fato confirmado pela operacao (2026-09-09):
--   * LIVIA GOMES DE SANT ANNA foi transferida para HELP PENHA em
--     04/09/2026;
--   * ate 03/09 ela era de HELP BONSUCESSO.
--
--
-- COMO O CASO APARECEU
-- --------------------
-- Pelo detector `fn_diag_vinculo_divergente` (migration 116), na primeira
-- vez que ele rodou. Forma identica ao caso JOYCE (109): o ETL de
-- contratos criou o cadastro (LIVIA, HELP PENHA) em 2026-09-09 13:18 ao
-- gravar producao sob a filial nova, porque `uq_consultores_nome_loja` e
-- (nome, loja_id) e um par inedito INSERE em vez de reconhecer a pessoa
-- que ja existia. A FOTO passou a dizer PENHA — o cadastro novo tem
-- `updated_at` maior e vence o dedup. O LEDGER continuou dizendo
-- BONSUCESSO desde 2026-05-12, `BACKFILL_PRODUCAO`.
--
-- A diferenca para a JOYCE e o veredito: la a filial estava ERRADA e a
-- pessoa nunca trabalhou na loja; aqui a transferencia e REAL. A forma
-- dos dados nao distingue os dois — so a operacao. E a razao de o
-- detector reportar em vez de decidir.
--
--
-- A PRODUCAO CONFIRMA A DATA (medido em 2026-09-09)
-- --------------------------------------------------
--   BONSUCESSO   02/09 x2, 03/09 x3      ultimo contrato: 03/09
--   PENHA        04/09 x4, 08/09 x1      primeiro contrato: 04/09
--
--   zero PENHA antes de 04/09; zero BONSUCESSO em ou depois de 04/09.
--
-- Fronteira limpa e disjunta: a data declarada e a fronteira observada
-- coincidem exatamente. Nao ha residuo a explicar, ao contrario da
-- CAROLINA (112), que tinha 1 avulso em PAVUNA no proprio dia da virada.
--
--
-- POR QUE 'MANUAL' NAS DUAS JANELAS — E POR QUE AQUI IMPORTA MAIS
-- ----------------------------------------------------------------
-- O rebuild do backfill (087) apaga so `origem LIKE 'BACKFILL%'` e
-- preserva ETL/MANUAL. Marcar so a janela nova deixaria a de BONSUCESSO
-- exposta: um rebuild apagaria o historico dela anterior a 09/2026.
--
-- E neste caso a regra automatica erraria de um jeito particular. A 087
-- decide pela LOJA DOMINANTE DO MES quando ha duas lojas na mesma
-- competencia — e 09/2026 esta 5 a 5. Nao ha dominante: o desempate cai
-- em criterio que nao expressa fato nenhum. Mesmo motivo da 112, so que
-- ali a minoria era 1 contra 6 e aqui e um empate exato.
--
--
-- FRONTEIRA
-- ---------
-- Janela meio-aberta [inicio, fim), como em toda a 086/087: fechar
-- BONSUCESSO em 2026-09-04 faz o ultimo dia coberto ser 03/09, e PENHA
-- comeca em 04/09. Emenda sem vago nem sobreposicao — e a data declarada
-- e a mesma do primeiro contrato em PENHA, entao declarado e inferido
-- concordam.
--
--
-- POR QUE UM BLOCO DIRETO E NAO A fn_movimentacoes_replace (117)
-- ---------------------------------------------------------------
-- Esta migration e auto-contida de proposito: nao depende de a 117 estar
-- aplicada nem correta. Se a porta nova tiver defeito, a correcao da
-- LIVIA nao fica presa junto — setembro fecha antes disso.
--
-- E a guarda aqui BLOQUEIA, ao contrario da 117, que reporta. Nao ha
-- inconsistencia: a 117 processa carga com varias pessoas e recusar tudo
-- por causa de uma linha e o erro que a 100 corrigiu. Esta migration
-- escreve UMA pessoa; se o fato mudou desde a medicao, parar e pedir olho
-- humano e o desfecho certo. Mesma escolha da 109.
--
--
-- EFEITO NUMERICO
-- ---------------
-- Em 09/2026 os dias uteis dela passam a ser repartidos (R3): 01/09 a
-- 03/09 em BONSUCESSO, 04/09 em diante em PENHA. A soma continua
-- devolvendo UMA pessoa. Hoje, com a janela unica aberta, BONSUCESSO
-- carrega o mes inteiro dela enquanto a producao de PENHA aparece em
-- PENHA — denominador numa loja, numerador em duas.
--
-- Depois desta migration, foto e ledger concordam: o cadastro vencedor do
-- dedup ja e o de PENHA.
--
-- Rematerializar o Caderno de 09/2026 depois de aplicar.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_bonsucesso_id UUID;
    v_penha_id      UUID;
    v_janela_id     UUID;
    v_quantidade    INTEGER;
    v_conflito      INTEGER;
    v_nome CONSTANT TEXT := 'LIVIA GOMES DE SANT ANNA';
    v_corte CONSTANT DATE := DATE '2026-09-04';
BEGIN
    -- ---- 1. Resolucao das lojas ----
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_bonsucesso_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP BONSUCESSO';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 118: HELP BONSUCESSO ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_penha_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP PENHA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 118: HELP PENHA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    -- ---- 2. Pre-condicao: a producao respeita o corte de 04/09 ----
    -- Medido limpo em 2026-09-09. Se a origem voltar a mudar antes da
    -- aplicacao, esta guarda para a migration em vez de gravar uma
    -- fronteira que os contratos ja nao sustentam.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_bonsucesso_id
       AND ct.data_cadastro >= v_corte;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 118: % contrato(s) em BONSUCESSO a partir de 04/09/2026 — a fronteira nao e mais limpa',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_penha_id
       AND ct.data_cadastro < v_corte;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 118: % contrato(s) em PENHA antes de 04/09/2026 — a fronteira nao e mais limpa',
            v_quantidade;
    END IF;

    -- ---- 3. Fecha a janela de BONSUCESSO ----
    -- Idempotente: na reexecucao a janela ja esta fechada e o SELECT nao
    -- acha linha aberta, entao o UPDATE nao roda.
    SELECT count(*), (array_agg(v.id))[1]
      INTO v_quantidade, v_janela_id
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_bonsucesso_id
       AND v.vigencia_fim IS NULL;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 118: % janelas abertas de Livia em Bonsucesso (esperado 0 ou 1)',
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
                'Migration 118: janela de Bonsucesso comeca em ou depois de 04/09/2026 — fechar violaria chk_cv_vigencia_ordem';
        END IF;

        UPDATE public.consultor_vigencia v
           SET vigencia_fim = v_corte,
               origem       = 'MANUAL'
         WHERE v.id = v_janela_id;
    END IF;

    -- ---- 4. Abre a janela de PENHA ----
    -- `uq_cv_consultor_loja_aberta` ja garante no maximo uma aberta por
    -- (pessoa, loja); o IF torna a reexecucao um no-op em vez de erro.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_penha_id;

    IF v_quantidade = 0 THEN
        INSERT INTO public.consultor_vigencia
            (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
        VALUES
            (v_nome, v_penha_id, v_corte, NULL, 'MANUAL');
    ELSIF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 118: % janelas de Livia em Penha (esperado 0 ou 1)',
            v_quantidade;
    END IF;

    -- ---- 5. Pos-condicoes ----
    -- Exatamente uma janela aberta, e ela e a de PENHA desde 04/09.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_fim IS NULL;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 118: pos-condicao falhou — % janelas abertas (esperado 1)',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_fim IS NULL
       AND v.loja_id = v_penha_id
       AND v.vigencia_inicio = v_corte;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 118: pos-condicao falhou — a janela aberta nao e HELP PENHA desde 04/09/2026';
    END IF;

    -- Emenda sem vago nem sobreposicao: nenhuma janela dela pode comecar
    -- antes do fim da anterior.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM (
          SELECT v.vigencia_inicio,
                 lag(v.vigencia_fim) OVER (ORDER BY v.vigencia_inicio) AS fim_ant
            FROM public.consultor_vigencia v
           WHERE v.nome_normalizado = v_nome
      ) t
     WHERE t.fim_ant IS NOT NULL
       AND t.vigencia_inicio <> t.fim_ant;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 118: pos-condicao falhou — % emenda(s) com vago ou sobreposicao na linha do tempo de Livia',
            v_quantidade;
    END IF;

    -- O cadastro que o dedup escolhe (updated_at mais recente) e o de
    -- PENHA: depois desta migration foto e ledger concordam. Nao e uma
    -- escrita desta migration — e a confirmacao de que ela nao precisou
    -- mexer em `consultores`.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM (
          SELECT c.loja_id
            FROM public.consultores c
           WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
           ORDER BY c.updated_at DESC NULLS LAST, c.id DESC
           LIMIT 1
      ) t
     WHERE t.loja_id = v_penha_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 118: pos-condicao falhou — o cadastro vencedor de Livia nao e HELP PENHA';
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) A linha do tempo dela:
--
--    SELECT l.nome, v.vigencia_inicio, v.vigencia_fim, v.origem
--      FROM consultor_vigencia v
--      JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado = 'LIVIA GOMES DE SANT ANNA'
--     ORDER BY v.vigencia_inicio;
--
--    -- esperado:
--    --   HELP BONSUCESSO   2026-05-12   2026-09-04   MANUAL
--    --   HELP PENHA        2026-09-04   NULL         MANUAL
--
-- 2) O detector nao a reporta mais (esta era a UNICA divergencia
--    medida em 2026-09-09):
--
--    SELECT jsonb_array_length(
--        public.fn_diag_vinculo_divergente() -> 'divergencias');
--    -- esperado: 0
--
--    -- Requer a migration 116 aplicada. Sem ela, o equivalente e
--    -- comparar a loja do cadastro vencedor com a da janela aberta.
--
-- 3) A producao dela em 09/2026 continua repartida entre as duas lojas —
--    e agora o denominador acompanha:
--
--    SELECT loja, count(*), sum(valor_consolidado)
--      FROM v_contratos_dashboard
--     WHERE consultor = 'LIVIA GOMES DE SANT ANNA'
--       AND data_status_pagamento >= DATE '2026-09-01'
--     GROUP BY loja;
--
-- 4) O contador de origem tende a CAIR: os 5 contratos de PENHA passam a
--    ter vigencia na loja do contrato. Comparar antes/depois em vez de
--    assumir — ele agrega varias causas:
--
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(9, 2026);
--    -- marcava 53 em 2026-09-09
--
-- 5) Rematerializar o Caderno de 09/2026:
--
--    SELECT fn_materializar_caderno(9, 2026);
--
--
-- TESTE NEGATIVO DA 117 (opcional, se ela ja estiver aplicada)
-- ------------------------------------------------------------
-- Depois desta migration, pedir a MESMA transferencia a porta nova deve
-- ser recusado — a pessoa ja esta em PENHA:
--
--    SELECT public.fn_movimentacoes_replace(jsonb_build_array(
--        jsonb_build_object(
--            'linha', 2, 'tipo', 'TRANSFERENCIA',
--            'nome', 'LIVIA GOMES DE SANT ANNA',
--            'loja_destino', (SELECT id FROM lojas WHERE nome = 'HELP PENHA'),
--            'data_efetiva', '2026-09-04')), true);
--
--    -- esperado: pendencia DESTINO_IGUAL_ORIGEM na linha 2, aplicado=false.
--    -- E um jeito barato de conferir que a 117 le o ledger corretamente.
