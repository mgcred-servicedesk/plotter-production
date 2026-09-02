-- =====================================================
-- Migracao 095: fn_headcount_replace — guardas de cadastro
--               (CREATE OR REPLACE da 094, MESMA assinatura)
--
-- Tres correcoes na porta de entrada do HC_Colaboradores, todas
-- medidas contra o banco real em 2026-08-25, ANTES da primeira carga.
-- Nenhuma delas muda numero publicado hoje: as duas primeiras nascem
-- em zero e a terceira reduz escrita. Sao guardas instaladas enquanto
-- o estado esta limpo, que e o unico momento em que instalar guarda
-- sai de graca.
--
-- Assinatura INALTERADA — (jsonb, text, boolean). Nao ha sobrecarga
-- nova, nao ha DROP, e a chamada atual do angry-man continua valendo
-- sem redeploy. Ver o aviso da 094: acrescentar parametro criaria
-- funcao NOVA e quebraria a chamada com "function is not unique".
--
--
-- O ESTADO MEDIDO (2026-08-25, leitura pura)
-- -------------------------------------------
--   consultores            424 linhas / 328 pessoas
--                          78 pessoas com cadastro duplicado
--                          27 delas com 'Ativo (a)' E 'Desligado (a)'
--   consultor_vigencia     395 janelas, 167 pessoas com janela aberta
--   origem das janelas     267 BACKFILL_PRODUCAO, 124 BACKFILL_CENSURADO,
--                          1 BACKFILL_PISO, 3 MANUAL — ZERO 'ETL'
--   peso 08/2026           116,33 para 127 cabecas (DU=21)
--
-- O ledger ainda nao recebeu uma unica escrita de ETL. Cadastro e
-- ledger estao coerentes: pessoas com cadastro 'Desligado (a)' e
-- janela ainda aberta = 0. E por isso que as guardas cabem agora.
--
--
-- MUDANCA 1 — `desligados_com_janela_aberta` no diagnostico
-- ---------------------------------------------------------
-- A 094 devolve `ativos_com_janela_fechada` (planilha diz ativo, ledger
-- diz fechado) e nada para o caso inverso, que e o que vai acontecer em
-- toda carga enquanto o RH nao preencher DATA_DESLIGAMENTO: planilha
-- diz 'Desligado (a)', o ledger tem janela aberta, e a coluna de data
-- veio vazia. Sem data nao ha o que aplicar — correto — mas a 094
-- tambem nao dizia nada, e o silencio aqui e caro:
--
--   fn_headcount_ponderado (091) le SO os ledgers, nunca
--   `consultores.status`. Janela aberta sem producao pesa 1,0 (R2:
--   silencio nao reduz nada). A pessoa segue dividindo a producao da
--   loja depois de ter saido.
--
-- E o rebuild da 087, que era o que fechava essas janelas, fica
-- proibido a partir da primeira escrita 'ETL' (docs/HEADCOUNT_ETL.md
-- secao 1). Ou seja: o caminho antigo fecha e o novo nao abre.
--
-- Dimensao do desvio, medida pelo fluxo historico de saidas
-- (fechamento da ultima janela, pessoa sem janela aberta): media de
-- 8,8 pessoas/mes nos ultimos 12 meses, pico de 17 em 07/2026. Sobre o
-- peso de 116,33 de 08/2026:
--
--   +1 mes   -> 125,1  (+7,6%)    produtividade por cabeca -7,0%
--   +3 meses -> 142,7  (+22,7%)   produtividade por cabeca -18,5%
--   +6 meses -> 169,1  (+45,4%)   produtividade por cabeca -31,2%
--
-- Nao e queda de desempenho: e gente que saiu continuando a dividir a
-- producao. O contador nasce em 0 e qualquer valor diferente de zero
-- numa carga futura e sinal puro, sem ruido historico para separar.
--
-- O contador NAO fecha janela. Fechar exigiria uma data, e a unica
-- disponivel seria inferida (fim do mes do ultimo contrato) — o oposto
-- de "declarado vence inferido". Fechar por status seria parametro
-- novo, logo assinatura nova, logo DROP + redeploy coordenado. Decisao
-- separada, de proposito. Esta migration faz o numero APARECER; agir
-- sobre ele continua sendo ato explicito.
--
--
-- MUDANCA 2 — status so muda quando a planilha fala
-- --------------------------------------------------
-- A 094 faz `SET status = EXCLUDED.status` sem condicao, sobre
-- `coalesce(status, 'Ativo (a)')`. Combinado com o default do
-- importador (import-cadastros.ts manda "Ativo (a)" quando a celula
-- esta vazia), celula em branco REATIVA quem esta desligado.
--
-- Agora o status final e `coalesce(planilha, banco, 'Ativo (a)')`:
-- planilha calada preserva o valor atual, e 'Ativo (a)' vale somente
-- para pessoa NOVA. E a mesma precedencia que a 094 ja aplica as datas
-- ("vazio nunca significa 'nao tem'") — o status era a unica coluna
-- fora dela.
--
-- Medido hoje: 0 linhas com status vazio, entao a mudanca nao altera
-- nada agora. Ela existe porque o arquivo do RH vai mudar de forma, e
-- coluna em branco e o modo mais comum de um arquivo mudar de forma.
-- Precisa do patch correspondente no angry-man (mandar null em vez de
-- "Ativo (a)") para ter efeito de ponta a ponta.
--
--
-- MUDANCA 3 — nao carimbar `updated_at` a toa
-- --------------------------------------------
-- A de efeito imediato, e a unica que protege numero que JA e lido.
--
-- A 094 faz ON CONFLICT DO UPDATE em todas as linhas da foto numa
-- instrucao. O trigger `trg_consultores_updated_at` dispara em toda
-- UPDATE, mude o valor ou nao — entao um upload iguala os 424
-- `updated_at` no mesmo now(). E `updated_at` e criterio de desempate
-- em DOIS lugares, para escolher qual linha da pessoa duplicada vale:
--
--   * Dashboard — `_colapsar_cadastro_recente`
--     (src/dashboard/loaders.py): comparacao ESTRITA (`>`), entao
--     empate deixa vencer a PRIMEIRA linha que a query devolver, ordem
--     que o Postgres nao garante. Fica instavel entre dois refreshes.
--
--   * Caderno / bereshit — `obter_caderno_fechamento`
--     (CTE `consultores_mais_recentes`, migrations 073/075/092):
--     `ORDER BY nome_normalizado, updated_at DESC NULLS LAST, id DESC`.
--     Empate cai no `id DESC`, um UUID aleatorio. Deterministico, mas
--     arbitrario em relacao ao fato.
--
-- Simulado sobre o banco de hoje, igualando todos os updated_at: o
-- cadastro ativo salta de 167 para 182 pessoas — 16 desligados viram
-- ativos (HELOINA entre eles) e 1 ativa vira desligada (ERICA, cujas
-- janelas MANUAL as 088/089 foram escritas para proteger).
--
-- No Caderno isso NAO desloca `weightedHeadcount` nem `productivity`,
-- que vem da 091 e leem so os ledgers. Desloca o bloco de auditoria:
-- `headcountDiagnostics.activeRegistered` e `countedInRegistry`, e com
-- eles a identidade da 075. No dashboard desloca o universo de ativos
-- de verdade, que e o que alimenta as visoes de controle.
--
-- A correcao e uma clausula: `WHERE tgt.status IS DISTINCT FROM
-- EXCLUDED.status`. Linha que nao mudou nao e reescrita, o trigger nao
-- dispara, e o historico de `updated_at` continua tendo sinal. No
-- cenario simulado (cadastro de hoje como arquivo) `atualizados` cai de
-- 424 para 0.
--
-- Efeito colateral bem-vindo: `cadastro.atualizados` passa a contar
-- mudanca real. O campo novo `inalterados` recebe o resto, entao
-- inseridos + atualizados + inalterados fecha exatamente contra o
-- numero de pares (pessoa, loja) DISTINTOS com loja resolvida — o
-- que a funcao de fato escreve. Linha sem loja segue em `sem_loja`.
--
--
-- COMPATIBILIDADE DO ENVELOPE
-- ----------------------------
-- Somente CAMPOS NOVOS: `cadastro.inalterados`,
-- `diagnostico.desligados_com_janela_aberta` e
-- `diagnostico.desligados_sem_data`. Nenhum campo removido ou
-- renomeado, nenhum tipo alterado. O angry-man le chaves nomeadas e
-- ignora o que nao conhece, entao a versao atual dele continua
-- funcionando sem redeploy — apenas nao mostra os campos novos.
--
-- `atualizados` muda de SIGNIFICADO (linhas tocadas -> linhas
-- alteradas). Nenhuma decisao automatica depende dele; ele so alimenta
-- o `inserted`/`updated` que o importador exibe.
--
-- Depende de: 094 (esta funcao), 086/087 (ledger), 089/090
-- (afastamento). Executar no Supabase SQL Editor, depois da 094.
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
        -- Classificacao do DESLIGAMENTO
        CASE
            WHEN p.desl IS NULL                      THEN 'sem_data'
            WHEN coalesce(ab.n_abertas, 0) = 0       THEN 'ja_fechada'
            WHEN pr.ultimo IS NOT NULL
             AND pr.ultimo >= p.desl                 THEN 'divergencia_producao'
            WHEN coalesce(ab.n_abertas_manual, 0) > 0 THEN 'divergencia_manual'
            WHEN ab.max_ini_aberta >= p.desl         THEN 'recusada_ordem'
            ELSE                                          'aplicar'
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
    UPDATE public.consultor_vigencia v
    SET vigencia_fim = pl.desl,
        origem       = 'ETL'
    FROM pg_temp.hc_plan pl
    WHERE v.nome_normalizado = pl.nn
      AND v.vigencia_fim IS NULL
      AND pl.acao_desl = 'aplicar'
      AND v.vigencia_inicio < pl.desl;
    GET DIAGNOSTICS v_desl_upd = ROW_COUNT;

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
            'ja_fechadas', (SELECT count(*) FROM pg_temp.hc_plan
                            WHERE acao_desl = 'ja_fechada'),
            'recusados',   (SELECT count(*) FROM pg_temp.hc_plan
                            WHERE acao_desl = 'recusada_ordem'),
            'divergencias_manual', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                'nome', nome, 'planilha', desl)), '[]'::jsonb)
                            FROM pg_temp.hc_plan
                            WHERE acao_desl = 'divergencia_manual'),
            'divergencias',(SELECT coalesce(jsonb_agg(jsonb_build_object(
                                'nome', nome, 'planilha', desl,
                                'ultimo_contrato', ultimo)), '[]'::jsonb)
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
    'antes da admissao declarada vira divergencia, nao escrita). Desligado e '
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
-- VALIDACAO — rodar apos aplicar
--
-- 1) Assinatura AINDA unica (esperado: exatamente 1 linha).
--    Se aparecerem duas, uma sobrecarga foi criada e a chamada do
--    angry-man vai falhar com "function is not unique".
--
--    SELECT p.proname,
--           pg_get_function_identity_arguments(p.oid) AS args,
--           p.proacl
--    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--    WHERE n.nspname = 'public' AND p.proname = 'fn_headcount_replace';
--    -- Esperado: args = 'p_rows jsonb, p_modo_afastamento text,
--    --                   p_reabrir_ativos boolean'
--
--
-- 2) Recusas seguem intactas (nenhuma escreve; todas retornam antes do
--    advisory lock). Regressao da 094, nao funcionalidade nova.
--
--    SELECT public.fn_headcount_replace('[]'::jsonb);
--    -- {"count":0,"error":"Arquivo vazio. Nada a aplicar."}
--
--    SELECT public.fn_headcount_replace('[{"nome":"TESTE"}]'::jsonb);
--    -- SNAPSHOT com bloco vazio -> recusa apontando SKIP.
--
--
-- 3) MUDANCA 3 — idempotencia real. Rodar DUAS vezes seguidas com o
--    cadastro atual como payload, dentro de BEGIN/ROLLBACK.
--
--    BEGIN;
--    SELECT public.fn_headcount_replace(
--        (SELECT jsonb_agg(jsonb_build_object(
--                    'nome', c.nome,
--                    'loja_id', c.loja_id,
--                    'status', c.status))
--         FROM public.consultores c
--         WHERE c.loja_id IS NOT NULL),
--        'SKIP') -> 'cadastro';
--    -- Esperado: {"inseridos":0,"atualizados":0,"inalterados":424,
--    --            "sem_loja":0}
--    -- `atualizados` = 0 e o ponto da mudanca 3. Na 094 este mesmo
--    -- payload devolvia atualizados = 424 e carimbava now() em todas.
--    ROLLBACK;
--
--
-- 4) MUDANCA 3 — os updated_at NAO se movem.
--
--    BEGIN;
--    CREATE TEMP TABLE antes AS
--        SELECT id, updated_at FROM public.consultores;
--    SELECT public.fn_headcount_replace(
--        (SELECT jsonb_agg(jsonb_build_object(
--                    'nome', c.nome, 'loja_id', c.loja_id,
--                    'status', c.status))
--         FROM public.consultores c WHERE c.loja_id IS NOT NULL),
--        'SKIP') -> 'cadastro';
--    SELECT count(*) AS linhas_recarimbadas
--    FROM public.consultores c JOIN antes a ON a.id = c.id
--    WHERE c.updated_at <> a.updated_at;
--    -- Esperado: 0.
--    ROLLBACK;
--
--
-- 5) MUDANCA 2 — status vazio preserva o banco.
--    Escolha alguem DESLIGADO e mande a linha sem `status`.
--
--    BEGIN;
--    SELECT c.nome, c.status FROM public.consultores c
--    WHERE c.status LIKE 'Deslig%' AND c.loja_id IS NOT NULL LIMIT 1;
--    -- use o nome/loja retornados abaixo:
--    SELECT public.fn_headcount_replace(
--        jsonb_build_array(jsonb_build_object(
--            'nome', '<NOME>', 'loja_id', '<UUID>')), 'SKIP');
--    SELECT status FROM public.consultores
--    WHERE nome = '<NOME>' AND loja_id = '<UUID>';
--    -- Esperado: 'Desligado (a)' — inalterado. Na 094 viraria
--    -- 'Ativo (a)'.
--    ROLLBACK;
--
--    E o inverso, para garantir que status DECLARADO ainda vence:
--    ... mesma chamada com 'status', 'Ativo (a)' -> muda para ativo,
--    e `cadastro.atualizados` = 1.
--
--
-- 6) MUDANCA 1 — o contador. Estado limpo hoje: esperado 0.
--
--    SELECT public.fn_headcount_replace(
--        (SELECT jsonb_agg(jsonb_build_object(
--                    'nome', c.nome, 'loja_id', c.loja_id,
--                    'status', c.status))
--         FROM public.consultores c WHERE c.loja_id IS NOT NULL),
--        'SKIP') -> 'diagnostico';
--    -- Esperado:
--    --   ativos_com_janela_fechada    = 28
--    --   desligados_com_janela_aberta = 0
--    --   desligados_sem_data          = []
--    --   status_nao_canonico          = 2   (HELOINA, ERICA)
--    --   reabertas                    = 0
--
--    Para ver o contador DISPARAR, mande alguem com janela aberta como
--    desligado, sem data (em BEGIN/ROLLBACK):
--
--    BEGIN;
--    SELECT public.fn_headcount_replace(
--        jsonb_build_array(jsonb_build_object(
--            'nome', v.nome, 'loja_id', v.loja_id,
--            'status', 'Desligado (a)')), 'SKIP') -> 'diagnostico'
--    FROM public.consultor_vigencia v
--    WHERE v.vigencia_fim IS NULL AND v.loja_id IS NOT NULL
--    LIMIT 1;
--    -- Esperado: desligados_com_janela_aberta = 1 e
--    --           desligados_sem_data = [{nome, janelas_abertas,
--    --                                   ultimo_contrato}]
--    -- `ultimo_contrato` e a data que deveria estar em
--    -- DATA_DESLIGAMENTO.
--    ROLLBACK;
--
--
-- 7) A transferencia nao pode virar saida. Pessoa desligada numa loja e
--    ativa em outra NAO conta no contador novo.
--
--    BEGIN;
--    SELECT public.fn_headcount_replace(
--        jsonb_build_array(
--            jsonb_build_object('nome','X','loja_id','<UUID_A>',
--                               'status','Desligado (a)'),
--            jsonb_build_object('nome','X','loja_id','<UUID_B>',
--                               'status','Ativo (a)')),
--        'SKIP') -> 'diagnostico' ->> 'desligados_com_janela_aberta';
--    -- Esperado: 0 (use um nome com janela aberta).
--    ROLLBACK;
-- =====================================================
