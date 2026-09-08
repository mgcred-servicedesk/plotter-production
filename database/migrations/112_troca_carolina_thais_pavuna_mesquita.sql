-- =====================================================
-- Migracao 112: troca de CAROLINA e THAIS entre PAVUNA e MESQUITA
-- Data: 2026-09-08
-- Depende de: 087 (consultor_vigencia diaria)
--
-- Fato confirmado pela operacao:
--   * em 03/09/2026 as duas migraram, em sentidos opostos:
--       CAROLINA PEREIRA CUSTODIO  HELP PAVUNA   -> HELP MESQUITA
--       THAIS EUFRASIO MARTINS     HELP MESQUITA -> HELP PAVUNA
--
-- As duas numa migration so porque e UM evento: a troca e simetrica e
-- os headcounts das duas lojas so fecham se as quatro escritas
-- acontecerem juntas. Aplicar metade deixaria PAVUNA com duas pessoas e
-- MESQUITA com nenhuma por um instante — ou, se a outra metade falhasse,
-- de forma permanente.
--
--
-- A PRODUCAO CONFIRMA A DATA (medido em 2026-09-08)
-- --------------------------------------------------
--   CAROLINA   ... 01/09 PAVUNA=3   02/09 PAVUNA=4
--                  03/09 MESQUITA=6  PAVUNA=1
--   THAIS      ... 01/09 MESQUITA=2 02/09 MESQUITA=3
--                  03/09 PAVUNA=2
--
-- THAIS e disjunta e inequivoca. CAROLINA tem UM contrato avulso em
-- PAVUNA no proprio dia da virada, contra 6 em MESQUITA — digitacao
-- residual do dia da troca, nao presenca.
--
--
-- POR QUE MANUAL, E NAO ESPERAR O BACKFILL
-- -----------------------------------------
-- A regra automatica da 087 erraria o caso da CAROLINA. Dentro de
-- 09/2026 as janelas de dias se SOBREPOEM (PAVUNA 01-03/09, MESQUITA
-- 03/09), e mes com sobreposicao cai na clausula da "loja dominante do
-- mes" — PAVUNA, com 8 contratos contra 6. O mes inteiro iria para
-- PAVUNA e a transferencia sumiria.
--
-- E exatamente o cenario que a 087 documenta como limite conhecido: a
-- sobreposicao distingue transferencia de digitacao avulsa quando a
-- minoria e infima, mas nao quando o contrato avulso cai no dia da
-- virada. So a data declarada resolve. `origem = 'MANUAL'` tambem
-- imuniza contra o rebuild, que apaga so `origem LIKE 'BACKFILL%'`.
--
--
-- EFEITO NO DIAGNOSTICO DE ORIGEM: NENHUM
-- ----------------------------------------
-- Com o corte em 03/09 (janela meio-aberta), o contrato avulso da
-- CAROLINA em PAVUNA nesse dia fica FORA da vigencia dela em PAVUNA.
-- Isso normalmente somaria 1 a
-- `fn_contar_pagamentos_sem_vinculo_origem`, mas nao soma: o contrato
-- 3000257 (proposta 103820892) esta CANCELADO / NAO PAGO AO CLIENTE,
-- entao `paid_effective` = 0 e a funcao so conta `paid_effective > 0`.
--
-- A alternativa (cortar em 04/09) deixaria os 6 contratos de MESQUITA
-- de 03/09 sem vinculo de origem — seis em vez de zero. O corte
-- declarado e tambem o mais barato.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_pavuna_id    UUID;
    v_mesquita_id  UUID;
    v_quantidade   INTEGER;
    v_conflito     INTEGER;
    v_corte CONSTANT DATE := DATE '2026-09-03';
    -- (nome, loja de origem, loja de destino)
    v_pessoas CONSTANT TEXT[] := ARRAY[
        'CAROLINA PEREIRA CUSTODIO',
        'THAIS EUFRASIO MARTINS'
    ];
    v_nome         TEXT;
    v_origem_id    UUID;
    v_destino_id   UUID;
    v_janela_id    UUID;
    i              INTEGER;
BEGIN
    -- ---- 1. Resolucao das lojas ----
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_pavuna_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP PAVUNA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 112: HELP PAVUNA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_mesquita_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP MESQUITA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 112: HELP MESQUITA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    -- ---- 2. As duas pernas da troca, mesmo tratamento ----
    FOR i IN 1 .. array_length(v_pessoas, 1) LOOP
        v_nome := v_pessoas[i];

        IF v_nome = 'CAROLINA PEREIRA CUSTODIO' THEN
            v_origem_id  := v_pavuna_id;
            v_destino_id := v_mesquita_id;
        ELSE
            v_origem_id  := v_mesquita_id;
            v_destino_id := v_pavuna_id;
        END IF;

        -- Pre-condicao: nada na loja de DESTINO antes do corte. O
        -- inverso NAO e exigido — a CAROLINA tem um avulso em PAVUNA no
        -- proprio dia da virada, e e legitimo.
        SELECT count(*)::integer
          INTO v_quantidade
          FROM public.contratos ct
          JOIN public.consultores cs ON cs.id = ct.consultor_id
         WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
           AND ct.loja_id = v_destino_id
           AND ct.data_cadastro < v_corte;

        IF v_quantidade <> 0 THEN
            RAISE EXCEPTION
                'Migration 112: % tem % contrato(s) na loja de destino antes de 03/09/2026 — a fronteira nao e limpa',
                v_nome, v_quantidade;
        END IF;

        -- Fecha a janela aberta na loja de ORIGEM.
        SELECT count(*), (array_agg(v.id))[1]
          INTO v_quantidade, v_janela_id
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = v_nome
           AND v.loja_id = v_origem_id
           AND v.vigencia_fim IS NULL;

        IF v_quantidade > 1 THEN
            RAISE EXCEPTION
                'Migration 112: % tem % janelas abertas na loja de origem (esperado 0 ou 1)',
                v_nome, v_quantidade;
        END IF;

        IF v_quantidade = 1 THEN
            SELECT count(*)::integer
              INTO v_conflito
              FROM public.consultor_vigencia v
             WHERE v.id = v_janela_id
               AND v.vigencia_inicio >= v_corte;

            IF v_conflito <> 0 THEN
                RAISE EXCEPTION
                    'Migration 112: janela de origem de % comeca em ou depois de 03/09/2026 — fechar violaria chk_cv_vigencia_ordem',
                    v_nome;
            END IF;

            UPDATE public.consultor_vigencia v
               SET vigencia_fim = v_corte,
                   origem       = 'MANUAL'
             WHERE v.id = v_janela_id;
        END IF;

        -- Abre a janela na loja de DESTINO.
        SELECT count(*)::integer
          INTO v_quantidade
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = v_nome
           AND v.loja_id = v_destino_id
           AND v.vigencia_fim IS NULL;

        IF v_quantidade = 0 THEN
            INSERT INTO public.consultor_vigencia
                (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
            VALUES
                (v_nome, v_destino_id, v_corte, NULL, 'MANUAL');
        ELSIF v_quantidade = 1 THEN
            SELECT count(*)::integer
              INTO v_conflito
              FROM public.consultor_vigencia v
             WHERE v.nome_normalizado = v_nome
               AND v.loja_id = v_destino_id
               AND v.vigencia_fim IS NULL
               AND v.vigencia_inicio = v_corte;

            IF v_conflito <> 1 THEN
                RAISE EXCEPTION
                    'Migration 112: % ja tem janela aberta no destino com inicio diferente de 03/09/2026',
                    v_nome;
            END IF;
        END IF;

        -- Pos-condicoes por pessoa.
        SELECT count(*)::integer
          INTO v_quantidade
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = v_nome
           AND v.vigencia_fim IS NULL;

        IF v_quantidade <> 1 THEN
            RAISE EXCEPTION
                'Migration 112: pos-condicao falhou — % ficou com % janelas abertas (esperado 1)',
                v_nome, v_quantidade;
        END IF;

        SELECT count(*)::integer
          INTO v_quantidade
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = v_nome
           AND v.vigencia_fim IS NULL
           AND v.loja_id = v_destino_id
           AND v.vigencia_inicio = v_corte;

        IF v_quantidade <> 1 THEN
            RAISE EXCEPTION
                'Migration 112: pos-condicao falhou — a janela aberta de % nao e a loja de destino desde 03/09/2026',
                v_nome;
        END IF;

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
                'Migration 112: pos-condicao falhou — % emenda(s) com vago ou sobreposicao na linha do tempo de %',
                v_quantidade, v_nome;
        END IF;
    END LOOP;

    -- ---- 3. Pos-condicao da TROCA: a simetria fechou ----
    -- Uma em cada loja, e nao as duas na mesma.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = ANY (v_pessoas)
       AND v.vigencia_fim IS NULL
       AND v.loja_id = v_mesquita_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 112: pos-condicao falhou — % das duas ficaram abertas em MESQUITA (esperado 1)',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = ANY (v_pessoas)
       AND v.vigencia_fim IS NULL
       AND v.loja_id = v_pavuna_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 112: pos-condicao falhou — % das duas ficaram abertas em PAVUNA (esperado 1)',
            v_quantidade;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
--    SELECT v.nome, l.nome AS loja, v.vigencia_inicio, v.vigencia_fim, v.origem
--      FROM consultor_vigencia v
--      JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado IN ('CAROLINA PEREIRA CUSTODIO',
--                                  'THAIS EUFRASIO MARTINS')
--     ORDER BY v.nome, v.vigencia_inicio;
--
--    -- esperado:
--    --   CAROLINA  HELP CAXIAS GUANABARA  2025-05-01  2026-07-06  BACKFILL_CENSURADO
--    --   CAROLINA  HELP PAVUNA            2026-07-06  2026-09-03  MANUAL
--    --   CAROLINA  HELP MESQUITA          2026-09-03  NULL        MANUAL
--    --   THAIS     HELP MESQUITA          2025-12-19  2026-09-03  MANUAL
--    --   THAIS     HELP PAVUNA            2026-09-03  NULL        MANUAL
--
-- O contador de origem NAO deve subir por causa desta migration (o
-- avulso da Carolina em Pavuna no dia 03/09 esta cancelado e nao pago):
--
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(9, 2026);
