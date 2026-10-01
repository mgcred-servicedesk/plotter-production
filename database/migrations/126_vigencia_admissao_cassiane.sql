-- =====================================================
-- Migracao 126: admissao declarada de CASSIANE COELHO DE OLIVEIRA
-- Data: 2026-10-01
-- Depende de: 086/087 (consultor_vigencia), 105 (guarda de origem),
--             119 (as cinco admissoes de setembro — mesma forma)
--
-- Fato confirmado pela operacao (2026-10-01):
--   * CASSIANE COELHO DE OLIVEIRA entrou em 15/09/2026, em
--     HELP SAO JOAO DE MERITI.
--
-- ULTIMO dos 164 eventos que bloquearam 09/2026. Depois desta migration a
-- guarda de origem vai a ZERO e as duas competencias podem ser
-- rematerializadas.
--
--
-- COMO O CASO APARECEU
-- --------------------
-- Pelo detector `fn_diag_vinculo_divergente` (116), lista
-- `sem_janela_aberta` — e pela guarda da 105 ao mesmo tempo, com 1 evento
-- pago de R$ 1.956,89 (ADE 103939116, BMG/INSS, Contrato Novo).
--
-- Ela nao tem janela NENHUMA em `consultor_vigencia`, nem aberta nem
-- fechada. O cadastro foi criado pelo proprio ETL de contratos em
-- 2026-09-25 14:26:04 — TRES SEGUNDOS antes de a linha do contrato ser
-- gravada (14:26:07). E a sexta aparicao da mecanica de
-- `uq_consultores_nome_loja`: par (nome, loja) inedito INSERE cadastro em
-- vez de reconhecer a pessoa, e quando o par e inedito porque a pessoa e
-- nova de verdade, o cadastro nasce certo e sem janela.
--
-- O diagnostico da 119 vale literalmente aqui: `fn_headcount_ponderado`
-- (091) le so os ledgers, entao sem janela ela pesa ZERO no denominador
-- enquanto a producao dela segue no numerador — a media da loja SOBE por
-- gente que existe, trabalha e nao e contada.
--
--
-- DECLARADO VENCE INFERIDO — 7 DIAS UTEIS DE DIFERENCA
-- ----------------------------------------------------
-- O fallback documentado (R1 da 087) e a data do PRIMEIRO CONTRATO. Aqui
-- a diferenca e grande, porque ela levou nove dias para digitar a
-- primeira venda:
--
--   admissao declarada   15/09   ->  12 dos 21 DU de 09/2026
--   1o contrato          24/09   ->   5 dos 21 DU
--   perdidos pelo fallback                7 DU
--
-- E a "admissao censurada" da 087 ao vivo: pessoa contratada, em
-- treinamento ou rampa, que so apareceria no ledger quando vendesse. Por
-- isso entra a data declarada.
--
-- Medido: ela nao tem NENHUM contrato antes de 15/09 (tem um so, de
-- 24/09), entao a data declarada nao desmente a producao em ponto algum.
--
--
-- EFEITO NUMERICO EM 09/2026 — LER ANTES DE APLICAR
-- -------------------------------------------------
-- Setembro tem 21 dias uteis (30 dias, 22 de semana, menos 07/09).
-- `origem = 'MANUAL'` conta como reducao DECLARADA na 091, entao o peso e
-- fracao pura, sem o piso de 50% que pegaria uma origem inferida:
--
--   HELP SAO JOAO DE MERITI   peso    2,0000 -> 2,5714   (+0,5714 = 12/21)
--                             cabecas      2 -> 3
--
-- O numerador da loja NAO muda — ela ja produzia e a producao dela ja
-- estava contada. Logo a queda da produtividade por dia-cabeca e exata e
-- independente de escopo: 2,0000 / 2,5714 = 0,7778, ou seja **-22,2%**.
-- Com o fallback de 24/09 a queda seria de so -10,6%, e seria errada.
--
-- 08/2026 NAO E TOCADA: a janela comeca em 15/09 e nao alcanca agosto.
-- Uma pos-condicao verifica isso, porque agosto acabou de voltar a zero
-- com a 106 e nao pode ser mexido de novo sem intencao.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_sjm   UUID;
    v_qtd   INTEGER;
    v_nome      CONSTANT TEXT := 'CASSIANE COELHO DE OLIVEIRA';
    v_admissao  CONSTANT DATE := DATE '2026-09-15';
BEGIN
    -- ---- 1. Loja ----
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_qtd, v_sjm
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
           = 'HELP SAO JOAO DE MERITI';

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 126: HELP SAO JOAO DE MERITI ausente ou ambigua (% correspondencias)',
            v_qtd;
    END IF;

    -- ---- 2. O cadastro dela existe, e e um so ----
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND c.loja_id = v_sjm;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 126: cadastro de Cassiane em Sao Joao de Meriti ausente ou ambiguo (% correspondencias)',
            v_qtd;
    END IF;

    -- ---- 3. Ela e consultora, nao supervisora ----
    -- Supervisor tem ledger proprio (076/082/113) e fica fora da
    -- populacao de produtividade; abrir janela de consultor seria errado.
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.supervisor_vigencia s
     WHERE s.nome_normalizado = v_nome;

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION
            'Migration 126: Cassiane tem % vigencia(s) de supervisao — o papel precisa ser decidido antes',
            v_qtd;
    END IF;

    -- ---- 4. A data declarada nao desmente a producao ----
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.data_cadastro < v_admissao;

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION
            'Migration 126: Cassiane tem % contrato(s) ANTES de % — a data declarada contradiz a producao',
            v_qtd, v_admissao;
    END IF;

    -- ---- 5. Abre a janela ----
    -- `uq_cv_consultor_loja_aberta` ja garante no maximo uma aberta por
    -- (pessoa, loja); o IF torna a reexecucao um no-op em vez de erro.
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome;

    IF v_qtd = 0 THEN
        INSERT INTO public.consultor_vigencia
            (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
        VALUES
            (v_nome, v_sjm, v_admissao, NULL, 'MANUAL');
    ELSIF v_qtd > 1 THEN
        RAISE EXCEPTION
            'Migration 126: Cassiane tem % janelas no ledger (esperado 0 antes, 1 depois)',
            v_qtd;
    END IF;

    -- ---- 6. Pos-condicoes ----
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado  = v_nome
       AND v.loja_id           = v_sjm
       AND v.vigencia_inicio   = v_admissao
       AND v.vigencia_fim IS NULL
       AND v.origem            = 'MANUAL';

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 126: pos-condicao falhou — a janela de Cassiane nao e SJM aberta desde %',
            v_admissao;
    END IF;

    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 126: pos-condicao falhou — % janelas de Cassiane (esperado exatamente 1)',
            v_qtd;
    END IF;

    -- 08/2026 intacta: nada dela alcanca agosto.
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_inicio < DATE '2026-09-01';

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION
            'Migration 126: pos-condicao falhou — janela de Cassiane alcanca 08/2026';
    END IF;

    -- Toda producao dela cai dentro da janela, na loja do contrato.
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND NOT EXISTS (
           SELECT 1
             FROM public.consultor_vigencia v
            WHERE v.nome_normalizado = v_nome
              AND v.loja_id = ct.loja_id
              AND ct.data_cadastro >= v.vigencia_inicio
              AND (v.vigencia_fim IS NULL
                   OR ct.data_cadastro < v.vigencia_fim)
       );

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION
            'Migration 126: pos-condicao falhou — % contrato(s) de Cassiane sem vigencia na loja',
            v_qtd;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) A janela dela:
--
--    SELECT l.nome, v.vigencia_inicio, v.vigencia_fim, v.origem
--      FROM consultor_vigencia v
--      JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado = 'CASSIANE COELHO DE OLIVEIRA';
--
--    -- esperado: HELP SAO JOAO DE MERITI  2026-09-15  NULL  MANUAL
--
-- 2) O detector para de acusa-la:
--
--    SELECT jsonb_array_length(
--        fn_diag_vinculo_divergente() -> 'sem_janela_aberta');
--    -- esperado: 0 (ela era a unica)
--
-- 3) A GUARDA DE ORIGEM CHEGA A ZERO NAS DUAS COMPETENCIAS:
--
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(8, 2026);  -- 0
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(9, 2026);  -- 1 -> 0
--
-- 4) O denominador da loja:
--
--    SELECT loja, peso, cabecas, du_competencia
--      FROM fn_headcount_ponderado(9, 2026)
--     WHERE loja = 'HELP SAO JOAO DE MERITI';
--
--    -- esperado: peso 2,5714 / cabecas 3 / DU 21
--    -- (era 2,0000 / 2 / 21 em 2026-10-01)
--
-- 5) Rematerializar, nesta ordem:
--
--    SELECT fn_materializar_caderno(8, 2026);
--    SELECT fn_materializar_caderno(9, 2026);
--
--    Conferir loja a loja antes de republicar: alem desta loja, a 124
--    mexeu em LARANJEIRAS, VILAR DOS TELES, COPACABANA, COPACABANA NOVA,
--    S.J. DE MERITI e BONSUCESSO, e a 125 em MEIER, LARANJEIRAS e RIO
--    COMPRIDO. Agosto tambem muda: a 106 move 17 contratos de Iluara para
--    Patricia em CASCADURA, e o snapshot publicado e de 02/09, anterior as
--    8 janelas fechadas na carga de HC de 23/09.
--
--
-- =====================================================
-- FOLLOW-UP
-- =====================================================
--
-- [ ] A PORTA CERTA PARA ISSO NUNCA FOI USADA. `acao_adm =
--     'criar_janela'` na `fn_headcount_replace` (095) existe exatamente
--     para admissao, e esta e a SEGUNDA vez que uma migration manual faz
--     o servico dela (a 119 foi a primeira, com cinco pessoas). Enquanto
--     o `HC_Colaboradores` nao for importado, toda admissao vai aparecer
--     primeiro como bloqueio de fechamento ou como linha em
--     `sem_janela_aberta` — depois do fato, nunca antes.
--     Nota: a planilha em `configuracao/HC_Colaboradores.xlsx` nao tem
--     coluna de data de admissao; a porta da 095 precisa dela.
