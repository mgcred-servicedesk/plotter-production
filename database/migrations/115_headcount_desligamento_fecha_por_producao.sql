-- =====================================================
-- Migracao 115: desligamento tambem fecha pela producao no arquivo HC
-- Data: 2026-09-09
-- Depende de: 095 (versao vigente da fn_headcount_replace), 100 (a
--             doutrina que esta migration adota)
--
-- DUAS PORTAS, DOIS DESFECHOS PARA O MESMO FATO
-- ----------------------------------------------
-- Producao digitada em ou depois da data de desligamento declarada e um
-- fato que chega pelas duas portas de RH, e ate aqui cada uma resolvia
-- de um jeito:
--
--   * fn_headcount_replace (095, arquivo HC_Colaboradores) — classifica
--     `divergencia_producao`, REPORTA e nao escreve. A janela fica
--     aberta e a pessoa segue pesando 1,0 no denominador (091) depois
--     de ter saido.
--
--   * fn_movimentacoes_rh_import (100, arquivo de e-mails) — fecha no
--     dia seguinte ao ultimo contrato, marca BACKFILL_PRODUCAO e
--     REPORTA a divergencia. Recusa so acima de 30 dias.
--
-- Mesma pessoa, mesma semana, dois arquivos: resultados diferentes.
--
-- Decisao do usuario (2026-09-09): vale a doutrina da 100 — producao
-- prova presenca. Esta migration leva a 095 para la.
--
-- O raciocinio da 100, que agora passa a valer nas duas portas: o
-- arquivo carrega o EVENTO (o e-mail de bloqueio, a comunicacao do
-- desligamento); a vigencia quer o primeiro dia de INDISPONIBILIDADE.
-- Entre os dois cabe o aviso previo, trabalhado e vendido normalmente.
-- Como `vigencia_fim` e exclusivo (091: `d.dia < v.vigencia_fim`),
-- gravar a data do arquivo tira do denominador dias que a pessoa
-- comprovadamente trabalhou — a producao dela continua contando e o
-- divisor encolhe, inflando a media da loja.
--
--
-- O QUE MUDA
-- ----------
--   1. Nova acao `aplicar_producao`: fecha em `ultimo_contrato + 1`,
--      com origem 'BACKFILL_PRODUCAO'. Vale ate 30 dias de distancia.
--   2. Acima de 30 dias segue `divergencia_producao` — reporta e nao
--      escreve. O teto e o do aviso previo legal, nao um numero solto;
--      alem dele a hipotese provavel e data errada no arquivo ou
--      digitacao no login de quem ja saiu, e isso e caso para olho
--      humano. Mesmo teto da 100.
--   3. `divergencia_manual` passa a ser avaliada ANTES das clausulas de
--      producao. Enquanto as duas so reportavam, a ordem era
--      indiferente; agora a de producao escreve, e sem a inversao um
--      desligamento com producao posterior sobrescreveria uma janela
--      MANUAL. A regra "correcao humana nao se desfaz por carga de
--      arquivo" continua acima de tudo.
--   4. `recusada_ordem` passa a ser avaliada contra a data EFETIVA:
--      fechar em `ultimo + 1` tambem nao pode preceder o inicio de uma
--      janela aberta.
--
-- Envelope: dois campos novos, `desligamento.aplicados_por_producao` e
-- `desligamento.divergencias_aplicadas` (nome, data do arquivo, ultimo
-- contrato, data gravada, distancia em dias). Nada removido nem
-- renomeado. `desligamento.divergencias` continua sendo a lista do que
-- NAO foi escrito — depois desta migration, so o caso acima de 30 dias.
--
--
-- EFEITO NUMERICO — LER ANTES DE APLICAR
-- ---------------------------------------
-- Hoje: NENHUM. O arquivo HC_Colaboradores nunca foi importado — medido
-- em 2026-09-08, `consultor_vigencia` tinha ZERO linhas com
-- origem = 'ETL', e essa e a unica porta que as escreve. A funcao muda
-- de comportamento antes da primeira carga, que e o melhor momento
-- possivel para muda-la.
--
-- Na primeira carga o efeito e o oposto do que "fechar mais janelas"
-- sugere: janelas que a 095 deixaria abertas passam a fechar, e cada
-- uma que fecha REDUZ o denominador ponderado da loja a partir da data
-- — o que SOBE a produtividade media. A grandeza foi medida contra o
-- arquivo real na 100: 6 dos 31 desligamentos caiam na regra dos 30
-- dias, quatro deles com producao no PROPRIO dia.
--
-- ASSINATURA INALTERADA (jsonb, text, boolean): CREATE OR REPLACE da
-- mesma funcao. Sem DROP, sem redeploy da Edge Function, sem mudanca na
-- whitelist do angry-man.
--
-- Executar no Supabase SQL Editor, depois da 114.
-- =====================================================

CREATE OR REPLACE FUNCTION public.fn_headcount_replace(
    p_rows             jsonb,
    p_modo_afastamento text    DEFAULT 'SNAPSHOT',
    p_reabrir_ativos   boolean DEFAULT false
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '120s'
AS $fn$
DECLARE
    v_modo        text;
    v_len         integer;
    v_invalidas   jsonb;
    v_afast       jsonb;
    v_afast_env   jsonb;
    v_cad_ins     integer := 0;
    v_cad_upd     integer := 0;
    v_cad_pre     integer := 0;
    v_cad_inalt   integer := 0;
    v_sem_loja    integer := 0;
    v_adm_upd     integer := 0;
    v_adm_new     integer := 0;
    v_desl_upd    integer := 0;
    v_desl_prod   integer := 0;
    v_reabertas   integer := 0;
    v_nao_canon   integer := 0;
    v_desl_aberta integer := 0;
    v_fechadas    integer := 0;
BEGIN
    -- ---- 1. Validacao do envelope ----
    v_modo := upper(btrim(coalesce(p_modo_afastamento, 'SNAPSHOT')));

    IF v_modo NOT IN ('SNAPSHOT', 'UPSERT', 'SKIP') THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format('Modo de afastamento invalido: %s. Use '
                            'SNAPSHOT, UPSERT ou SKIP.', p_modo_afastamento));
    END IF;

    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Payload ausente ou nao e um array JSON.');
    END IF;

    v_len := jsonb_array_length(p_rows);

    IF v_len = 0 THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Arquivo vazio. Nada a aplicar.');
    END IF;

    -- ---- 2. Validacao das linhas, ANTES de escrever qualquer coisa ----
    -- Datas em ISO. `nome` obrigatorio. O bloco de afastamento segue
    -- exatamente o vocabulario da 090 — validado aqui tambem para que a
    -- chamada delegada nunca possa falhar por validacao no meio da
    -- transacao, ja com o cadastro aplicado.
    SELECT jsonb_agg(r) INTO v_invalidas
    FROM jsonb_array_elements(p_rows) r
    WHERE btrim(coalesce(r->>'nome', '')) = ''
       OR (coalesce(r->>'data_admissao', '') <> ''
           AND r->>'data_admissao' !~ '^\d{4}-\d{2}-\d{2}$')
       OR (coalesce(r->>'data_desligamento', '') <> ''
           AND r->>'data_desligamento' !~ '^\d{4}-\d{2}-\d{2}$')
       OR (coalesce(r->>'afastamento_tipo', '') <> ''
           AND upper(btrim(r->>'afastamento_tipo')) NOT IN (
               'AFASTAMENTO_MEDICO', 'LICENCA_MATERNIDADE',
               'LICENCA_NAO_REMUNERADA', 'FERIAS'))
       OR (coalesce(r->>'afastamento_tipo', '') <> ''
           AND coalesce(r->>'afastamento_inicio', '') !~ '^\d{4}-\d{2}-\d{2}$')
       OR (coalesce(r->>'afastamento_fim', '') <> ''
           AND r->>'afastamento_fim' !~ '^\d{4}-\d{2}-\d{2}$')
       OR (coalesce(r->>'loja_id', '') <> ''
           AND r->>'loja_id' !~ '^[0-9a-fA-F-]{36}$');

    IF v_invalidas IS NOT NULL THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Linhas invalidas — nada foi aplicado.',
            'invalidas', v_invalidas);
    END IF;

    -- Uma pessoa duas vezes no mesmo arquivo torna indeterminado qual
    -- data vale. Barra antes de aplicar, em vez de aplicar a ultima.
    SELECT jsonb_agg(DISTINCT r->>'nome') INTO v_invalidas
    FROM jsonb_array_elements(p_rows) r
    WHERE upper(regexp_replace(btrim(r->>'nome'), '[[:space:]]+', ' ', 'g')) IN (
        SELECT upper(regexp_replace(btrim(r2->>'nome'), '[[:space:]]+', ' ', 'g'))
        FROM jsonb_array_elements(p_rows) r2
        WHERE coalesce(r2->>'data_admissao', '') <> ''
           OR coalesce(r2->>'data_desligamento', '') <> ''
        GROUP BY 1 HAVING count(*) > 1);

    IF v_invalidas IS NOT NULL THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Mesma pessoa aparece mais de uma vez com data de '
                     'admissao ou desligamento — qual data vale fica '
                     'indeterminado. Nada foi aplicado.',
            'invalidas', v_invalidas);
    END IF;

    -- ---- 3. Bloco de afastamento: extrai e decide o modo ----
    SELECT jsonb_agg(jsonb_build_object(
               'nome',        btrim(r->>'nome'),
               'tipo',        upper(btrim(r->>'afastamento_tipo')),
               'data_inicio', r->>'afastamento_inicio',
               'data_fim',    nullif(btrim(coalesce(r->>'afastamento_fim', '')), ''),
               'observacao',  nullif(btrim(coalesce(r->>'observacao', '')), '')))
      INTO v_afast
    FROM jsonb_array_elements(p_rows) r
    WHERE coalesce(r->>'afastamento_tipo', '') <> '';

    IF v_modo = 'SNAPSHOT' AND v_afast IS NULL THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Modo SNAPSHOT com bloco de afastamento vazio: '
                     'fecharia todas as janelas abertas de uma vez. Se o '
                     'arquivo nao tem as colunas de afastamento, use modo '
                     'SKIP. Se realmente ninguem esta afastado, encerre as '
                     'janelas com fn_afastamentos_replace em modo UPSERT, '
                     'uma linha por pessoa.');
    END IF;

    -- Serializa com a 090 e com outras cargas (mesmo id; o lock e
    -- re-entrante dentro da transacao, entao a chamada delegada
    -- reaproveita este).
    PERFORM pg_advisory_xact_lock(20260820);

    -- ---- 4. Plano: uma linha por pessoa, com tudo ja resolvido ----
    -- Materializado porque as fases seguintes leem o mesmo cruzamento
    -- varias vezes e `contratos` tem ~141 mil linhas — sem indice util
    -- para filtro por nome, cada leitura seria uma varredura nova.
    -- `ON COMMIT DROP` ja limpa no fim da transacao; este DROP so
    -- importa se a funcao for chamada duas vezes na MESMA transacao
    -- (acontece ao testar no SQL Editor dentro de BEGIN/ROLLBACK).
    -- Checagem explicita em vez de `DROP TABLE IF EXISTS pg_temp.x`:
    -- na primeira chamada da sessao o schema temporario ainda nao
    -- existe, e `pg_my_temp_schema()` devolve 0 sem erro.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relname = 'hc_plan'
          AND c.relnamespace = pg_catalog.pg_my_temp_schema()
    ) THEN
        DROP TABLE pg_temp.hc_plan;
    END IF;

    CREATE TEMP TABLE hc_plan ON COMMIT DROP AS
    WITH payload AS (
        SELECT
            upper(regexp_replace(btrim(r->>'nome'),
                                 '[[:space:]]+', ' ', 'g'))          AS nn,
            btrim(r->>'nome')                                        AS nome,
            nullif(btrim(coalesce(r->>'loja_id', '')), '')::uuid     AS loja_id,
            nullif(btrim(coalesce(r->>'status', '')), '')            AS status,
            nullif(coalesce(r->>'data_admissao', ''), '')::date      AS adm,
            nullif(coalesce(r->>'data_desligamento', ''), '')::date  AS desl
        FROM jsonb_array_elements(p_rows) r
    ),
    prod AS (
        -- `contratos`, nao `v_contratos_dashboard`: a pergunta e
        -- PRESENCA, nao producao paga. Data e `data_cadastro` (registro
        -- do contrato), nunca `data_status_pagamento` — pagamento
        -- arrasta depois da saida. Mesmo piso de 2025-01-01 da 087.
        SELECT
            upper(regexp_replace(btrim(cs.nome),
                                 '[[:space:]]+', ' ', 'g')) AS nn,
            min(ct.data_cadastro::date) AS primeiro,
            max(ct.data_cadastro::date) AS ultimo
        FROM public.contratos ct
        JOIN public.consultores cs ON cs.id = ct.consultor_id
        WHERE ct.data_cadastro >= DATE '2025-01-01'
        GROUP BY 1
    ),
    primeira AS (
        SELECT DISTINCT ON (v.nome_normalizado)
            v.nome_normalizado AS nn,
            v.id               AS jan_id,
            v.vigencia_inicio  AS jan_ini,
            v.vigencia_fim     AS jan_fim,
            v.origem           AS jan_origem
        FROM public.consultor_vigencia v
        ORDER BY v.nome_normalizado, v.vigencia_inicio, v.id
    ),
    abertas AS (
        SELECT
            v.nome_normalizado     AS nn,
            count(*)::integer      AS n_abertas,
            max(v.vigencia_inicio) AS max_ini_aberta,
            count(*) FILTER (WHERE v.origem = 'MANUAL')::integer
                                   AS n_abertas_manual
        FROM public.consultor_vigencia v
        WHERE v.vigencia_fim IS NULL
        GROUP BY 1
    ),
    ultima_fechada AS (
        SELECT DISTINCT ON (v.nome_normalizado)
            v.nome_normalizado AS nn,
            v.id               AS uf_id,
            v.origem           AS uf_origem,
            v.loja_id          AS uf_loja_id
        FROM public.consultor_vigencia v
        WHERE v.vigencia_fim IS NOT NULL
        ORDER BY v.nome_normalizado, v.vigencia_fim DESC, v.id
    )
    SELECT
        p.nn, p.nome, p.loja_id, p.status, p.adm, p.desl,
        -- Desligado e SO 'DESLIG%'. Ver cabecalho (caso HELOINA).
        (upper(coalesce(p.status, '')) LIKE 'DESLIG%')            AS eh_desligado,
        (p.status IS NOT NULL
         AND upper(p.status) NOT LIKE 'ATIVO%'
         AND upper(p.status) NOT LIKE 'DESLIG%')                  AS status_nao_canonico,
        pr.primeiro, pr.ultimo,
        pf.jan_id, pf.jan_ini, pf.jan_fim, pf.jan_origem,
        coalesce(ab.n_abertas, 0)                                 AS n_abertas,
        coalesce(ab.n_abertas_manual, 0)                          AS n_abertas_manual,
        ab.max_ini_aberta,
        uf.uf_id, uf.uf_origem, uf.uf_loja_id,
        -- Classificacao da ADMISSAO
        CASE
            WHEN p.adm IS NULL                       THEN 'sem_data'
            -- Producao vem ANTES de tudo: contrato digitado antes da
            -- admissao declarada desmente a planilha, tenha a pessoa
            -- janela ou nao.
            WHEN pr.primeiro IS NOT NULL
             AND pr.primeiro < p.adm                 THEN 'divergencia_producao'
            WHEN pf.jan_id IS NULL                   THEN 'criar_janela'
            -- Correcao humana nao se desfaz por carga de arquivo. Mesma
            -- regra da 077: divergencia se reporta, nao se aplica.
            WHEN pf.jan_origem = 'MANUAL'
             AND pf.jan_ini <> p.adm                 THEN 'divergencia_manual'
            WHEN pf.jan_fim IS NOT NULL
             AND p.adm >= pf.jan_fim                 THEN 'recusada_ordem'
            WHEN pf.jan_ini = p.adm
             AND pf.jan_origem = 'ETL'               THEN 'sem_efeito'
            ELSE                                          'aplicar'
        END AS acao_adm,
        -- Data que sera GRAVADA. Igual a do arquivo, exceto quando a
        -- producao contradiz: ai e o dia seguinte ao ultimo contrato.
        -- Fica numa coluna propria porque o UPDATE precisa dela e uma
        -- CASE nao pode referenciar `acao_desl` no mesmo nivel do SELECT.
        CASE
            WHEN p.desl IS NULL                      THEN NULL
            WHEN pr.ultimo IS NOT NULL
             AND pr.ultimo >= p.desl
             AND (pr.ultimo - p.desl) <= 30          THEN pr.ultimo + 1
            ELSE                                          p.desl
        END AS desl_efetiva,
        -- Classificacao do DESLIGAMENTO
        --
        -- MUDANCA 115 — ordem e desfecho. Ate a 095, producao posterior
        -- ao desligamento declarado era `divergencia_producao` e NAO
        -- escrevia; a 100 ja resolvia o mesmo conflito escrevendo a data
        -- derivada. Duas portas, dois desfechos para o fato identico.
        -- Decisao do usuario (2026-09-09): vale a da 100 — producao
        -- prova presenca.
        --
        -- `divergencia_manual` SUBIU para antes das clausulas de
        -- producao. Enquanto as duas apenas reportavam, a ordem era
        -- indiferente; agora a de producao ESCREVE, e sem a inversao ela
        -- passaria por cima de uma janela MANUAL — exatamente a regra
        -- que a 095 existe para sustentar.
        CASE
            WHEN p.desl IS NULL                       THEN 'sem_data'
            WHEN coalesce(ab.n_abertas, 0) = 0        THEN 'ja_fechada'
            WHEN coalesce(ab.n_abertas_manual, 0) > 0 THEN 'divergencia_manual'
            -- Acima de 30 dias nao ha aviso previo que explique a
            -- distancia: continua recusa, como na 100.
            WHEN pr.ultimo IS NOT NULL
             AND pr.ultimo >= p.desl
             AND (pr.ultimo - p.desl) > 30            THEN 'divergencia_producao'
            -- Ordem avaliada contra a data EFETIVA, nao a do arquivo:
            -- fechar em `ultimo + 1` tambem nao pode preceder o inicio
            -- de uma janela aberta.
            WHEN ab.max_ini_aberta >= (
                     CASE WHEN pr.ultimo IS NOT NULL AND pr.ultimo >= p.desl
                          THEN pr.ultimo + 1 ELSE p.desl END
                 )                                    THEN 'recusada_ordem'
            WHEN pr.ultimo IS NOT NULL
             AND pr.ultimo >= p.desl                  THEN 'aplicar_producao'
            ELSE                                           'aplicar'
        END AS acao_desl
    FROM payload p
    LEFT JOIN prod           pr ON pr.nn = p.nn
    LEFT JOIN primeira       pf ON pf.nn = p.nn
    LEFT JOIN abertas        ab ON ab.nn = p.nn
    LEFT JOIN ultima_fechada uf ON uf.nn = p.nn;

    -- ---- 5. Cadastro (a foto) ----
    -- Sem loja_id nao ha como upsertar: `uq_consultores_nome_loja` e
    -- (nome, loja_id) e NULL nao dispara ON CONFLICT (NULLS DISTINCT),
    -- entao a linha duplicaria em silencio a cada carga.
    SELECT count(*)::integer INTO v_sem_loja
    FROM pg_temp.hc_plan WHERE loja_id IS NULL;

    -- Plano do cadastro, deduplicado UMA vez. A 094 deduplicava dentro
    -- do INSERT (`DISTINCT ON`) e contava fora dele, com um
    -- `count(DISTINCT ...)` separado — duas deduplicacoes independentes
    -- que podiam eleger linhas diferentes quando a mesma (pessoa, loja)
    -- vinha duas vezes no arquivo com status diferente. Agora conta e
    -- escreve a partir da MESMA linha, por construcao.
    --
    -- `DISTINCT ON` continua sendo necessario pelo motivo original: a
    -- mesma (pessoa, loja) duas vezes faria ON CONFLICT DO UPDATE tocar
    -- a mesma linha duas vezes na mesma instrucao, que o Postgres recusa.
    --
    -- Sobre o `RETURNING xmax = 0`: segue descartado (094) — distinguiria
    -- insert de update numa passada, mas depende de detalhe interno nao
    -- garantido pela documentacao.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relname = 'hc_cad'
          AND c.relnamespace = pg_catalog.pg_my_temp_schema()
    ) THEN
        DROP TABLE pg_temp.hc_cad;
    END IF;

    CREATE TEMP TABLE hc_cad ON COMMIT DROP AS
    SELECT DISTINCT ON (pl.nome, pl.loja_id)
           pl.nome,
           pl.loja_id,
           c.status                                    AS status_atual,
           -- MUDANCA 2, em uma linha: se a planilha nao diz nada sobre
           -- o status, o valor ATUAL do banco e preservado. 'Ativo (a)'
           -- passa a valer somente para pessoa NOVA.
           coalesce(pl.status, c.status, 'Ativo (a)')  AS status_final,
           (c.id IS NOT NULL)                          AS existe
    FROM pg_temp.hc_plan pl
    LEFT JOIN public.consultores c
           ON c.nome = pl.nome AND c.loja_id = pl.loja_id
    WHERE pl.loja_id IS NOT NULL
    ORDER BY pl.nome, pl.loja_id;

    SELECT (count(*) FILTER (WHERE existe))::integer,
           (count(*) FILTER (WHERE existe
                             AND status_atual IS DISTINCT FROM status_final))::integer
      INTO v_cad_pre, v_cad_upd
    FROM pg_temp.hc_cad;

    v_cad_inalt := v_cad_pre - v_cad_upd;

    -- MUDANCA 3 — o `WHERE` do DO UPDATE. Linha cujo status nao mudou
    -- nao e reescrita, e o trigger `trg_consultores_updated_at` nao
    -- dispara. Sem ele, um upload carimba now() em TODAS as linhas na
    -- mesma instrucao e, com isso, iguala todos os `updated_at`.
    --
    -- Isso importa fora do banco: `_colapsar_cadastro_recente`
    -- (src/dashboard/loaders.py) escolhe, entre linhas duplicadas da
    -- mesma pessoa, a de `updated_at` mais recente para decidir se ela
    -- e ativa — com comparacao ESTRITA, entao empate deixa vencer a
    -- primeira linha que a query devolver, ordem que o Postgres nao
    -- garante. Medido em 2026-08-25, antes de qualquer carga: 328
    -- pessoas em 424 linhas, 78 com cadastro duplicado e 27 dessas com
    -- linhas 'Ativo (a)' E 'Desligado (a)' ao mesmo tempo. Um upload
    -- sem esta clausula poderia devolver 27 desligados ao universo de
    -- ativos do dashboard — e de forma instavel entre dois refreshes.
    INSERT INTO public.consultores AS tgt (nome, loja_id, status)
    SELECT nome, loja_id, status_final FROM pg_temp.hc_cad
    ON CONFLICT (nome, loja_id) DO UPDATE
        SET status = EXCLUDED.status
        WHERE tgt.status IS DISTINCT FROM EXCLUDED.status;
    GET DIAGNOSTICS v_cad_ins = ROW_COUNT;
    v_cad_ins := v_cad_ins - v_cad_upd;

    SELECT count(*)::integer INTO v_nao_canon
    FROM pg_temp.hc_plan WHERE status_nao_canonico;

    -- ---- 6. Admissao ----
    -- Recua (ou avanca) o inicio da PRIMEIRA janela e marca ETL, que e
    -- o que apaga a licenca de BACKFILL_CENSURADO.
    UPDATE public.consultor_vigencia v
    SET vigencia_inicio = pl.adm,
        origem          = 'ETL'
    FROM pg_temp.hc_plan pl
    WHERE v.id = pl.jan_id
      AND pl.acao_adm = 'aplicar';
    GET DIAGNOSTICS v_adm_upd = ROW_COUNT;

    -- Pessoa sem nenhuma janela: contratado que ainda nao vendeu. E o
    -- caso que hoje simplesmente nao existe no denominador.
    INSERT INTO public.consultor_vigencia
        (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
    SELECT pl.nome, pl.loja_id, pl.adm, NULL, 'ETL'
    FROM pg_temp.hc_plan pl
    WHERE pl.acao_adm = 'criar_janela'
      AND pl.loja_id IS NOT NULL
      AND NOT pl.eh_desligado;
    GET DIAGNOSTICS v_adm_new = ROW_COUNT;

    -- ---- 7. Desligamento ----
    -- Fecha TODAS as janelas abertas da pessoa: sair da empresa encerra
    -- o vinculo com qualquer loja, nao so com a ultima. Janela cujo
    -- inicio e posterior a data cai fora pelo WHERE e ja foi contada
    -- como recusada na classificacao.
    -- MUDANCA 115: fecha na data EFETIVA e carimba a procedencia dela.
    -- `origem` diz de onde veio a DATA, nao de onde veio o evento — a
    -- mesma frase da 100. Data do arquivo, 'ETL'; data derivada do
    -- ultimo contrato, 'BACKFILL_PRODUCAO'.
    UPDATE public.consultor_vigencia v
    SET vigencia_fim = pl.desl_efetiva,
        origem       = CASE WHEN pl.acao_desl = 'aplicar_producao'
                            THEN 'BACKFILL_PRODUCAO' ELSE 'ETL' END
    FROM pg_temp.hc_plan pl
    WHERE v.nome_normalizado = pl.nn
      AND v.vigencia_fim IS NULL
      AND pl.acao_desl IN ('aplicar', 'aplicar_producao')
      AND v.vigencia_inicio < pl.desl_efetiva;
    GET DIAGNOSTICS v_desl_upd = ROW_COUNT;

    -- DISTINCT nn, nao count(*): `hc_plan` tem uma linha por linha do
    -- ARQUIVO, e quem aparece em duas lojas aparece em duas linhas. E o
    -- mesmo cuidado que `desligados_com_janela_aberta` ja toma na 095.
    SELECT count(DISTINCT nn)::integer INTO v_desl_prod
    FROM pg_temp.hc_plan WHERE acao_desl = 'aplicar_producao';

    -- ---- 8. Diagnostico / reabertura ----
    SELECT count(*)::integer INTO v_fechadas
    FROM pg_temp.hc_plan
    WHERE NOT eh_desligado AND desl IS NULL AND n_abertas = 0
      AND uf_id IS NOT NULL;

    -- MUDANCA 1 — o espelho de `ativos_com_janela_fechada`, que a 094
    -- nao tinha. Planilha diz que a pessoa saiu, o ledger diz que ela
    -- ainda esta la, e DATA_DESLIGAMENTO nao veio: nao ha o que
    -- aplicar, e antes disto a funcao simplesmente nao dizia nada.
    --
    -- Por que nao dizer nada e caro: fn_headcount_ponderado (091) le SO
    -- os ledgers, nunca `consultores.status`. Janela aberta sem
    -- producao pesa 1,0 (R2: silencio nao reduz nada), entao a pessoa
    -- segue dividindo a producao da loja depois de ter saido. E o
    -- rebuild da 087, que era o que fechava essas janelas, fica
    -- proibido a partir da primeira escrita ETL.
    --
    -- `desl IS NULL` de proposito: data preenchida que nao passou ja
    -- sai como divergencia ou recusa no bloco `desligamento`. Este
    -- contador e o silencio, nao o conflito.
    --
    -- Conta PESSOA, nao linha, e exige que NENHUMA linha do arquivo a
    -- declare ativa: desligado numa loja e ativo em outra e
    -- transferencia, nao saida.
    SELECT count(DISTINCT pl.nn)::integer INTO v_desl_aberta
    FROM pg_temp.hc_plan pl
    WHERE pl.eh_desligado
      AND pl.desl IS NULL
      AND pl.n_abertas > 0
      AND NOT EXISTS (SELECT 1 FROM pg_temp.hc_plan p2
                      WHERE p2.nn = pl.nn AND NOT p2.eh_desligado);

    IF p_reabrir_ativos THEN
        -- So inferencia se desfaz. E so quando nao ha ja uma janela
        -- aberta para a mesma (pessoa, loja) — `uq_cv_consultor_loja_aberta`.
        UPDATE public.consultor_vigencia v
        SET vigencia_fim = NULL
        FROM pg_temp.hc_plan pl
        WHERE v.id = pl.uf_id
          AND NOT pl.eh_desligado
          AND pl.desl IS NULL
          AND pl.n_abertas = 0
          AND pl.uf_origem LIKE 'BACKFILL%'
          AND NOT EXISTS (
              SELECT 1 FROM public.consultor_vigencia w
              WHERE w.nome_normalizado = v.nome_normalizado
                AND w.vigencia_fim IS NULL
                AND coalesce(w.loja_id, '00000000-0000-0000-0000-000000000000'::uuid)
                  = coalesce(v.loja_id, '00000000-0000-0000-0000-000000000000'::uuid));
        GET DIAGNOSTICS v_reabertas = ROW_COUNT;
    END IF;

    -- ---- 9. Afastamento (delegado a 090) ----
    IF v_modo = 'UPSERT' AND v_afast IS NULL THEN
        -- Correcao pontual sem nenhuma linha a corrigir: nada a fazer.
        -- Repassar NULL faria a 090 devolver erro de payload e abortar
        -- uma carga que esta correta.
        v_afast_env := jsonb_build_object(
            'modo', 'UPSERT',
            'nota', 'Nenhuma linha de afastamento no arquivo; nada a corrigir.');
    ELSIF v_modo <> 'SKIP' THEN
        v_afast_env := public.fn_afastamentos_replace(v_afast, v_modo);

        -- Validacao ja passou na fase 2; um erro aqui e estado
        -- inesperado e nao pode virar sucesso parcial.
        IF v_afast_env->>'error' IS NOT NULL THEN
            RAISE EXCEPTION 'Bloco de afastamento recusado: %',
                v_afast_env->>'error';
        END IF;
    ELSE
        v_afast_env := jsonb_build_object(
            'modo', 'SKIP',
            'nota', 'Arquivo sem colunas de afastamento; ledger intocado.');
    END IF;

    -- ---- 10. Envelope ----
    -- Agregado de proposito: pode ser logado inteiro. Nenhum `tipo` nem
    -- `observacao` sai daqui — sao dado pessoal sensivel (089).
    RETURN jsonb_build_object(
        'count', v_len,
        'cadastro', jsonb_build_object(
            'inseridos',   v_cad_ins,
            'atualizados', v_cad_upd,
            -- Campo novo: linha que veio no arquivo e ja estava igual no
            -- banco. Antes ela entrava em `atualizados` e o envelope
            -- reportava a foto inteira como alterada a cada upload.
            'inalterados', v_cad_inalt,
            'sem_loja',    v_sem_loja),
        'admissao', jsonb_build_object(
            'aplicadas',       v_adm_upd,
            'janelas_criadas', v_adm_new,
            'sem_data',       (SELECT count(*) FROM pg_temp.hc_plan
                               WHERE acao_adm = 'sem_data'),
            'sem_efeito',     (SELECT count(*) FROM pg_temp.hc_plan
                               WHERE acao_adm = 'sem_efeito'),
            'recusadas',      (SELECT count(*) FROM pg_temp.hc_plan
                               WHERE acao_adm = 'recusada_ordem'),
            'divergencias_manual', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                   'nome', nome, 'planilha', adm,
                                   'ledger', jan_ini)), '[]'::jsonb)
                               FROM pg_temp.hc_plan
                               WHERE acao_adm = 'divergencia_manual'),
            'divergencias',   (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                   'nome', nome, 'planilha', adm,
                                   'primeiro_contrato', primeiro)), '[]'::jsonb)
                               FROM pg_temp.hc_plan
                               WHERE acao_adm = 'divergencia_producao')),
        'desligamento', jsonb_build_object(
            'aplicados',    v_desl_upd,
            -- Quantas PESSOAS fecharam numa data diferente da que o
            -- arquivo trouxe. Quem importa precisa ver isso: a data
            -- gravada nao e a que ele digitou (exigencia da 100).
            'aplicados_por_producao', v_desl_prod,
            'divergencias_aplicadas', (SELECT coalesce(jsonb_agg(
                                jsonb_build_object(
                                    'nome', nome,
                                    'planilha', desl,
                                    'ultimo_contrato', ultimo,
                                    'data_aplicada', desl_efetiva,
                                    'dias', (ultimo - desl))), '[]'::jsonb)
                            FROM pg_temp.hc_plan
                            WHERE acao_desl = 'aplicar_producao'),
            'ja_fechadas', (SELECT count(*) FROM pg_temp.hc_plan
                            WHERE acao_desl = 'ja_fechada'),
            'recusados',   (SELECT count(*) FROM pg_temp.hc_plan
                            WHERE acao_desl = 'recusada_ordem'),
            'divergencias_manual', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                'nome', nome, 'planilha', desl)), '[]'::jsonb)
                            FROM pg_temp.hc_plan
                            WHERE acao_desl = 'divergencia_manual'),
            -- Continua sendo a lista do que NAO foi escrito. Depois da
            -- 115 ela guarda so o caso patologico (> 30 dias); o que a
            -- producao ajustou e escreveu esta em
            -- `divergencias_aplicadas`, acima.
            'divergencias',(SELECT coalesce(jsonb_agg(jsonb_build_object(
                                'nome', nome, 'planilha', desl,
                                'ultimo_contrato', ultimo,
                                'dias', (ultimo - desl))), '[]'::jsonb)
                            FROM pg_temp.hc_plan
                            WHERE acao_desl = 'divergencia_producao')),
        'afastamento', v_afast_env,
        'diagnostico', jsonb_build_object(
            'ativos_com_janela_fechada',    v_fechadas,
            'desligados_com_janela_aberta', v_desl_aberta,
            -- Lista acionavel: `ultimo_contrato` e exatamente a data que
            -- o RH deveria ter posto em DATA_DESLIGAMENTO (era o
            -- fallback do backfill). Nome de consultor nao e dado
            -- sensivel — `tipo` e `observacao` de afastamento sao, e
            -- continuam fora do envelope.
            'desligados_sem_data', (
                SELECT coalesce(jsonb_agg(jsonb_build_object(
                           'nome',            d.nome,
                           'janelas_abertas', d.n_abertas,
                           'ultimo_contrato', d.ultimo)
                       ORDER BY d.nome), '[]'::jsonb)
                FROM (
                    SELECT DISTINCT ON (pl.nn)
                           pl.nn, pl.nome, pl.n_abertas, pl.ultimo
                    FROM pg_temp.hc_plan pl
                    WHERE pl.eh_desligado
                      AND pl.desl IS NULL
                      AND pl.n_abertas > 0
                      AND NOT EXISTS (SELECT 1 FROM pg_temp.hc_plan p2
                                      WHERE p2.nn = pl.nn
                                        AND NOT p2.eh_desligado)
                    ORDER BY pl.nn, pl.nome
                ) d),
            'reabertas',                    v_reabertas,
            'status_nao_canonico',          v_nao_canon),
        'error', NULL);
END;
$fn$;

COMMENT ON FUNCTION public.fn_headcount_replace(jsonb, text, boolean) IS
    'Porta de entrada do HC_Colaboradores: numa transacao so atualiza '
    '`consultores` (a foto), grava admissao/desligamento em '
    '`consultor_vigencia` com origem ETL, e delega o bloco de afastamento a '
    'fn_afastamentos_replace. Coluna vazia mantem o fallback; coluna '
    'preenchida vence a inferencia — mas nunca vence PRODUCAO (contrato '
    'antes da admissao declarada vira divergencia, nao escrita; contrato '
    'DEPOIS do desligamento declarado fecha a janela em ultimo_contrato+1 '
    'com origem BACKFILL_PRODUCAO ate 30 dias, e acima disso vira '
    'divergencia — doutrina da 100, adotada aqui pela 115). Desligado e '
    'so status LIKE DESLIG%; licenca vira afastamento, nunca saida. '
    'p_modo_afastamento SKIP nao toca no ledger de afastamento. '
    'p_reabrir_ativos e ato explicito. 095: status so muda quando a planilha '
    'traz valor (vazio preserva o banco); linha inalterada NAO e reescrita, '
    'para nao igualar os updated_at que dashboard e Caderno usam como '
    'desempate de cadastro duplicado; e o envelope passa a reportar '
    '`desligados_com_janela_aberta`, que a 091 contaria com peso 1,0. '
    'SECURITY DEFINER; EXECUTE so para service_role. NAO criar sobrecarga '
    '(ver 077/090/094).';

-- Idempotente: CREATE OR REPLACE preserva os grants da 094. Repetidos
-- aqui para que o arquivo continue sendo a descricao completa do objeto.
REVOKE ALL ON FUNCTION public.fn_headcount_replace(jsonb, text, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_headcount_replace(jsonb, text, boolean)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_headcount_replace(jsonb, text, boolean)
    TO service_role;



-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) Dry-run do arquivo real, sem escrever nada. `p_modo_afastamento`
--    = 'SKIP' isola o bloco de desligamento:
--
--    -- SELECT public.fn_headcount_replace('<payload>', 'SKIP', false)
--    --        -> 'desligamento';
--    --
--    -- comparar com a execucao anterior a esta migration:
--    --   * `divergencias` deve ENCOLHER (sai tudo que estiver a <= 30 dias)
--    --   * `aplicados_por_producao` deve receber exatamente esses casos
--    --   * `aplicados` sobe pelo mesmo tanto
--    --   * a soma `aplicados + divergencias + recusados + ja_fechadas +
--    --     divergencias_manual` nao muda
--
-- 2) A procedencia distingue as duas datas:
--
--    SELECT origem, count(*) FROM consultor_vigencia
--     WHERE vigencia_fim IS NOT NULL GROUP BY origem;
--    -- depois da primeira carga: 'ETL' = fechou na data do arquivo;
--    --                           'BACKFILL_PRODUCAO' = fechou pela producao
--
-- 3) A inversao de ordem protege MANUAL. Em ambiente de teste, monte uma
--    pessoa com janela MANUAL aberta E producao posterior a data do
--    arquivo:
--
--    -- esperado: acao_desl = 'divergencia_manual', a janela NAO fecha, e
--    --           o nome sai em `divergencias_manual`.
--    -- ANTES desta migration cairia em `divergencia_producao` — que
--    -- tambem nao escrevia, entao o estado final e o mesmo; o que muda e
--    -- que agora ele nao pode virar escrita.
--
-- 4) Nenhuma janela ficou invalida (fim <= inicio). O CHECK
--    chk_cv_vigencia_ordem ja garante, mas a consulta confirma que a
--    clausula de ordem contra a data efetiva esta fazendo efeito:
--
--    SELECT count(*) FROM consultor_vigencia
--     WHERE vigencia_fim IS NOT NULL AND vigencia_fim <= vigencia_inicio;
--    -- esperado: 0
--
-- 5) Rematerializar o Caderno das competencias afetadas. Uma janela
--    atravessa varias — fechar em setembro muda o denominador de maio:
--
--    SELECT public.fn_materializar_caderno(<mes>, <ano>);
