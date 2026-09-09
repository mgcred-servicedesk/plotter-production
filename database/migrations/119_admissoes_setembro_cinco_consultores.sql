-- =====================================================
-- Migracao 119: admissoes declaradas de cinco consultores
-- Data: 2026-09-09
-- Depende de: 086/087 (consultor_vigencia)
--
-- Fatos confirmados pela operacao (2026-09-09):
--
--   BRUNO VINICIUS MARTINS DA SILVA        HELP PRACA SECA        25/08/2026
--   STEPHANIA LANA LOPES                   HELP NOVA IGUACU       20/08/2026
--   MARIA LUISA DE MORAIS BRANDAO          HELP MADUREIRA         25/08/2026
--   GISELLE GALVAO DE FARIAS               HELP BONSUCESSO        04/09/2026
--   MATHEUS DUTRA DOS SANTOS DE OLIVEIRA   HELP CAXIAS GUANABARA  04/09/2026
--
--
-- COMO O CASO APARECEU, E POR QUE E URGENTE
-- ------------------------------------------
-- Pelo detector `fn_diag_vinculo_divergente` (116), lista
-- `sem_janela_aberta`. As cinco pessoas nao tem janela NENHUMA em
-- `consultor_vigencia` — nem aberta nem fechada. Os cadastros foram
-- criados pelo ETL de contratos em 08 e 09/09, ao gravar a primeira
-- producao delas.
--
-- `fn_headcount_ponderado` (091) le SO os ledgers. Sem janela, a pessoa
-- pesa ZERO no denominador — mas a producao dela continua no numerador,
-- porque o numerador sai de `contratos`. O efeito e a media da loja SUBIR
-- por gente que existe, trabalha e nao e contada. E o espelho exato da
-- patologia que a 086 corrigiu do outro lado.
--
-- O caminho normal para isso e `acao_adm = 'criar_janela'` na
-- `fn_headcount_replace` (095). Ele nunca rodou: o `HC_Colaboradores`
-- jamais foi importado — em 2026-09-08 `consultor_vigencia` tinha ZERO
-- linhas `origem = 'ETL'`, e essa e a unica porta que as escreve.
--
--
-- DECLARADO VENCE INFERIDO — E AQUI A DIFERENCA E MENSURAVEL
-- -----------------------------------------------------------
-- O fallback documentado para admissao e a data do PRIMEIRO CONTRATO. Se
-- fosse usado aqui, tres das cinco perderiam o periodo entre a admissao
-- real e a primeira venda:
--
--   pessoa       admissao    1o contrato   dias perdidos pelo fallback
--   STEPHANIA    20/08       04/09         8 dias uteis de 08/2026
--   BRUNO        25/08       04/09         5 dias uteis de 08/2026
--   MARIA LUISA  25/08       08/09         5 dias uteis de 08/2026
--   GISELLE      04/09       04/09         nenhum
--   MATHEUS      04/09       04/09         nenhum
--
-- Isto e a "admissao censurada" da 087 acontecendo ao vivo: pessoa
-- contratada, em treinamento ou rampa, que so aparece no ledger quando
-- vende. Por isso as datas declaradas entram, e nao a inferencia.
--
-- Nenhuma das cinco tem contrato ANTES da propria data declarada
-- (medido: zero para as cinco), entao nao ha `divergencia_producao` — a
-- planilha nao esta desmentindo a producao em caso nenhum.
--
--
-- EFEITO NUMERICO — LER ANTES DE APLICAR
-- ---------------------------------------
-- Medido em 2026-09-09. Agosto e setembro tem 21 dias uteis cada.
--
--   08/2026 (competencia JA PUBLICADA — o denominador CRESCE e a
--            produtividade dessas tres lojas CAI):
--     HELP NOVA IGUACU        +0,3810   (STEPHANIA, 8 DU)
--     HELP PRACA SECA         +0,2381   (BRUNO, 5 DU)
--     HELP MADUREIRA          +0,2381   (MARIA LUISA, 5 DU)
--     total                   +0,8571
--
--   As tres entram em agosto com producao ZERO no mes — nenhuma vendeu
--   antes de 04/09. Peso sem numerador e o efeito correto: elas estavam
--   contratadas e sendo pagas. Mas e uma mudanca visivel num mes fechado,
--   e nao adianta descobrir isso depois de publicar.
--
--   09/2026:
--     HELP PRACA SECA         +1,0000   (BRUNO)
--     HELP NOVA IGUACU        +1,0000   (STEPHANIA)
--     HELP MADUREIRA          +1,0000   (MARIA LUISA)
--     HELP BONSUCESSO         +0,8571   (GISELLE, 18 DU)
--     HELP CAXIAS GUANABARA   +0,8571   (MATHEUS, 18 DU)
--     total                   +4,7143
--
-- Rematerializar o Caderno de 08/2026 E de 09/2026 depois de aplicar.
--
--
-- POR QUE 'MANUAL' E NAO 'ETL'
-- -----------------------------
-- As datas vieram da operacao, a mao, pelo mesmo canal das 109-112 e da
-- 118 — nao de carga de arquivo. 'MANUAL' descreve a procedencia com
-- honestidade e, alem disso, PROTEGE: se um dia o `HC_Colaboradores`
-- subir com data diferente para uma destas pessoas, a 095 classifica
-- `divergencia_manual` e REPORTA em vez de sobrescrever. Com 'ETL' a
-- classificacao seria `aplicar` e a data declarada pela operacao seria
-- trocada em silencio.
--
-- Detalhe conhecido e inofensivo: se o HC trouxer a MESMA data, a 095 cai
-- em `aplicar` (a clausula `sem_efeito` exige origem = 'ETL') e reescreve
-- a linha com o mesmo `vigencia_inicio`, mudando so a procedencia para
-- 'ETL'. Nenhum numero muda.
--
--
-- ESTRUTURA
-- ---------
-- Loop sobre uma lista de VALUES em vez de cinco blocos iguais: cinco
-- copias do mesmo codigo sao cinco lugares para um nome ou uma data
-- divergirem. As guardas rodam por pessoa e qualquer falha aborta a
-- transacao inteira — as cinco entram juntas ou nenhuma entra.
--
-- Executar no Supabase SQL Editor. Independente das 113-118.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_row        record;
    v_loja_id    UUID;
    v_quantidade INTEGER;
    v_inseridas  INTEGER := 0;
    v_ja_tinham  INTEGER := 0;
BEGIN
    FOR v_row IN
        SELECT *
        FROM (VALUES
            ('BRUNO VINICIUS MARTINS DA SILVA',      'HELP PRACA SECA',       DATE '2026-08-25'),
            ('STEPHANIA LANA LOPES',                 'HELP NOVA IGUACU',      DATE '2026-08-20'),
            ('MARIA LUISA DE MORAIS BRANDAO',        'HELP MADUREIRA',        DATE '2026-08-25'),
            ('GISELLE GALVAO DE FARIAS',             'HELP BONSUCESSO',       DATE '2026-09-04'),
            ('MATHEUS DUTRA DOS SANTOS DE OLIVEIRA', 'HELP CAXIAS GUANABARA', DATE '2026-09-04')
        ) AS t(nome, loja, adm)
    LOOP
        -- ---- 1. Loja resolve sem ambiguidade ----
        SELECT count(*), (array_agg(l.id))[1]
          INTO v_quantidade, v_loja_id
          FROM public.lojas l
         WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
               = v_row.loja;

        IF v_quantidade <> 1 THEN
            RAISE EXCEPTION
                'Migration 119: loja % ausente ou ambigua (% correspondencias) — pessoa %',
                v_row.loja, v_quantidade, v_row.nome;
        END IF;

        -- ---- 2. A pessoa existe, e o cadastro dela e desta loja ----
        -- Um cadastro so, na loja declarada. Se houver dois, a pessoa tem
        -- historico de loja que esta migration nao modela — a janela
        -- unica que ela abre seria a fronteira errada.
        SELECT count(*)::integer
          INTO v_quantidade
          FROM public.consultores c
         WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g'))
               = v_row.nome;

        IF v_quantidade <> 1 THEN
            RAISE EXCEPTION
                'Migration 119: % tem % cadastro(s) em `consultores` (esperado exatamente 1)',
                v_row.nome, v_quantidade;
        END IF;

        SELECT count(*)::integer
          INTO v_quantidade
          FROM public.consultores c
         WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g'))
               = v_row.nome
           AND c.loja_id = v_loja_id;

        IF v_quantidade <> 1 THEN
            RAISE EXCEPTION
                'Migration 119: o cadastro de % nao esta em % — a loja declarada nao bate com a do cadastro',
                v_row.nome, v_row.loja;
        END IF;

        -- ---- 3. Producao nao desmente a admissao declarada ----
        -- Contrato digitado ANTES da data declarada significa que a
        -- pessoa ja estava presente: a data esta errada, ou a producao
        -- foi atribuida a ela indevidamente (foi o caso da ILUARA, 106).
        -- Medido zero para as cinco em 2026-09-09; a guarda existe para o
        -- caso de a origem mudar antes da aplicacao.
        SELECT count(*)::integer
          INTO v_quantidade
          FROM public.contratos ct
          JOIN public.consultores cs ON cs.id = ct.consultor_id
         WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g'))
               = v_row.nome
           AND ct.data_cadastro < v_row.adm;

        IF v_quantidade <> 0 THEN
            RAISE EXCEPTION
                'Migration 119: % tem % contrato(s) ANTES da admissao declarada (%) — producao prova presenca e desmente a data',
                v_row.nome, v_quantidade, v_row.adm;
        END IF;

        -- ---- 4. Abre a janela ----
        -- Idempotente: se ja houver qualquer janela da pessoa, nao cria
        -- outra. Reexecutar a migration nao duplica nem sobrepoe.
        SELECT count(*)::integer
          INTO v_quantidade
          FROM public.consultor_vigencia v
         WHERE v.nome_normalizado = v_row.nome;

        IF v_quantidade = 0 THEN
            INSERT INTO public.consultor_vigencia
                (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
            VALUES
                (v_row.nome, v_loja_id, v_row.adm, NULL, 'MANUAL');
            v_inseridas := v_inseridas + 1;
        ELSE
            -- Nao e erro: alguem pode ter corrigido antes, ou a migration
            -- ja rodou. Mas tambem nao se sobrescreve em silencio.
            v_ja_tinham := v_ja_tinham + 1;
            RAISE NOTICE
                'Migration 119: % ja tem % janela(s) — nada feito para esta pessoa',
                v_row.nome, v_quantidade;
        END IF;
    END LOOP;

    RAISE NOTICE 'Migration 119: % janela(s) criada(s), % pessoa(s) ja tinham.',
                 v_inseridas, v_ja_tinham;

    -- ---- 5. Pos-condicoes ----
    -- Cada uma das cinco com exatamente UMA janela aberta, na loja e na
    -- data declaradas.
    SELECT count(*)::integer INTO v_quantidade
      FROM (VALUES
          ('BRUNO VINICIUS MARTINS DA SILVA',      'HELP PRACA SECA',       DATE '2026-08-25'),
          ('STEPHANIA LANA LOPES',                 'HELP NOVA IGUACU',      DATE '2026-08-20'),
          ('MARIA LUISA DE MORAIS BRANDAO',        'HELP MADUREIRA',        DATE '2026-08-25'),
          ('GISELLE GALVAO DE FARIAS',             'HELP BONSUCESSO',       DATE '2026-09-04'),
          ('MATHEUS DUTRA DOS SANTOS DE OLIVEIRA', 'HELP CAXIAS GUANABARA', DATE '2026-09-04')
      ) AS t(nome, loja, adm)
      JOIN public.consultor_vigencia v ON v.nome_normalizado = t.nome
      JOIN public.lojas l ON l.id = v.loja_id
     WHERE v.vigencia_fim IS NULL
       AND v.vigencia_inicio = t.adm
       AND upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) = t.loja;

    IF v_quantidade <> 5 THEN
        RAISE EXCEPTION
            'Migration 119: pos-condicao falhou — % das 5 janelas conferem loja e data (esperado 5)',
            v_quantidade;
    END IF;

    -- Nenhuma delas pode ter ganhado mais de uma janela.
    SELECT count(*)::integer INTO v_quantidade
      FROM (
          SELECT v.nome_normalizado
            FROM public.consultor_vigencia v
           WHERE v.nome_normalizado IN (
                   'BRUNO VINICIUS MARTINS DA SILVA',
                   'STEPHANIA LANA LOPES',
                   'MARIA LUISA DE MORAIS BRANDAO',
                   'GISELLE GALVAO DE FARIAS',
                   'MATHEUS DUTRA DOS SANTOS DE OLIVEIRA')
           GROUP BY v.nome_normalizado
          HAVING count(*) > 1
      ) t;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 119: pos-condicao falhou — % pessoa(s) com mais de uma janela',
            v_quantidade;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) As cinco janelas:
--
--    SELECT v.nome, l.nome AS loja, v.vigencia_inicio, v.vigencia_fim, v.origem
--      FROM consultor_vigencia v
--      JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado IN (
--             'BRUNO VINICIUS MARTINS DA SILVA',
--             'STEPHANIA LANA LOPES',
--             'MARIA LUISA DE MORAIS BRANDAO',
--             'GISELLE GALVAO DE FARIAS',
--             'MATHEUS DUTRA DOS SANTOS DE OLIVEIRA')
--     ORDER BY v.vigencia_inicio, v.nome;
--
--    -- esperado (5 linhas, todas MANUAL, todas vigencia_fim NULL):
--    --   STEPHANIA LANA LOPES         HELP NOVA IGUACU        2026-08-20
--    --   BRUNO VINICIUS M. DA SILVA   HELP PRACA SECA         2026-08-25
--    --   MARIA LUISA DE M. BRANDAO    HELP MADUREIRA          2026-08-25
--    --   GISELLE GALVAO DE FARIAS     HELP BONSUCESSO         2026-09-04
--    --   MATHEUS DUTRA DOS S. DE O.   HELP CAXIAS GUANABARA   2026-09-04
--
-- 2) O detector nao as reporta mais:
--
--    SELECT jsonb_array_length(
--        public.fn_diag_vinculo_divergente() -> 'sem_janela_aberta');
--    -- esperado: 0  (eram 5 em 2026-09-09, e eram exatamente estas)
--    -- Requer a 116 aplicada.
--
-- 3) O denominador cresceu como previsto. Comparar antes/depois:
--
--    SELECT loja, peso, cabecas, du_competencia
--      FROM fn_headcount_ponderado(8, 2026)
--     WHERE loja IN ('HELP NOVA IGUACU', 'HELP PRACA SECA', 'HELP MADUREIRA');
--    -- esperado: peso +0,3810 / +0,2381 / +0,2381 e +1 cabeca cada;
--    --           du_competencia = 21
--
--    SELECT loja, peso, cabecas, du_competencia
--      FROM fn_headcount_ponderado(9, 2026)
--     WHERE loja IN ('HELP PRACA SECA', 'HELP NOVA IGUACU', 'HELP MADUREIRA',
--                    'HELP BONSUCESSO', 'HELP CAXIAS GUANABARA');
--    -- esperado: peso +1,0000 / +1,0000 / +1,0000 / +0,8571 / +0,8571;
--    --           du_competencia = 21
--
-- 4) Rematerializar as DUAS competencias — agosto muda:
--
--    SELECT fn_materializar_caderno(8, 2026);
--    SELECT fn_materializar_caderno(9, 2026);
--
--    Sem isso o Caderno publicado pelo bereshit diverge do dashboard, que
--    passa a dividir pelo peso novo imediatamente.
