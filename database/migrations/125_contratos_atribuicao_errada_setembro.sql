-- =====================================================
-- Migracao 125: dois contratos de setembro atribuidos a pessoa/loja
--               erradas pelo ETL
-- Data: 2026-10-01
--
-- ########################################################
-- #  NAO APLICAR — RESOLVIDA NA ORIGEM EM 2026-10-01     #
-- ########################################################
--
-- A operacao subiu uma carga corrigindo as duas ADEs no EXTRATOR, antes
-- de esta migration ser aplicada. Medido em 2026-10-01, depois da carga:
--
--   ADE 10457301   contrato 3001439  -> MIZAEL / HELP RIO COMPRIDO     ok
--   ADE 979085158  contrato 3006832  -> MARCELLA NUNES DEODATO /
--                                       HELP RIO COMPRIDO             ok
--
-- `created_at` das duas linhas nao mudou (09/09 13:18 e 22/09 13:47),
-- entao a carga fez UPDATE no lugar — nao duplicou contrato. O estado
-- final e identico ao que esta migration afirmaria, e as duas datas de
-- cadastro passaram a cair dentro de vigencia na loja do contrato.
--
-- MELHOR DESFECHO DO QUE APLICAR. O follow-up desta propria migration
-- avisava: "a correcao e no banco, nao na origem — se o extrator repetir
-- a ADE errada, o contrato volta para MARCELA na proxima carga". Corrigido
-- na origem, esse risco deixa de existir.
--
-- O arquivo fica como REGISTRO do veredito da operacao e pelas queries de
-- verificacao do fim. Se for executado por engano, e um no-op seguro: as
-- guardas aceitam o estado final (as clausulas `IN (origem, destino)`
-- existem para isso), os dois UPDATE casam zero linhas e as pos-condicoes
-- passam. Nao editar depois de qualquer aplicacao futura — ver AGENTS.md.
--
-- ########################################################
-- Depende de: 105 (guarda de origem), 111 (retorno de Mizael a Rio
--             Comprido), 124 (as previsoes desmentidas)
--
-- Terceira e ultima frente do bloqueio de 09/2026. Depois da 124 e da
-- 106, `fn_contar_pagamentos_sem_vinculo_origem(9, 2026)` caiu de 164
-- para 3. Esta migration resolve 2 dos 3 — os dois que a operacao julgou
-- como ATRIBUICAO ERRADA do ETL, nao como furo de ledger. O terceiro
-- (CASSIANE) e admissao e sai numa migration propria.
--
-- Ao contrario da 124, aqui o ledger esta certo e o CONTRATO esta errado.
-- Mesma direcao da 106/107: o eixo da metrica continua o pagamento, e a
-- data de cadastro so serve para auditar a origem.
--
--
-- CASO 1 — ADE 979085158: MARCELA (desligada) x MARCELLA (ativa)
-- --------------------------------------------------------------
-- Fato confirmado pela operacao (2026-10-01):
--   * o contrato foi registrado errado; a venda e de MARCELLA NUNES
--     DEODATO, de HELP RIO COMPRIDO.
--
-- O ETL pendurou um contrato de 21/09 em MARCELA DOS SANTOS SILVA, que
-- esta `Desligado (a)` no banco E no `HC_Colaboradores`, e cuja producao
-- para em 29/12/2025 — nove meses antes. A janela dela em HELP MEIER
-- fechou em 2026-01-01 pela regra de saida inferida da 087.
--
-- A confusao e de NOME, nao de loja:
--
--   MARCELA  DOS SANTOS SILVA   desligada   HELP MEIER
--   MARCELLA NUNES DEODATO      ativa       HELP RIO COMPRIDO
--
-- Medido: a ADE 979085158 e unica na base (nao ha contrato irmao com
-- ela), e MARCELLA tem janela aberta em RIO COMPRIDO desde 2026-07-27,
-- com 145 contratos em setembro. Ela NAO e supervisora — diferente da
-- 106, onde a producao foi para Patricia e saiu de `paidByConsultants`.
-- Aqui o valor continua no ranking de consultores, agora no nome certo.
--
-- Esta e a quarta aparicao da mecanica de `uq_consultores_nome_loja`
-- nesta base (109 JOYCE, 118 LIVIA, 121 MATHEUS, agora esta): nome
-- parecido ou ADE errada na origem faz o ETL escolher a pessoa errada, e
-- o que denuncia e sempre a producao fora de qualquer vigencia.
--
--
-- CASO 2 — ADE 10457301: MIZAEL, loja antiga depois do corte
-- -----------------------------------------------------------
-- Fato confirmado pela operacao (2026-10-01):
--   * a transferencia de 04/09 para HELP RIO COMPRIDO vale;
--   * logo o contrato de 08/09 esta atribuido a loja antiga.
--
-- A 111 foi escrita em 08/09 e registrou, de boa-fe, que "os ultimos
-- contratos em LARANJEIRAS sao de 02/09 e 03/09". O contrato que bloqueia
-- foi gravado em 2026-09-09 13:18 — o dia SEGUINTE. A 111 nao podia
-- saber, e o aviso dela ("em 04/09 ele ainda nao tem nenhum contrato em
-- RIO COMPRIDO ... declarado vence inferido") agora corta para o outro
-- lado: declarado continua vencendo, e quem cede e o contrato.
--
-- Os outros dois contratos de setembro (02/09 e 03/09) sao anteriores ao
-- corte e ficam em LARANJEIRAS, onde nasceram. Uma guarda garante que o
-- de 08/09 e o UNICO em Laranjeiras a partir de 04/09: se aparecer outro,
-- a migration para, porque ai o fato declarado precisa ser reexaminado.
--
-- O cadastro tambem muda, nao so a loja: `uq_consultores_nome_loja` da a
-- Mizael uma linha por loja, e um contrato em RIO COMPRIDO apontando para
-- o cadastro de LARANJEIRAS seria inconsistente para quem resolve o nome
-- pelo `consultor_id` (a CTE `producao` da 116, entre outros). A guarda
-- de origem da 105 nao notaria — ela casa por `nome_normalizado` — mas
-- isso e motivo para acertar os dois, nao para deixar passar um.
--
--
-- EFEITO NUMERICO EM 09/2026
-- --------------------------
-- Nenhum denominador muda: nenhuma vigencia e tocada. Move-se so o
-- numerador, entre lojas:
--
--   HELP MEIER          -R$   763,32
--   HELP LARANJEIRAS    -R$   371,44
--   HELP RIO COMPRIDO   +R$ 1.134,76
--
-- `dailyProductivity` das tres lojas muda; a soma da rede nao. No ranking
-- de consultores, MARCELLA ganha R$ 763,32 e MIZAEL conserva o valor
-- apenas trocando de loja.
--
-- `fn_contar_pagamentos_sem_vinculo_origem(9, 2026)`: 3 -> 1.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.contratos IN SHARE ROW EXCLUSIVE MODE;


-- ===========================================
-- 1. ADE 979085158 -> MARCELLA NUNES DEODATO / HELP RIO COMPRIDO
-- ===========================================

DO $$
DECLARE
    v_meier        UUID;
    v_rio_comprido UUID;
    v_marcela      UUID;  -- DOS SANTOS SILVA, desligada, Meier
    v_marcella     UUID;  -- NUNES DEODATO, ativa, Rio Comprido
    v_qtd          INTEGER;
    v_atualizadas  INTEGER;
    v_valor_antes  NUMERIC;
    v_valor_depois NUMERIC;
    v_contrato CONSTANT BIGINT := 3006832;
    v_ade      CONSTANT TEXT   := '979085158';
    v_cadastro CONSTANT DATE   := DATE '2026-09-21';
BEGIN
    -- ---- 1.1 Lojas ----
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_qtd, v_meier
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
           = 'HELP MEIER';

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: HELP MEIER ausente ou ambigua (% correspondencias)',
            v_qtd;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_qtd, v_rio_comprido
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
           = 'HELP RIO COMPRIDO';

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: HELP RIO COMPRIDO ausente ou ambigua (% correspondencias)',
            v_qtd;
    END IF;

    -- ---- 1.2 As duas pessoas ----
    SELECT count(*), (array_agg(c.id))[1]
      INTO v_qtd, v_marcela
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g'))
           = 'MARCELA DOS SANTOS SILVA'
       AND c.loja_id = v_meier;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: cadastro de MARCELA DOS SANTOS SILVA em Meier ausente ou ambiguo (% correspondencias)',
            v_qtd;
    END IF;

    SELECT count(*), (array_agg(c.id))[1]
      INTO v_qtd, v_marcella
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g'))
           = 'MARCELLA NUNES DEODATO'
       AND c.loja_id = v_rio_comprido;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: cadastro de MARCELLA NUNES DEODATO em Rio Comprido ausente ou ambiguo (% correspondencias)',
            v_qtd;
    END IF;

    -- ---- 1.3 A destinataria tem vigencia na data de cadastro ----
    -- Sem isso a correcao so mudaria o nome do furo de lugar.
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = 'MARCELLA NUNES DEODATO'
       AND v.loja_id = v_rio_comprido
       AND v_cadastro >= v.vigencia_inicio
       AND (v.vigencia_fim IS NULL OR v_cadastro < v.vigencia_fim);

    IF v_qtd < 1 THEN
        RAISE EXCEPTION
            'Migration 125: MARCELLA nao tem vigencia em RIO COMPRIDO em % — a correcao nao resolveria o bloqueio',
            v_cadastro;
    END IF;

    -- ---- 1.4 O contrato e o que foi medido ----
    SELECT count(*)::integer, coalesce(sum(c.valor), 0)
      INTO v_qtd, v_valor_antes
      FROM public.contratos c
     WHERE c.contrato_id   = v_contrato
       AND c.num_proposta  = v_ade
       AND c.data_cadastro = v_cadastro
       AND c.consultor_id IN (v_marcela, v_marcella)
       AND c.loja_id      IN (v_meier, v_rio_comprido);

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: contrato % / ADE % nao esta no estado medido (% correspondencias)',
            v_contrato, v_ade, v_qtd;
    END IF;

    -- ---- 1.5 A troca ----
    -- Idempotente: na reexecucao o contrato ja esta em MARCELLA e o
    -- UPDATE nao casa nenhuma linha.
    UPDATE public.contratos c
       SET consultor_id = v_marcella,
           loja_id      = v_rio_comprido
     WHERE c.contrato_id  = v_contrato
       AND c.consultor_id = v_marcela
       AND c.loja_id      = v_meier;

    GET DIAGNOSTICS v_atualizadas = ROW_COUNT;

    IF v_atualizadas NOT IN (0, 1) THEN
        RAISE EXCEPTION
            'Migration 125: estado parcial inesperado (% linhas atualizadas no caso 1)',
            v_atualizadas;
    END IF;

    -- ---- 1.6 Pos-condicoes ----
    SELECT count(*)::integer, coalesce(sum(c.valor), 0)
      INTO v_qtd, v_valor_depois
      FROM public.contratos c
     WHERE c.contrato_id   = v_contrato
       AND c.consultor_id  = v_marcella
       AND c.loja_id       = v_rio_comprido
       AND c.data_cadastro = v_cadastro;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: pos-condicao falhou — contrato % nao esta em MARCELLA/RIO COMPRIDO',
            v_contrato;
    END IF;

    IF v_valor_depois IS DISTINCT FROM v_valor_antes THEN
        RAISE EXCEPTION
            'Migration 125: pos-condicao falhou — valor do contrato % mudou de % para %',
            v_contrato, v_valor_antes, v_valor_depois;
    END IF;

    -- MARCELA volta a nao ter producao nenhuma em 2026, coerente com a
    -- janela dela fechada em 2026-01-01.
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.contratos c
     WHERE c.consultor_id = v_marcela
       AND c.data_cadastro >= DATE '2026-01-01';

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION
            'Migration 125: pos-condicao falhou — MARCELA ainda tem % contrato(s) em 2026',
            v_qtd;
    END IF;
END
$$;


-- ===========================================
-- 2. ADE 10457301 -> MIZAEL / HELP RIO COMPRIDO
-- ===========================================

DO $$
DECLARE
    v_laranjeiras  UUID;
    v_rio_comprido UUID;
    v_mz_laranj    UUID;
    v_mz_rio       UUID;
    v_qtd          INTEGER;
    v_atualizadas  INTEGER;
    v_valor_antes  NUMERIC;
    v_valor_depois NUMERIC;
    v_nome     CONSTANT TEXT   := 'MIZAEL BARBOSA NETO';
    v_contrato CONSTANT BIGINT := 3001439;
    v_ade      CONSTANT TEXT   := '10457301';
    v_cadastro CONSTANT DATE   := DATE '2026-09-08';
    v_corte    CONSTANT DATE   := DATE '2026-09-04';
BEGIN
    -- ---- 2.1 Lojas ----
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_qtd, v_laranjeiras
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
           = 'HELP LARANJEIRAS';

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: HELP LARANJEIRAS ausente ou ambigua (% correspondencias)',
            v_qtd;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_qtd, v_rio_comprido
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g'))
           = 'HELP RIO COMPRIDO';

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: HELP RIO COMPRIDO ausente ou ambigua (% correspondencias)',
            v_qtd;
    END IF;

    -- ---- 2.2 Os dois cadastros dele ----
    SELECT count(*), (array_agg(c.id))[1]
      INTO v_qtd, v_mz_laranj
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND c.loja_id = v_laranjeiras;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: cadastro de Mizael em Laranjeiras ausente ou ambiguo (% correspondencias)',
            v_qtd;
    END IF;

    SELECT count(*), (array_agg(c.id))[1]
      INTO v_qtd, v_mz_rio
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND c.loja_id = v_rio_comprido;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: cadastro de Mizael em Rio Comprido ausente ou ambiguo (% correspondencias)',
            v_qtd;
    END IF;

    -- ---- 2.3 A janela declarada pela 111 cobre a data de cadastro ----
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_rio_comprido
       AND v_cadastro >= v.vigencia_inicio
       AND (v.vigencia_fim IS NULL OR v_cadastro < v.vigencia_fim);

    IF v_qtd < 1 THEN
        RAISE EXCEPTION
            'Migration 125: Mizael nao tem vigencia em RIO COMPRIDO em % — a 111 pode ter sido revista',
            v_cadastro;
    END IF;

    -- ---- 2.4 E o UNICO contrato em Laranjeiras depois do corte ----
    -- Se aparecer outro, o fato declarado em 04/09 precisa de novo exame
    -- antes de qualquer escrita.
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.contratos c
     WHERE c.consultor_id IN (v_mz_laranj, v_mz_rio)
       AND c.loja_id = v_laranjeiras
       AND c.data_cadastro >= v_corte;

    IF v_qtd > 1 THEN
        RAISE EXCEPTION
            'Migration 125: Mizael tem % contratos em LARANJEIRAS a partir de % — esperado no maximo 1',
            v_qtd, v_corte;
    END IF;

    -- ---- 2.5 O contrato e o que foi medido ----
    SELECT count(*)::integer, coalesce(sum(c.valor), 0)
      INTO v_qtd, v_valor_antes
      FROM public.contratos c
     WHERE c.contrato_id   = v_contrato
       AND c.num_proposta  = v_ade
       AND c.data_cadastro = v_cadastro
       AND c.consultor_id IN (v_mz_laranj, v_mz_rio)
       AND c.loja_id      IN (v_laranjeiras, v_rio_comprido);

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: contrato % / ADE % nao esta no estado medido (% correspondencias)',
            v_contrato, v_ade, v_qtd;
    END IF;

    -- ---- 2.6 A troca ----
    UPDATE public.contratos c
       SET consultor_id = v_mz_rio,
           loja_id      = v_rio_comprido
     WHERE c.contrato_id  = v_contrato
       AND c.consultor_id = v_mz_laranj
       AND c.loja_id      = v_laranjeiras;

    GET DIAGNOSTICS v_atualizadas = ROW_COUNT;

    IF v_atualizadas NOT IN (0, 1) THEN
        RAISE EXCEPTION
            'Migration 125: estado parcial inesperado (% linhas atualizadas no caso 2)',
            v_atualizadas;
    END IF;

    -- ---- 2.7 Pos-condicoes ----
    SELECT count(*)::integer, coalesce(sum(c.valor), 0)
      INTO v_qtd, v_valor_depois
      FROM public.contratos c
     WHERE c.contrato_id   = v_contrato
       AND c.consultor_id  = v_mz_rio
       AND c.loja_id       = v_rio_comprido
       AND c.data_cadastro = v_cadastro;

    IF v_qtd <> 1 THEN
        RAISE EXCEPTION
            'Migration 125: pos-condicao falhou — contrato % nao esta em MIZAEL/RIO COMPRIDO',
            v_contrato;
    END IF;

    IF v_valor_depois IS DISTINCT FROM v_valor_antes THEN
        RAISE EXCEPTION
            'Migration 125: pos-condicao falhou — valor do contrato % mudou de % para %',
            v_contrato, v_valor_antes, v_valor_depois;
    END IF;

    -- Os de 02/09 e 03/09 continuam em Laranjeiras: nasceram antes do
    -- corte e nao sao desta migration.
    SELECT count(*)::integer
      INTO v_qtd
      FROM public.contratos c
     WHERE c.consultor_id IN (v_mz_laranj, v_mz_rio)
       AND c.loja_id = v_laranjeiras
       AND c.data_cadastro >= DATE '2026-09-01'
       AND c.data_cadastro <  v_corte;

    IF v_qtd <> 2 THEN
        RAISE EXCEPTION
            'Migration 125: pos-condicao falhou — % contrato(s) de Mizael em Laranjeiras antes de % (esperado 2)',
            v_qtd, v_corte;
    END IF;
END
$$;


-- ===========================================
-- 3. Pos-condicao conjunta: producao coberta pelo ledger
--
-- Mesma forma da secao 3 da 124, agora sobre as pessoas desta migration.
-- Afirmada sobre CONTRATOS, nao sobre pagamento: nao fica falsa na
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
                     'MARCELA DOS SANTOS SILVA',
                     'MARCELLA NUNES DEODATO',
                     'MIZAEL BARBOSA NETO')
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
            'Migration 125: pos-condicao falhou — producao sem vigencia na loja: %',
            v_furos;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) Os dois contratos no lugar certo:
--
--    SELECT v.contrato_id, v.num_proposta, v.consultor, v.loja,
--           v.data_cadastro, v.valor_consolidado, v.data_status_pagamento
--      FROM v_contratos_dashboard v
--     WHERE v.contrato_id IN (3006832, 3001439)
--     ORDER BY v.contrato_id;
--
--    -- esperado:
--    --  3001439  10457301   MIZAEL BARBOSA NETO     HELP RIO COMPRIDO  2026-09-08
--    --  3006832  979085158  MARCELLA NUNES DEODATO  HELP RIO COMPRIDO  2026-09-21
--
-- 2) A guarda de origem cai para 1 — sobra so CASSIANE:
--
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(9, 2026);
--    -- 3 antes; 1 depois. Setembro SEGUE BLOQUEADO ate a admissao dela
--    -- ser registrada.
--
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(8, 2026);
--    -- 0, inalterado: os dois contratos sao de setembro.
--
-- 3) O numerador que mudou de loja (conferir antes de republicar):
--
--    SELECT loja, count(*), sum(valor_consolidado)
--      FROM v_contratos_dashboard
--     WHERE loja IN ('HELP MEIER', 'HELP LARANJEIRAS', 'HELP RIO COMPRIDO')
--       AND data_status_pagamento >= DATE '2026-09-01'
--       AND data_status_pagamento <  DATE '2026-10-01'
--     GROUP BY loja ORDER BY loja;
--
--    -- MEIER -763,32 / LARANJEIRAS -371,44 / RIO COMPRIDO +1.134,76
--    -- em relacao a medicao de 2026-10-01.
--
-- 4) MARCELA nao aparece mais em 2026 (ela segue desligada e sem janela):
--
--    SELECT count(*) FROM contratos ct
--      JOIN consultores cs ON cs.id = ct.consultor_id
--     WHERE upper(regexp_replace(btrim(cs.nome),'[[:space:]]+',' ','g'))
--           = 'MARCELA DOS SANTOS SILVA'
--       AND ct.data_cadastro >= DATE '2026-01-01';
--    -- esperado: 0
--
-- 5) Rematerializar — so quando a contagem de 09 estiver em 0:
--
--    SELECT fn_materializar_caderno(8, 2026);
--    SELECT fn_materializar_caderno(9, 2026);
--
--
-- =====================================================
-- FOLLOW-UPS
-- =====================================================
--
-- [ ] CASSIANE COELHO DE OLIVEIRA — ultimo evento do bloqueio. Admissao
--     de setembro em HELP SAO JOAO DE MERITI, cadastro criado pelo proprio
--     ETL de contratos em 25/09 14:26:04, tres segundos antes de gravar o
--     contrato. Falta a data declarada pelo RH para abrir a janela MANUAL.
--     A 116 ja a acusa em `sem_janela_aberta`.
--
-- [ ] A CORRECAO E NO BANCO, NAO NA ORIGEM. Se o extrator repetir a ADE
--     errada do caso 1, o contrato volta para MARCELA na proxima carga —
--     a mesma ressalva da 121. Vale conferir a ADE 979085158 na origem.
--
-- [ ] `uq_consultores_nome_loja` JA ERROU QUATRO VEZES por nome parecido
--     ou ADE trocada (109, 118, 121, esta). Nenhuma guarda nova e
--     necessaria — a 105 pega o caso sempre que ha pagamento, e a 116
--     pega o cadastro orfao. Mas vale medir quantos pares de nomes a um
--     caractere de distancia existem em `consultores`: MARCELA/MARCELLA
--     nao e o unico par e o proximo erro desses nao sera visto antes de
--     outro bloqueio.
