-- =====================================================
-- Migracao 124: desfaz as previsoes de transferencia da 087 que a
--               producao de setembro desmentiu, e registra a
--               transferencia real de GISELLE para HELP COPACABANA NOVA
-- Data: 2026-10-01
-- Depende de: 086/087 (ledger de vigencia), 105 (guarda de origem),
--             116 (detector foto x ledger), 119 (admissao de Giselle)
--
--
-- O BLOQUEIO QUE TROUXE ESTA MIGRATION
-- ------------------------------------
-- `fn_materializar_caderno(9, 2026)` falha fechado com
-- `unlinkedPaidOriginEvents = 164` (`overlappingEligibleDays = 0`):
-- 164 contratos pagos, R$ 347.089,55 — 2,6% do mes — cuja `data_cadastro`
-- nao cai em nenhuma vigencia da pessoa na loja do contrato. Oito pessoas,
-- quatro causas distintas. Esta migration cobre as DUAS primeiras, que
-- somam 144 eventos e cuja evidencia e unilateral. Ver o fim do arquivo
-- para o que segue bloqueando de proposito.
--
--
-- CAUSA 1 (129 eventos): A PREVISAO DA CTE `transferidos`
-- --------------------------------------------------------
-- A 087 tem, por desenho, um ramo que ADIVINHA transferencia:
--
--   -- ativo hoje numa loja diferente da ultima em que digitou: a
--   -- producao ainda nao mostrou a transferencia. Sem data verificada,
--   -- a janela nova comeca no mes seguinte (nao no dia seguinte).
--
-- Rodando em 2026-08-20 20:42, ela criou 7 janelas abertas comecando em
-- 2026-09-01 e fechou na mesma data a janela da loja onde a pessoa
-- realmente produzia. A loja da janela nova sai da FOTO
-- (`consultores` deduplicado por `updated_at DESC`) — e a foto estava
-- velha para tres dessas pessoas, porque a carga de HC de 2026-08-11
-- 20:44 tocou a linha ANTIGA de cada uma, fazendo o cadastro
-- desatualizado vencer o dedup. A mecanica do par (nome, loja_id) em
-- `uq_consultores_nome_loja` e a mesma de 109/118/121: o ETL INSERE um
-- cadastro novo na loja nova em vez de mover a pessoa, e quem decide qual
-- das duas linhas e a verdade e o `updated_at`.
--
-- Setembro desmentiu a previsao de forma categorica (medido 2026-10-01,
-- `contratos` completo, nao so o pago):
--
--   pessoa        previsao 01/09        producao real                   na loja prevista
--   CAMILLY       HELP COPACABANA       LARANJEIRAS 04/08..30/09 (159)  zero desde 04/08
--   ANA CLARA     HELP S.J. DE MERITI   VILAR DOS TELES 20/07..30/09    zero desde 20/07
--   VICTOR        HELP COPACABANA       COPACABANA NOVA 04/08..04/09    zero, NUNCA
--
-- Victor e o caso extremo: ele nao tem um unico contrato em HELP
-- COPACABANA em toda a base. A janela aberta dele naquela loja e 100%
-- inferencia a partir de um cadastro que a 116 ja acusa como orfao.
--
-- As outras 4 previsoes de 01/09 (DJANE, PATRICIA, e as MANUAL/ETL de
-- HUGO, JOYCE, PEDRO) batem com a producao e ficam como estao.
--
--
-- POR QUE A 116 NAO PEGOU ISSO — E O QUE MUDA DEPOIS DAQUI
-- --------------------------------------------------------
-- Para CAMILLY e ANA CLARA, foto e ledger CONCORDAM: o ledger copiou a
-- foto. O detector compara os dois e nao ve nada; quem viu foi a guarda
-- de origem da 105, que compara o ledger com a PRODUCAO. As duas
-- superficies de controle nao sao redundantes — esta migration e a prova.
--
-- Depois de aplicada, `fn_diag_vinculo_divergente()` passa de 3 para 5
-- divergencias: CAMILLY e ANA CLARA aparecem. Isso e GANHO, nao regressao.
-- O erro sai do ledger (onde falsificava o denominador em silencio) e vai
-- para o detector, que e onde uma pergunta aberta deve morar. A foto
-- continua errada e precisa ser corrigida na origem — ver follow-ups.
--
--
-- POR QUE `DELETE` E NAO FECHAR A JANELA PREVISTA
-- -----------------------------------------------
-- Mesmo argumento da 121: fechar afirmaria "esteve nesta loja de 01/09
-- ate X", o oposto do fato medido, e manteria peso no denominador da loja
-- errada. `chk_cv_vigencia_ordem` (fim > inicio) nem admite janela de
-- duracao zero. Para "nunca existiu", o caminho e remover a linha.
--
-- A guarda exige `origem LIKE 'BACKFILL%'` na linha que remove: decisao
-- MANUAL ou ETL nunca e apagada por esta migration.
--
--
-- POR QUE `MANUAL` NA JANELA REABERTA
-- -----------------------------------
-- O rebuild do backfill apaga `origem LIKE 'BACKFILL%'` e preserva
-- ETL/MANUAL (mesmo motivo da 118). Se a janela reaberta continuasse
-- BACKFILL_PRODUCAO, um rebuild futuro — com a foto ainda velha —
-- recriaria exatamente a previsao que esta migration desfaz.
--
--
-- CAUSA 2 (15 eventos): A TRANSFERENCIA DE GISELLE, NAO REGISTRADA
-- ----------------------------------------------------------------
-- Admitida em HELP BONSUCESSO em 04/09 pela 119, com janela MANUAL
-- aberta ali. A producao mostra transferencia limpa e disjunta:
--
--   BONSUCESSO       04/09..11/09   9 contratos   ultimo: 11/09
--   COPACABANA NOVA  15/09..30/09  26 contratos   primeiro: 15/09
--
-- Zero BONSUCESSO em ou depois de 15/09; zero COPACABANA NOVA antes.
-- Forma identica a LIVIA (118): fronteira observada inequivoca. Como a
-- janela unica aberta carrega o mes inteiro em BONSUCESSO, hoje o
-- denominador esta numa loja e metade do numerador na outra.
--
-- Fronteira meio-aberta [inicio, fim): fechar BONSUCESSO em 2026-09-15
-- faz o ultimo dia coberto ser 14/09, e COPACABANA NOVA comeca em 15/09.
--
--
-- O QUE ESTA MIGRATION NAO FAZ
-- ----------------------------
-- 1. Nao toca em `consultores`. A foto e produto da carga de HC
--    (094/095); corrigir `loja_id` aqui seria desfeito na proxima carga.
--    O conserto duravel e no `HC_Colaboradores`.
-- 2. Nao decide o destino de VICTOR. O cadastro dele em HELP SAO JOAO DE
--    MERITI (criado 2026-09-23, zero producao la) pode ser transferencia
--    real sem producao ainda, ou ADE errada como na 121. Esta migration
--    afirma apenas o que a producao prova: em 03 e 04/09 ele estava em
--    COPACABANA NOVA. A 116 continua reportando-o, de proposito.
-- 3. Nao desbloqueia 09/2026 sozinha. Ver o fim do arquivo.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;


-- ===========================================
-- 1. Previsoes de transferencia desmentidas pela producao
-- ===========================================

DO $$
DECLARE
    r             RECORD;
    v_loja_prev   UUID;
    v_loja_real   UUID;
    v_janela_prev UUID;
    v_janela_real UUID;
    v_qtd         INTEGER;
BEGIN
    FOR r IN
        SELECT *
          FROM (VALUES
              ('CAMILLY DE OLIVEIRA LAURIA',
               'HELP COPACABANA',         'HELP LARANJEIRAS',     DATE '2026-09-01'),
              ('ANA CLARA SOUZA BRAYNER',
               'HELP SAO JOAO DE MERITI', 'HELP VILAR DOS TELES', DATE '2026-09-01'),
              ('VICTOR FELIPE TRAJANO COSTA',
               'HELP COPACABANA',         'HELP COPACABANA NOVA', DATE '2026-09-01')
          ) AS t(nome, loja_prevista, loja_real, corte)
    LOOP
        -- ---- 1.1 Resolucao das lojas ----
        SELECT count(*), (array_agg(l.id))[1]
          INTO v_qtd, v_loja_prev
          FROM public.lojas l
         WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
               = r.loja_prevista;

        IF v_qtd <> 1 THEN
            RAISE EXCEPTION
                'Migration 124: loja % ausente ou ambigua (% correspondencias)',
                r.loja_prevista, v_qtd;
        END IF;

        SELECT count(*), (array_agg(l.id))[1]
          INTO v_qtd, v_loja_real
          FROM public.lojas l
         WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
               = r.loja_real;

        IF v_qtd <> 1 THEN
            RAISE EXCEPTION
                'Migration 124: loja % ausente ou ambigua (% correspondencias)',
                r.loja_real, v_qtd;
        END IF;

        -- ---- 1.2 Pre-condicao: a previsao continua desmentida ----
        -- Se a producao passar a aparecer na loja prevista, a transferencia
        -- era real e esta migration nao pode mais afirmar o contrario.
        SELECT count(*)::integer
          INTO v_qtd
          FROM public.contratos ct
          JOIN public.consultores cs ON cs.id = ct.consultor_id
         WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g'))
               = r.nome
           AND ct.loja_id = v_loja_prev
           AND ct.data_cadastro >= r.corte;

        IF v_qtd <> 0 THEN
            RAISE EXCEPTION
                'Migration 124: % tem % contrato(s) em % a partir de % — a previsao da 087 deixou de ser falsa',
                r.nome, v_qtd, r.loja_prevista, r.corte;
        END IF;

        SELECT count(*)::integer
          INTO v_qtd
          FROM public.contratos ct
          JOIN public.consultores cs ON cs.id = ct.consultor_id
         WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g'))
               = r.nome
           AND ct.loja_id = v_loja_real
           AND ct.data_cadastro >= r.corte;

        IF v_qtd = 0 THEN
            RAISE EXCEPTION
                'Migration 124: % nao tem contrato em % a partir de % — sem producao, reabrir a janela seria outra inferencia',
                r.nome, r.loja_real, r.corte;
        END IF;

        -- ---- 1.3 A troca ----
        -- Idempotente: na reexecucao a linha prevista nao existe mais e o
        -- bloco inteiro e saltado; as pos-condicoes seguem valendo.
        SELECT count(*), (array_agg(v.id))[1]
          INTO v_qtd, v_janela_prev
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = r.nome
           AND v.loja_id          = v_loja_prev
           AND v.vigencia_inicio  = r.corte
           AND v.vigencia_fim IS NULL
           AND v.origem LIKE 'BACKFILL%';

        IF v_qtd > 1 THEN
            RAISE EXCEPTION
                'Migration 124: % janelas previstas de % em % (esperado 0 ou 1)',
                v_qtd, r.nome, r.loja_prevista;
        END IF;

        IF v_qtd = 1 THEN
            SELECT count(*), (array_agg(v.id))[1]
              INTO v_qtd, v_janela_real
              FROM public.consultor_vigencia v
             WHERE v.nome_normalizado = r.nome
               AND v.loja_id          = v_loja_real
               AND v.vigencia_fim     = r.corte;

            IF v_qtd <> 1 THEN
                RAISE EXCEPTION
                    'Migration 124: % janelas de % em % fechadas em % (esperado exatamente 1)',
                    v_qtd, r.nome, r.loja_real, r.corte;
            END IF;

            -- Ledger primeiro, como na 121: interrupcao no meio deixa a
            -- pessoa sem janela aberta (detectavel pela 116 em
            -- `sem_janela_aberta`) em vez de com duas.
            DELETE FROM public.consultor_vigencia WHERE id = v_janela_prev;

            UPDATE public.consultor_vigencia
               SET vigencia_fim = NULL,
                   origem       = 'MANUAL'
             WHERE id = v_janela_real;
        END IF;

        -- ---- 1.4 Pos-condicoes ----
        SELECT count(*)::integer
          INTO v_qtd
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = r.nome
           AND v.vigencia_fim IS NULL;

        IF v_qtd <> 1 THEN
            RAISE EXCEPTION
                'Migration 124: pos-condicao falhou — % tem % janelas abertas (esperado 1)',
                r.nome, v_qtd;
        END IF;

        SELECT count(*)::integer
          INTO v_qtd
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = r.nome
           AND v.vigencia_fim IS NULL
           AND v.loja_id = v_loja_real;

        IF v_qtd <> 1 THEN
            RAISE EXCEPTION
                'Migration 124: pos-condicao falhou — a janela aberta de % nao e %',
                r.nome, r.loja_real;
        END IF;

        -- Emenda sem vago nem sobreposicao na linha do tempo da pessoa.
        SELECT count(*)::integer
          INTO v_qtd
          FROM (
              SELECT v.vigencia_inicio,
                     lag(v.vigencia_fim) OVER (ORDER BY v.vigencia_inicio) AS fim_ant
                FROM public.consultor_vigencia v
               WHERE v.nome_normalizado = r.nome
          ) t
         WHERE t.fim_ant IS NOT NULL
           AND t.vigencia_inicio <> t.fim_ant;

        IF v_qtd <> 0 THEN
            RAISE EXCEPTION
                'Migration 124: pos-condicao falhou — % emenda(s) com vago ou sobreposicao em %',
                v_qtd, r.nome;
        END IF;
    END LOOP;
END
$$;


-- ===========================================
-- 2. GISELLE: BONSUCESSO -> COPACABANA NOVA em 15/09
-- ===========================================

DO $$
DECLARE
    v_bonsucesso UUID;
    v_copa_nova  UUID;
    v_janela     UUID;
    v_qtd        INTEGER;
    v_nome  CONSTANT TEXT := 'GISELLE GALVAO DE FARIAS';
    v_corte CONSTANT DATE := DATE '2026-09-15';
BEGIN
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_qtd, v_bonsucesso
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
           = 'HELP BONSUCESSO';

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 124: HELP BONSUCESSO ausente ou ambigua (% correspondencias)',
            v_qtd;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_qtd, v_copa_nova
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
           = 'HELP COPACABANA NOVA';

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 124: HELP COPACABANA NOVA ausente ou ambigua (% correspondencias)',
            v_qtd;
    END IF;

    -- ---- Pre-condicao: a fronteira de 15/09 continua limpa ----
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_bonsucesso
       AND ct.data_cadastro >= v_corte;

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION
            'Migration 124: % contrato(s) de Giselle em BONSUCESSO a partir de 15/09 — a fronteira nao e mais limpa',
            v_qtd;
    END IF;

    SELECT count(*)::integer
      INTO v_qtd
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_copa_nova
       AND ct.data_cadastro < v_corte;

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION
            'Migration 124: % contrato(s) de Giselle em COPACABANA NOVA antes de 15/09 — a fronteira nao e mais limpa',
            v_qtd;
    END IF;

    -- ---- Fecha BONSUCESSO ----
    SELECT count(*), (array_agg(v.id))[1]
      INTO v_qtd, v_janela
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_bonsucesso
       AND v.vigencia_fim IS NULL;

    IF v_qtd > 1 THEN
        RAISE EXCEPTION
            'Migration 124: % janelas abertas de Giselle em Bonsucesso (esperado 0 ou 1)',
            v_qtd;
    END IF;

    IF v_qtd = 1 THEN
        SELECT count(*)::integer
          INTO v_qtd
          FROM public.consultor_vigencia v
         WHERE v.id = v_janela
           AND v.vigencia_inicio >= v_corte;

        IF v_qtd <> 0 THEN
            RAISE EXCEPTION
                'Migration 124: a janela de Giselle em Bonsucesso comeca em ou depois de 15/09 — fechar violaria chk_cv_vigencia_ordem';
        END IF;

        UPDATE public.consultor_vigencia
           SET vigencia_fim = v_corte,
               origem       = 'MANUAL'
         WHERE id = v_janela;
    END IF;

    -- ---- Abre COPACABANA NOVA ----
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_copa_nova;

    IF v_qtd = 0 THEN
        INSERT INTO public.consultor_vigencia
            (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
        VALUES
            (v_nome, v_copa_nova, v_corte, NULL, 'MANUAL');
    ELSIF v_qtd > 1 THEN
        RAISE EXCEPTION
            'Migration 124: % janelas de Giselle em Copacabana Nova (esperado 0 ou 1)',
            v_qtd;
    END IF;

    -- ---- Pos-condicoes ----
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_fim IS NULL
       AND v.loja_id = v_copa_nova
       AND v.vigencia_inicio = v_corte;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 124: pos-condicao falhou — a janela aberta de Giselle nao e COPACABANA NOVA desde 15/09';
    END IF;

    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_fim IS NULL;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 124: pos-condicao falhou — Giselle tem % janelas abertas (esperado 1)',
            v_qtd;
    END IF;

    SELECT count(*)::integer
      INTO v_qtd
      FROM (
          SELECT v.vigencia_inicio,
                 lag(v.vigencia_fim) OVER (ORDER BY v.vigencia_inicio) AS fim_ant
            FROM public.consultor_vigencia v
           WHERE v.nome_normalizado = v_nome
      ) t
     WHERE t.fim_ant IS NOT NULL
       AND t.vigencia_inicio <> t.fim_ant;

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION
            'Migration 124: pos-condicao falhou — % emenda(s) com vago ou sobreposicao em Giselle',
            v_qtd;
    END IF;
END
$$;


-- ===========================================
-- 3. Pos-condicao conjunta: producao coberta pelo ledger
--
-- O invariante que esta migration existe para restaurar, afirmado sobre
-- CONTRATOS e nao sobre pagamento: para as quatro pessoas, todo contrato
-- digitado a partir de 01/08/2026 cai numa vigencia dela na loja do
-- contrato. Independe de status de pagamento, logo nao fica falso na
-- proxima importacao.
-- ===========================================

DO $$
DECLARE
    v_furos TEXT;
BEGIN
    SELECT string_agg(
               format('%s em %s dia %s', t.nome, t.loja, t.data_cadastro),
               '; ' ORDER BY t.nome, t.data_cadastro)
      INTO v_furos
      FROM (
          SELECT upper(regexp_replace(btrim(cs.nome),
                       '[[:space:]]+', ' ', 'g')) AS nome,
                 l.nome                           AS loja,
                 ct.data_cadastro::date           AS data_cadastro
            FROM public.contratos ct
            JOIN public.consultores cs ON cs.id = ct.consultor_id
            LEFT JOIN public.lojas l   ON l.id  = ct.loja_id
           WHERE upper(regexp_replace(btrim(cs.nome),
                       '[[:space:]]+', ' ', 'g')) IN (
                     'CAMILLY DE OLIVEIRA LAURIA',
                     'ANA CLARA SOUZA BRAYNER',
                     'VICTOR FELIPE TRAJANO COSTA',
                     'GISELLE GALVAO DE FARIAS')
             AND ct.data_cadastro >= DATE '2026-08-01'
             AND NOT EXISTS (
                 SELECT 1
                   FROM public.consultor_vigencia v
                  WHERE v.nome_normalizado = upper(regexp_replace(
                            btrim(cs.nome), '[[:space:]]+', ' ', 'g'))
                    AND v.loja_id = ct.loja_id
                    AND ct.data_cadastro >= v.vigencia_inicio
                    AND (v.vigencia_fim IS NULL
                         OR ct.data_cadastro < v.vigencia_fim)
             )
      ) t;

    IF v_furos IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 124: pos-condicao falhou — producao sem vigencia na loja: %',
            v_furos;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) As quatro linhas do tempo:
--
--    SELECT v.nome_normalizado, l.nome, v.vigencia_inicio, v.vigencia_fim,
--           v.origem
--      FROM consultor_vigencia v
--      LEFT JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado IN ('CAMILLY DE OLIVEIRA LAURIA',
--                                  'ANA CLARA SOUZA BRAYNER',
--                                  'VICTOR FELIPE TRAJANO COSTA',
--                                  'GISELLE GALVAO DE FARIAS')
--     ORDER BY v.nome_normalizado, v.vigencia_inicio;
--
--    -- esperado:
--    --  ANA CLARA  S.J. DE MERITI   2026-03-10  2026-07-20  BACKFILL_PRODUCAO
--    --  ANA CLARA  VILAR DOS TELES  2026-07-20  NULL        MANUAL
--    --  CAMILLY    COPACABANA       2025-05-01  2026-08-04  BACKFILL_CENSURADO
--    --  CAMILLY    LARANJEIRAS      2026-08-04  NULL        MANUAL
--    --  GISELLE    BONSUCESSO       2026-09-04  2026-09-15  MANUAL
--    --  GISELLE    COPACABANA NOVA  2026-09-15  NULL        MANUAL
--    --  VICTOR     LARANJEIRAS      2025-08-21  2026-08-04  BACKFILL_PRODUCAO
--    --  VICTOR     COPACABANA NOVA  2026-08-04  NULL        MANUAL
--
-- 2) A guarda de origem CAI 144 eventos, mas NAO chega a zero:
--
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(9, 2026);
--    -- 164 antes; 20 depois desta migration;
--    --  3 depois de aplicada tambem a 106 (os 17 de Iluara saem da
--    --    contagem porque Patricia e supervisora e supervisor nao entra
--    --    em `eventos_pagos`).
--
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(8, 2026);
--    -- 17 antes; 0 depois da 106. Agosto depende SO dela.
--
--    Comparar antes/depois em vez de assumir: o contador agrega causas e
--    qualquer importacao nova pode somar evento.
--
-- 3) O detector passa a reportar CAMILLY e ANA CLARA — e isso e o ponto:
--
--    SELECT jsonb_array_length(fn_diag_vinculo_divergente()->'divergencias');
--    -- 3 antes (GISELLE, MARIANA DE OLIVEIRA, VICTOR); 4 depois.
--    -- GISELLE SAI: foto e ledger passam a concordar em COPACABANA NOVA.
--    -- CAMILLY e ANA CLARA ENTRAM, e VICTOR permanece — as tres fotos que
--    -- a carga de HC de 11/08 deixou velhas. Virou pergunta aberta no
--    -- detector em vez de erro silencioso no denominador.
--
-- 4) Rematerializar — nesta ordem, e so quando a contagem estiver em 0:
--
--    SELECT fn_materializar_caderno(8, 2026);
--    SELECT fn_materializar_caderno(9, 2026);
--
--
-- =====================================================
-- O QUE CONTINUA BLOQUEANDO 09/2026 (3 eventos, de proposito)
-- =====================================================
--
-- Nenhum destes tem evidencia unilateral: a forma dos dados nao separa
-- "ADE errada" de "pessoa que voltou", e quem decide e a operacao (mesma
-- doutrina de 109/118/121). Cada um precisa da sua propria migration.
--
--   CASSIANE COELHO DE OLIVEIRA   1 evento   R$ 1.956,89   cadastro 24/09
--     Cadastro criado em 25/09 em HELP SAO JOAO DE MERITI, nenhuma janela
--     no ledger. A 116 ja a acusa em `sem_janela_aberta`. Falta a DATA DE
--     ADMISSAO para abrir a janela MANUAL (<= 24/09). Admissao de
--     setembro que a 119 nao pegou.
--
--   MARCELA DOS SANTOS SILVA      1 evento   R$   763,32   cadastro 21/09
--     `Desligado (a)`, janela em HELP MEIER fechada em 2026-01-01, e um
--     contrato pago digitado em 21/09 na mesma loja. Ou e ADE errada
--     (mecanica da 121) ou e retorno nao registrado. Veredito da operacao.
--
--   MIZAEL BARBOSA NETO           1 evento   R$   371,44   cadastro 08/09
--     Desligado, sem janela aberta (a ultima fecha em 10/09). O contrato
--     de 08/09 e em HELP LARANJEIRAS, mas a 111 o poe em HELP RIO
--     COMPRIDO desde 04/09. Conferir a data do retorno: a 111 pode ter
--     antecipado em quatro dias uma volta que so aconteceu depois.
--
--
-- =====================================================
-- FOLLOW-UPS QUE NAO SAO DESTA MIGRATION
-- =====================================================
--
-- [ ] A FOTO DE CAMILLY, ANA CLARA E VICTOR CONTINUA VELHA. Enquanto o
--     `HC_Colaboradores` trouxer a loja antiga, (a) o dashboard mostra a
--     pessoa na loja errada e (b) qualquer rebuild do backfill recria a
--     previsao de transferencia — agora com a janela certa como MANUAL,
--     o que faria o rebuild colidir com `uq_cv_consultor_loja_aberta` em
--     vez de sobrescrever em silencio. Corrigir na origem.
--
-- [ ] A CTE `transferidos` DA 087 ESCREVE INFERENCIA COM CARA DE FATO.
--     Ela e a unica parte do backfill que afirma presenca sem um unico
--     contrato que a sustente, e das 7 previsoes de 01/09 tres estavam
--     erradas. Avaliar se o lugar dela e o ledger ou o detector da 116.
--
-- [ ] A 116 NAO VE ERRO QUE O LEDGER HERDOU DA FOTO. Vale uma sexta
--     checagem: janela aberta cuja loja nao tem producao da pessoa na
--     competencia corrente, havendo producao em outra loja. Era o unico
--     sinal que teria pegado CAMILLY e ANA CLARA antes do bloqueio.
