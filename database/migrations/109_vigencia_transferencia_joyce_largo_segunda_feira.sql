-- =====================================================
-- Migracao 109: transferencia de JOYCE para HELP LARGO DA SEGUNDA FEIRA
-- Data: 2026-09-08
-- Depende de: 087 (ledger em granularidade de dia)
--
-- Fato confirmado pela operacao:
--   * JOYCE ANNY DA SILVA FOCHT DE JESUS NUNCA trabalhou em HELP ALCANTARA;
--   * a partir de 01/09/2026 ela pertence a HELP LARGO DA SEGUNDA FEIRA;
--   * antes dessa data, a producao dela e de HELP CASCADURA.
--
-- A regra particiona a producao dela sem ambiguidade (remedido em
-- 2026-09-08, apos a carga das 14:32): 163 contratos em CASCADURA, o
-- ultimo em 31/08/2026, e ZERO em CASCADURA a partir de 01/09; 6
-- contratos em LARGO DA SEGUNDA FEIRA entre 02/09 e 04/09, nenhum
-- antes. Nao ha mes com as duas lojas, entao a fronteira nao depende
-- de desempate.
--
-- Direcao reconfirmada pelo usuario em 2026-09-08: CASCADURA ate
-- 31/08, LARGO DA SEGUNDA FEIRA a partir de 01/09 — nunca o inverso.
--
--
-- O QUE JA FOI CORRIGIDO NA ORIGEM (e o que sobrou)
-- --------------------------------------------------
-- Em 03/09 as 15:24 o ETL de contratos gravou 2 ADEs sob a filial HELP
-- ALCANTARA para ela e, 6 segundos antes, CRIOU o cadastro
-- (JOYCE, HELP ALCANTARA) — porque `uq_consultores_nome_loja` e
-- (nome, loja_id), entao um par inedito INSERE em vez de reconhecer a
-- pessoa que ja existia em CASCADURA. Em 04/09 as 18:50 a origem foi
-- reimportada: os 5 contratos passaram para HELP LARGO DA SEGUNDA
-- FEIRA e um TERCEIRO cadastro foi criado para a loja certa.
--
-- Sobraram TRES coisas que a reimportacao nao alcanca, e esta migration
-- resolve as tres:
--
--   1. o LEDGER, que esta fora do caminho do ETL de contratos e segue
--      dizendo HELP CASCADURA / janela aberta desde 2026-05-04;
--   2. a PRODUCAO FANTASMA em HELP ALCANTARA: em 2026-09-08 as 14:32 a
--      origem voltou a gravar sob a filial errada — contrato 3000625
--      (proposta 10445112, data_cadastro 04/09, R$ 346,26, PAGO AO
--      CLIENTE), preso ao cadastro orfao;
--   3. o cadastro ORFAO (JOYCE, HELP ALCANTARA), residuo do INSERT de
--      03/09. Remocao autorizada pelo usuario em 2026-09-08.
--
-- A ORDEM IMPORTA: (3) so e possivel depois de (2). `contratos`
-- referencia `consultores` e o orfao deixou de estar vazio, entao a
-- guarda de remocao — que exige zero contratos — passou a barrar a
-- migration inteira. Pior seria remover sem a guarda: a FK e
-- ON DELETE SET NULL, entao o DELETE nao apagaria o contrato, deixaria
-- `consultor_id = NULL` e trocaria uma producao na loja errada por uma
-- producao sem consultor nenhum.
--
-- Por que o orfao nao pode simplesmente ficar: ate 08/09 ele era inerte
-- porque `_colapsar_cadastro_recente` (loaders.py) e o `DISTINCT ON ...
-- ORDER BY updated_at DESC` do SQL escolhem o cadastro de updated_at
-- mais recente, e o de LARGO DA SEGUNDA FEIRA (04/09 18:50) e mais novo
-- que o de ALCANTARA (03/09 15:24). A pessoa aparecia na loja certa POR
-- ORDEM DE TIMESTAMP, nao porque a linha errada deixasse de existir. O
-- contrato de 08/09 mostrou que essa protecao nao vale nada: o ETL
-- reconheceu o par (nome, HELP ALCANTARA) que ja existia e pendurou
-- producao nova nele, sem tocar em updated_at nenhum.
--
-- Consequencia de (1) enquanto nao se aplica esta migration:
-- `carregar_vinculos_consultores` conta os 21 dias uteis de 09/2026
-- inteiros em CASCADURA, e os 6 contratos de LARGO DA SEGUNDA FEIRA
-- ficam sem vigencia de origem — entram em
-- `fn_contar_pagamentos_sem_vinculo_origem(9, 2026)`, que marcava 58 em
-- 2026-09-08.
--
-- Consequencia de (2): a producao dela em 09/2026 aparece repartida
-- entre tres lojas nas telas que usam a loja do CONTRATO (a view
-- `v_contratos_dashboard` deriva `loja` de `contratos.loja_id`) —
-- LARGO DA SEGUNDA FEIRA R$ 10.284,90, ALCANTARA R$ 346,26 e CASCADURA
-- R$ 0,00. Na aba de gestao o efeito e outro: `_esqueleto_vinculos`
-- (kpis/produtividade.py) identifica a pessoa pela loja de maior
-- permanencia NO LEDGER e `_producao_por_consultor` soma a producao por
-- NOME, entao hoje os R$ 10.631,16 inteiros aparecem creditados a
-- CASCADURA. Duas telas, duas lojas erradas, a mesma raiz.
--
--
-- FRONTEIRA
-- ---------
-- Janela meio-aberta [inicio, fim), como em toda a 086/087: fechar
-- CASCADURA em 2026-09-01 faz o ultimo dia coberto ser 31/08 e LARGO DA
-- SEGUNDA FEIRA comecar em 01/09. Emenda sem vago nem sobreposicao.
--
-- A data vem da REGRA DECLARADA pela operacao (01/09), nao do primeiro
-- contrato (02/09). E o mesmo criterio das 106/107: declarado vence
-- inferido. Usar 02/09 tiraria dela o 1o dia util do mes por inferencia.
--
-- origem = 'MANUAL' nas duas linhas. Alem de marcar procedencia, isso
-- IMUNIZA a correcao: o rebuild do backfill apaga so
-- `origem LIKE 'BACKFILL%'`. Sem isso, um rebuild leria os 5 contratos
-- de 09/2026, veria loja unica no mes e reescreveria a fronteira.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.consultores IN SHARE ROW EXCLUSIVE MODE;
-- `contratos` entrou na 2a versao desta migration: a etapa 5 reatribui
-- a producao fantasma. Sem o lock, uma carga concorrente do ETL poderia
-- pendurar um contrato novo no cadastro orfao entre a reatribuicao e o
-- DELETE, e a FK ON DELETE SET NULL o desligaria da pessoa em silencio.
LOCK TABLE public.contratos IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_cascadura_id  UUID;
    v_largo_id      UUID;
    v_alcantara_id  UUID;
    v_janela_id     UUID;
    v_orfao_id      UUID;
    v_cad_largo_id      UUID;
    v_cad_cascadura_id  UUID;
    v_movidos_largo     INTEGER := 0;
    v_movidos_cascadura INTEGER := 0;
    v_quantidade    INTEGER;
    v_conflito      INTEGER;
    v_nome CONSTANT TEXT := 'JOYCE ANNY DA SILVA FOCHT DE JESUS';
    v_corte CONSTANT DATE := DATE '2026-09-01';
BEGIN
    -- ---- 1. Resolucao das lojas ----
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_cascadura_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP CASCADURA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 109: HELP CASCADURA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_largo_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP LARGO DA SEGUNDA FEIRA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 109: HELP LARGO DA SEGUNDA FEIRA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_alcantara_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP ALCANTARA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 109: HELP ALCANTARA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    -- ---- 2. Pre-condicao: a producao respeita o corte de 01/09 ----
    -- Se a origem voltar a mudar, esta guarda para a migration em vez de
    -- gravar uma fronteira que os contratos ja nao sustentam.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_cascadura_id
       AND ct.data_cadastro >= v_corte;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 109: % contrato(s) em CASCADURA a partir de 01/09/2026 — a fronteira nao e mais limpa',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_largo_id
       AND ct.data_cadastro < v_corte;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 109: % contrato(s) em LARGO DA SEGUNDA FEIRA antes de 01/09/2026 — a fronteira nao e mais limpa',
            v_quantidade;
    END IF;

    -- ---- 3. Fecha a janela de CASCADURA ----
    -- Idempotente: na reexecucao a janela ja esta fechada e o SELECT
    -- abaixo nao acha linha aberta, entao o UPDATE nao roda.
    SELECT count(*), (array_agg(v.id))[1]
      INTO v_quantidade, v_janela_id
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_cascadura_id
       AND v.vigencia_fim IS NULL;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 109: % janelas abertas de Joyce em Cascadura (esperado 0 ou 1)',
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
                'Migration 109: janela de Cascadura comeca em ou depois de 01/09/2026 — fechar violaria chk_cv_vigencia_ordem';
        END IF;

        UPDATE public.consultor_vigencia v
           SET vigencia_fim = v_corte,
               origem       = 'MANUAL'
         WHERE v.id = v_janela_id;
    END IF;

    -- ---- 4. Abre a janela de LARGO DA SEGUNDA FEIRA ----
    -- `uq_cv_consultor_loja_aberta` ja garante no maximo uma aberta por
    -- (pessoa, loja); o IF torna a reexecucao um no-op em vez de erro.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.loja_id = v_largo_id;

    IF v_quantidade = 0 THEN
        INSERT INTO public.consultor_vigencia
            (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
        VALUES
            (v_nome, v_largo_id, v_corte, NULL, 'MANUAL');
    ELSIF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 109: % janelas de Joyce em Largo da Segunda Feira (esperado 0 ou 1)',
            v_quantidade;
    END IF;

    -- ---- 5. Reatribui a producao fantasma de HELP ALCANTARA ----
    -- Toda producao pendurada no cadastro orfao volta para a loja que o
    -- LEDGER diz, pela data do contrato: antes do corte e CASCADURA,
    -- a partir do corte e LARGO DA SEGUNDA FEIRA. Nao ha lista de
    -- contratos codificada aqui de proposito — em 2026-09-08 e um so
    -- (3000625, de 04/09), mas a origem ja provou que grava mais sob a
    -- filial errada, e a regra tem de valer para o que chegar ate a
    -- aplicacao.
    --
    -- `loja_id` E `consultor_id` mudam juntos: a view deriva `loja` de
    -- `contratos.loja_id` e `consultor` de `consultores.nome` via
    -- `consultor_id`. Mover so a loja deixaria o contrato preso ao
    -- cadastro orfao e a etapa 6 nao poderia remove-lo.
    SELECT count(*), (array_agg(c.id))[1]
      INTO v_quantidade, v_orfao_id
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND c.loja_id = v_alcantara_id;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 109: % cadastros de Joyce em HELP ALCANTARA (esperado 0 ou 1)',
            v_quantidade;
    END IF;

    IF v_quantidade = 1 THEN
        -- Cadastros de destino. Sao pre-condicao da reatribuicao: sem
        -- eles nao ha para onde mover, e mover para o cadastro errado
        -- seria pior que nao mover.
        SELECT count(*), (array_agg(c.id))[1]
          INTO v_quantidade, v_cad_largo_id
          FROM public.consultores c
         WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
           AND c.loja_id = v_largo_id;

        IF v_quantidade <> 1 THEN
            RAISE EXCEPTION
                'Migration 109: % cadastros de Joyce em LARGO DA SEGUNDA FEIRA (esperado exatamente 1 para receber a producao)',
                v_quantidade;
        END IF;

        SELECT count(*), (array_agg(c.id))[1]
          INTO v_quantidade, v_cad_cascadura_id
          FROM public.consultores c
         WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
           AND c.loja_id = v_cascadura_id;

        IF v_quantidade <> 1 THEN
            RAISE EXCEPTION
                'Migration 109: % cadastros de Joyce em CASCADURA (esperado exatamente 1 para receber a producao)',
                v_quantidade;
        END IF;

        -- A partir do corte: LARGO DA SEGUNDA FEIRA.
        UPDATE public.contratos ct
           SET loja_id      = v_largo_id,
               consultor_id = v_cad_largo_id
         WHERE ct.consultor_id = v_orfao_id
           AND ct.data_cadastro >= v_corte;

        GET DIAGNOSTICS v_movidos_largo = ROW_COUNT;

        -- Antes do corte: CASCADURA. Hoje nao existe nenhum; a clausula
        -- esta aqui porque a fronteira, e nao a foto de hoje, e a regra.
        UPDATE public.contratos ct
           SET loja_id      = v_cascadura_id,
               consultor_id = v_cad_cascadura_id
         WHERE ct.consultor_id = v_orfao_id
           AND ct.data_cadastro < v_corte;

        GET DIAGNOSTICS v_movidos_cascadura = ROW_COUNT;

        -- `data_cadastro` e NULL-avel: um contrato sem data nao cai em
        -- nenhum dos dois UPDATEs e travaria a etapa 6 sem explicar por
        -- que. Para aqui, dizendo o que aconteceu.
        SELECT count(*)::integer
          INTO v_conflito
          FROM public.contratos ct
         WHERE ct.consultor_id = v_orfao_id
           AND ct.data_cadastro IS NULL;

        IF v_conflito <> 0 THEN
            RAISE EXCEPTION
                'Migration 109: % contrato(s) do cadastro orfao sem data_cadastro — sem data nao ha como decidir a loja de destino',
                v_conflito;
        END IF;

        RAISE NOTICE
            'Migration 109: producao fantasma reatribuida — % para LARGO DA SEGUNDA FEIRA, % para CASCADURA',
            v_movidos_largo, v_movidos_cascadura;
    END IF;

    -- ---- 6. Remove o cadastro orfao (JOYCE, HELP ALCANTARA) ----
    -- Autorizado pelo usuario em 2026-09-08. So apaga o que estiver
    -- comprovadamente sem referencia: as tres guardas abaixo sao a
    -- pre-condicao, nao documentacao.
    SELECT count(*), (array_agg(c.id))[1]
      INTO v_quantidade, v_orfao_id
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND c.loja_id = v_alcantara_id;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 109: % cadastros de Joyce em HELP ALCANTARA (esperado 0 ou 1)',
            v_quantidade;
    END IF;

    IF v_quantidade = 1 THEN
        -- Nunca apagar o ultimo cadastro da pessoa: `contratos.consultor_id`
        -- e `usuario_escopos.consultor_id` dependem de existir ao menos um.
        SELECT count(*)::integer
          INTO v_conflito
          FROM public.consultores c
         WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
           AND c.id <> v_orfao_id;

        IF v_conflito = 0 THEN
            RAISE EXCEPTION
                'Migration 109: o cadastro em HELP ALCANTARA e o unico de Joyce — remover deixaria a pessoa sem cadastro';
        END IF;

        -- Depois da etapa 5 isto tem de ser zero. Se nao for, algum
        -- contrato escapou da reatribuicao (data_cadastro fora das duas
        -- faixas, ou escrita concorrente) e remover o cadastro agora o
        -- deixaria sem consultor, via ON DELETE SET NULL.
        SELECT count(*)::integer INTO v_conflito
          FROM public.contratos WHERE consultor_id = v_orfao_id;
        IF v_conflito <> 0 THEN
            RAISE EXCEPTION
                'Migration 109: cadastro orfao ainda tem % contrato(s) apos a reatribuicao da etapa 5',
                v_conflito;
        END IF;

        -- usuario_escopos.consultor_id e ON DELETE CASCADE: sem esta
        -- guarda, o DELETE levaria junto o escopo de um usuario em
        -- silencio.
        SELECT count(*)::integer INTO v_conflito
          FROM public.usuario_escopos WHERE consultor_id = v_orfao_id;
        IF v_conflito <> 0 THEN
            RAISE EXCEPTION
                'Migration 109: cadastro orfao tem % usuario_escopos — remover apagaria escopo por CASCADE',
                v_conflito;
        END IF;

        SELECT count(*)::integer INTO v_conflito
          FROM public.reconquista WHERE consultor_id = v_orfao_id;
        IF v_conflito <> 0 THEN
            RAISE EXCEPTION
                'Migration 109: cadastro orfao tem % linha(s) em reconquista',
                v_conflito;
        END IF;

        DELETE FROM public.consultores WHERE id = v_orfao_id;
    END IF;

    -- ---- 7. Pos-condicoes ----
    -- Exatamente uma janela aberta, e ela e a de LARGO DA SEGUNDA FEIRA.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_fim IS NULL;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 109: pos-condicao falhou — % janelas abertas (esperado 1)',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nome
       AND v.vigencia_fim IS NULL
       AND v.loja_id = v_largo_id
       AND v.vigencia_inicio = v_corte;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 109: pos-condicao falhou — a janela aberta nao e LARGO DA SEGUNDA FEIRA desde 01/09/2026';
    END IF;

    -- Emenda sem vago nem sobreposicao: nenhuma janela dela pode
    -- comecar antes do fim da anterior.
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
            'Migration 109: pos-condicao falhou — % emenda(s) com vago ou sobreposicao na linha do tempo de Joyce',
            v_quantidade;
    END IF;

    -- Nenhum cadastro dela em HELP ALCANTARA sobrou.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND c.loja_id = v_alcantara_id;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 109: pos-condicao falhou — % cadastro(s) de Joyce ainda em HELP ALCANTARA',
            v_quantidade;
    END IF;

    -- E o cadastro que o dedup escolhe (updated_at mais recente) e o de
    -- LARGO DA SEGUNDA FEIRA — a loja certa por identidade, nao por
    -- ordem de timestamp.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM (
          SELECT c.loja_id
            FROM public.consultores c
           WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = v_nome
           ORDER BY c.updated_at DESC NULLS LAST, c.id DESC
           LIMIT 1
      ) t
     WHERE t.loja_id = v_largo_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 109: pos-condicao falhou — o cadastro vencedor de Joyce nao e HELP LARGO DA SEGUNDA FEIRA';
    END IF;

    -- Nenhuma producao dela sobrou apontando para HELP ALCANTARA. E
    -- esta a pos-condicao do efeito fantasma: enquanto um contrato dela
    -- carregar essa loja, ela reaparece dentro de ALCANTARA em toda
    -- tela que usa a loja do contrato, com ou sem cadastro.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_alcantara_id;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 109: pos-condicao falhou — % contrato(s) de Joyce ainda em HELP ALCANTARA',
            v_quantidade;
    END IF;

    -- Nenhum contrato ficou orfao de consultor. A FK e ON DELETE SET
    -- NULL: se a etapa 5 tivesse deixado algo para tras, a etapa 6 o
    -- teria desligado da pessoa em silencio.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
     WHERE ct.consultor_id IS NULL
       AND ct.loja_id = v_alcantara_id;

    IF v_quantidade <> 0 THEN
        RAISE EXCEPTION
            'Migration 109: pos-condicao falhou — % contrato(s) em HELP ALCANTARA ficaram sem consultor',
            v_quantidade;
    END IF;

    -- A producao total dela nao mudou: reatribuir move de loja, nunca
    -- cria nem destroi. 170 = 163 CASCADURA + 6 LARGO + 1 reatribuido,
    -- medido em 2026-09-08; a guarda compara com o que o UPDATE moveu,
    -- entao continua valendo se a origem trouxer mais contratos antes
    -- da aplicacao.
    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.contratos ct
      JOIN public.consultores cs ON cs.id = ct.consultor_id
     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = v_nome
       AND ct.loja_id = v_largo_id
       AND ct.data_cadastro >= v_corte;

    IF v_quantidade < v_movidos_largo THEN
        RAISE EXCEPTION
            'Migration 109: pos-condicao falhou — LARGO DA SEGUNDA FEIRA tem % contrato(s) a partir do corte, menos que os % reatribuidos',
            v_quantidade, v_movidos_largo;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) A linha do tempo dela: CASCADURA fecha em 01/09, LARGO abre em 01/09.
--
--    SELECT l.nome, v.vigencia_inicio, v.vigencia_fim, v.origem
--      FROM consultor_vigencia v
--      JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado = 'JOYCE ANNY DA SILVA FOCHT DE JESUS'
--     ORDER BY v.vigencia_inicio;
--
--    -- esperado:
--    --   HELP CASCADURA                2026-05-04   2026-09-01   MANUAL
--    --   HELP LARGO DA SEGUNDA FEIRA   2026-09-01   NULL         MANUAL
--
-- 2) Os 7 contratos de 09/2026 deixam de ser pagamento sem vinculo de
--    origem — os 6 de LARGO por ganharem vigencia, o de ALCANTARA por
--    mudar de loja. O contador NAO vai a zero: ele agregava 58 em
--    2026-09-08 as 15h, dos quais 7 sao dela (o de 03/09 tem
--    valor_liquido 0,00 e ja nao contava, entao a queda observada pode
--    ser de 6). Comparar antes/depois em vez de assumir:
--
--    SELECT fn_contar_pagamentos_sem_vinculo_origem(9, 2026);
--    -- esperado: cair ~6-7 pontos, se nada mais mudar na origem.
--
--
-- 3) A producao fantasma sumiu de HELP ALCANTARA. Esta e a consulta que
--    reproduz o que o usuario via no dashboard:
--
--    SELECT loja, count(*), sum(valor_consolidado)
--      FROM v_contratos_dashboard
--     WHERE consultor = 'JOYCE ANNY DA SILVA FOCHT DE JESUS'
--       AND data_status_pagamento >= DATE '2026-09-01'
--     GROUP BY loja;
--
--    -- esperado: UMA linha, HELP LARGO DA SEGUNDA FEIRA.
--    -- antes: LARGO 10.284,90 + ALCANTARA 346,26.
--
--    E a producao total dela nao pode ter mudado (170 contratos em
--    2026-09-08 — 163 CASCADURA + 7 setembro):
--
--    SELECT count(*) FROM contratos ct JOIN consultores cs
--        ON cs.id = ct.consultor_id
--     WHERE upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g'))
--           = 'JOYCE ANNY DA SILVA FOCHT DE JESUS';
--
--
-- 4) O cadastro orfao sumiu e o vencedor do dedup e a loja certa:
--
--    SELECT l.nome, c.status, c.updated_at
--      FROM consultores c
--      JOIN lojas l ON l.id = c.loja_id
--     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g'))
--           = 'JOYCE ANNY DA SILVA FOCHT DE JESUS'
--     ORDER BY c.updated_at DESC;
--
--    -- esperado: 2 linhas, nenhuma em HELP ALCANTARA
--    --   HELP LARGO DA SEGUNDA FEIRA   Ativo (a)   2026-09-04 18:50
--    --   HELP CASCADURA                Ativo (a)   2026-08-11 20:44
