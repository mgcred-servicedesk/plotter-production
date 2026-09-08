-- =====================================================
-- Migracao 111: retorno de MIZAEL a HELP RIO COMPRIDO
-- Data: 2026-09-08
-- Depende de: 103 (cobertura temporaria de 11/08 a 24/08)
--
-- Fato confirmado pela operacao:
--   * MIZAEL BARBOSA NETO volta a produzir para HELP RIO COMPRIDO
--     a partir de 04/09/2026.
--
-- Terceiro capitulo da mesma pessoa. A 103 registrou a cobertura
-- temporaria (11/08 a 24/08) e o retorno a HELP LARANJEIRAS em 25/08;
-- esta migration fecha essa janela e abre a nova em RIO COMPRIDO.
--
--
-- POR QUE A FOTO JA DIZIA RIO COMPRIDO — E POR QUE ISSO NAO E PROVA
-- ------------------------------------------------------------------
-- `consultores` tem duas linhas dele, e a de RIO COMPRIDO (updated_at
-- 2026-08-13) vence o dedup por `updated_at` desde a cobertura de
-- agosto. Ou seja: a foto vinha apontando RIO COMPRIDO havia tres
-- semanas enquanto o ledger — corretamente — dizia LARANJEIRAS, porque
-- o ETL criou o cadastro durante a cobertura e nunca o moveu de volta.
--
-- A partir de 04/09 os dois passam a concordar, mas por coincidencia,
-- nao porque algo tenha sido corrigido: o cadastro de RIO COMPRIDO
-- continua sendo o mesmo residuo de 13/08. Registrado aqui para que a
-- concordancia futura nao seja lida como evidencia.
--
--
-- SEGUNDA JANELA NA MESMA LOJA — E ESPERADO
-- ------------------------------------------
-- Ele ja tem uma janela FECHADA em RIO COMPRIDO (11/08 a 25/08). Esta
-- migration cria a SEGUNDA. Isso e suportado de proposito:
--
--   * `uq_cv_consultor_loja_aberta` e parcial (WHERE vigencia_fim IS
--     NULL), entao so proibe duas ABERTAS na mesma loja — a antiga esta
--     fechada;
--   * `_fetch_vinculos_consultores` agrupa por (pessoa, loja) e SOMA os
--     dias, e a docstring dele ja prevê o caso: "Duas janelas da mesma
--     pessoa na mesma loja (ex.: correcao manual partindo o periodo)
--     somam os dias — sem sobreposicao, garantida pelo ledger."
--
--
-- FRONTEIRA
-- ---------
-- Corte em 2026-09-04, janela meio-aberta [inicio, fim): o ultimo dia
-- dele em LARANJEIRAS e 03/09, e RIO COMPRIDO comeca em 04/09. Bate com
-- a producao — os ultimos contratos em LARANJEIRAS sao de 02/09 e
-- 03/09, e nao ha nenhum em RIO COMPRIDO em setembro.
--
-- ATENCAO: a data e DECLARADA, nao inferida. Em 04/09 ele ainda nao tem
-- nenhum contrato em RIO COMPRIDO — a migration nao exige que tenha, e
-- NAO deve exigir: e o mesmo criterio das 106/107/109 (declarado vence
-- inferido). Se esperassemos o primeiro contrato, o inicio sairia
-- errado sempre que a pessoa levasse dias para digitar.
--
-- origem = 'MANUAL' nas duas linhas, como na 103: imuniza contra o
-- rebuild do backfill, que apaga so `origem LIKE 'BACKFILL%'`.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_laranjeiras_id UUID;
    v_rio_id         UUID;
    v_janela_id      UUID;
    v_quantidade     INTEGER;
    v_conflito       INTEGER;
    v_nome  CONSTANT TEXT := 'MIZAEL BARBOSA NETO';
    v_corte CONSTANT DATE := DATE '2026-09-04';
BEGIN
    -- ---- 1. Resolucao das lojas ----
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_laranjeiras_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP LARANJEIRAS';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 111: HELP LARANJEIRAS ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_rio_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP RIO COMPRIDO';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 111: HELP RIO COMPRIDO ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    -- ---- 2. Pre-condicao: nada em LARANJEIRAS a partir do corte ----
    -- O inverso NAO e checado: em 04/09 ele ainda nao produziu em RIO
    -- COMPRIDO, e exigir isso contradiria "declarado vence inferido".
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_laranjeiras_id
       AND ct.data_cadastro >= v_corte;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 111: % contrato(s) em LARANJEIRAS a partir de 04/09/2026 — a fronteira nao e limpa',
            v_quantidade;
    END IF;

    -- ---- 3. Fecha a janela aberta de LARANJEIRAS ----
    SELECT count(*), (array_agg(v.id))[1]
      INTO v_quantidade, v_janela_id
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_laranjeiras_id
       AND v.vigencia_fim IS NULL;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 111: % janelas abertas de Mizael em Laranjeiras (esperado 0 ou 1)',
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
                'Migration 111: janela de Laranjeiras comeca em ou depois de 04/09/2026 — fechar violaria chk_cv_vigencia_ordem';
        END IF;

        UPDATE public.consultor_vigencia v
           SET vigencia_fim = v_corte,
               origem       = 'MANUAL'
         WHERE v.id = v_janela_id;
    END IF;

    -- ---- 4. Abre a SEGUNDA janela de RIO COMPRIDO ----
    -- Conta so as abertas: a de 11/08-25/08 esta fechada e deve
    -- permanecer.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_rio_id
       AND v.vigencia_fim IS NULL;

    IF v_quantidade = 0 THEN
        INSERT INTO public.consultor_vigencia
            (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
        VALUES
            (v_nome, v_rio_id, v_corte, NULL, 'MANUAL');
    ELSIF v_quantidade = 1 THEN
        -- Reexecucao: so aceita se for exatamente a janela desta migration.
        SELECT count(*)::integer
          INTO v_conflito
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = v_nome
           AND v.loja_id = v_rio_id
           AND v.vigencia_fim IS NULL
           AND v.vigencia_inicio = v_corte;

        IF v_conflito <> 1 THEN
            RAISE EXCEPTION
                'Migration 111: ja existe janela aberta de Mizael em Rio Comprido com inicio diferente de 04/09/2026';
        END IF;
    END IF;

    -- ---- 5. Pos-condicoes ----
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_fim IS NULL;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 111: pos-condicao falhou — % janelas abertas (esperado 1)',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_fim IS NULL
       AND v.loja_id = v_rio_id
       AND v.vigencia_inicio = v_corte;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 111: pos-condicao falhou — a janela aberta nao e RIO COMPRIDO desde 04/09/2026';
    END IF;

    -- A linha do tempo dele tem 4 segmentos e nenhuma emenda com vago
    -- ou sobreposicao.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome;

    IF v_quantidade <> 4 THEN
        RAISE EXCEPTION
            'Migration 111: pos-condicao falhou — % segmentos na linha do tempo de Mizael (esperado 4)',
            v_quantidade;
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
            'Migration 111: pos-condicao falhou — % emenda(s) com vago ou sobreposicao na linha do tempo de Mizael',
            v_quantidade;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
--    SELECT l.nome, v.vigencia_inicio, v.vigencia_fim, v.origem
--      FROM consultor_vigencia v
--      JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado = 'MIZAEL BARBOSA NETO'
--     ORDER BY v.vigencia_inicio;
--
--    -- esperado (4 linhas, todas MANUAL):
--    --   HELP LARANJEIRAS    2026-06-26   2026-08-11
--    --   HELP RIO COMPRIDO   2026-08-11   2026-08-25
--    --   HELP LARANJEIRAS    2026-08-25   2026-09-04
--    --   HELP RIO COMPRIDO   2026-09-04   NULL
--
-- Em 09/2026 os dias uteis dele ficam repartidos entre as duas lojas
-- (R3): 01/09 a 03/09 em LARANJEIRAS, 04/09 em diante em RIO COMPRIDO.
-- A soma continua devolvendo UMA pessoa.
