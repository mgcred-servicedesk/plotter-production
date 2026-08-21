-- =====================================================
-- Migracao 094: fn_headcount_replace
--               (porta de entrada do HC_Colaboradores.xlsx)
--
-- Fecha o contrato de ETL que a 090 abriu pela metade. A 090 deu ao
-- afastamento uma porta de entrada em lote; admissao e desligamento
-- continuaram sem nenhuma — docs/HEADCOUNT_ETL.md secao 4.2 registra
-- esta funcao como "ainda nao escrita". Sem ela, `consultor_vigencia`
-- so tem o backfill da 087 e nenhum caminho incremental, o que colide
-- com o aviso do proprio contrato: depois que o ETL comeca a escrever,
-- rebuild em massa deixa de ser possivel.
--
-- UMA RPC PARA O ARQUIVO INTEIRO (decisao do usuario, 2026-08-20)
-- ---------------------------------------------------------------
-- O HC_Colaboradores e UM arquivo e uma FOTO. Portanto uma entrada so,
-- numa transacao so, atualizando as tres coisas que a foto afirma:
--
--   `consultores`           -> quem existe e em que loja (a foto)
--   `consultor_vigencia`    -> desde quando / ate quando (o ledger)
--   `consultor_afastamento` -> quem esta indisponivel (delegado a 090)
--
-- E o mesmo desenho de fn_supervisores_replace (077): foto e ledger
-- mudam juntos ou nao mudam. Partir em tres chamadas deixaria o banco
-- observavel num estado onde o cadastro ja mudou e o ledger nao.
--
-- `fn_afastamentos_replace` CONTINUA chamavel direto — e por ela que se
-- faz correcao pontual em modo UPSERT, sem passar pelo arquivo inteiro.
--
--
-- PRECEDENCIA: DECLARADO VENCE INFERIDO, SILENCIO NAO VENCE NADA
-- ---------------------------------------------------------------
-- A regra que atravessa a funcao inteira. Coluna preenchida e FATO e
-- sobrescreve a janela derivada da producao, marcando `origem = 'ETL'`.
-- Coluna VAZIA nao afirma nada: mantem o fallback que ja existe, sem
-- tocar na linha. Vazio nunca significa "nao tem".
--
-- Isso tem uma consequencia que vale escrever: `origem = 'ETL'` nao e
-- so procedencia, e o gatilho da R2 na 091 — janela ETL entra em
-- `declarado` e PERDE o piso de 50%, passando a valer a fracao pura.
-- Correto por construcao: o piso existe para limitar erro de
-- estimativa, e uma data informada pelo RH nao e estimativa.
--
--
-- PRODUCAO PROVA PRESENCA; O RH NAO PODE DESMENTI-LA
-- ---------------------------------------------------
-- Guarda que nao estava no contrato e a medicao pediu. Se a planilha
-- disser que alguem foi admitido em 01/06 e houver contrato digitado
-- por essa pessoa em 12/05, as duas afirmacoes nao podem ser ambas
-- verdadeiras. A funcao NAO aplica e reporta a divergencia.
--
-- A assimetria e deliberada e e a mesma da 087: producao prova
-- presenca, a falta dela nao prova ausencia. Por isso o contrario nao
-- vale — desligamento declarado SEM producao posterior e aceito sem
-- discussao, porque nao ha nada que o contradiga.
--
--
-- STATUS NAO E CANAL DE AFASTAMENTO (medido em 2026-08-21)
-- ---------------------------------------------------------
-- HELOINA DE AQUINO esta no cadastro com `status = 'Licenca
-- Maternidade'`. A regra `eh_ativo` da 087 e `LIKE 'ATIVO%'`, entao ela
-- nao passa no teste e o backfill FECHOU a janela dela em 2026-05-01,
-- como se tivesse sido desligada. Ela nao foi: esta afastada.
--
-- O efeito e um desligamento fantasma. Hoje HELOINA nem aparece em
-- `cabecas`; no desenho correto ela aparece com peso 0 nos meses cheios
-- de licenca — e volta sozinha quando o afastamento fechar, sem que
-- ninguem precise lembrar de reativa-la.
--
-- Por isso esta funcao adota regra propria e mais estreita:
-- **desligado e so quem tem status LIKE 'DESLIG%'**. Qualquer outro
-- status significa PRESENTE. Licenca vira afastamento pelas colunas
-- proprias, nunca por status. O envelope devolve `status_nao_canonico`
-- para que o canal ad-hoc fique visivel enquanto existir.
--
--
-- REABRIR JANELA E ATO EXPLICITO (p_reabrir_ativos)
-- -------------------------------------------------
-- Uma pessoa que a planilha declara ativa, sem data de desligamento, e
-- cuja janela o backfill fechou por inferencia, e uma contradicao real:
-- o silencio da producao encerrou alguem que o RH afirma estar la.
--
-- Reabrir seria o que a precedencia manda. Mas reabrir muda numero JA
-- PUBLICADO, retroativamente, em massa — e a 090 aprendeu essa licao na
-- direcao oposta: o caminho que mexe em tudo de uma vez nao pode ser
-- alcancavel por acidente. Entao o padrao e DIAGNOSTICAR, nao agir. O
-- envelope sempre devolve `ativos_com_janela_fechada`; reabrir de fato
-- exige `p_reabrir_ativos => true`, dito de proposito.
--
-- Quando reabre, mexe SO em janela com `origem LIKE 'BACKFILL%'`. Linha
-- ETL ou MANUAL e fato declarado e nao se desfaz por inferencia.
--
-- MANUAL E INTOCAVEL, EM QUALQUER FASE
-- -------------------------------------
-- Vale para admissao e desligamento tambem, e nao estava no contrato.
-- `origem = 'MANUAL'` e correcao feita por uma pessoa que olhou o caso;
-- deixar a carga seguinte sobrescrever desfaria esse trabalho toda vez
-- que o arquivo subisse, em silencio. A 077 ja resolveu exatamente este
-- conflito para supervisores — divergencia se REPORTA, nao se aplica —
-- e aqui a regra e a mesma. ERICA (janelas MANUAL das 088/089) e o caso
-- vivo: sem esta guarda, a primeira carga do HC apagaria a correcao
-- historica que duas migrations foram escritas para fazer.
--
-- Medido em 2026-08-21, antes de qualquer carga: 0 pessoas nesse estado
-- (o backfill da 087 esta coerente com o cadastro). O parametro existe
-- para quando o arquivo real chegar, nao para consertar o presente.
--
--
-- MODO DO BLOCO DE AFASTAMENTO (p_modo_afastamento)
-- --------------------------------------------------
--   SNAPSHOT (padrao) -> repassa a 090 como foto: quem sumiu voltou.
--   UPSERT            -> repassa como correcao pontual.
--   SKIP              -> nao toca em `consultor_afastamento`.
--
-- SKIP nao existe na 090 e e a razao de este parametro existir. A 090
-- RECUSA SNAPSHOT vazio de proposito (fecharia todas as janelas de uma
-- vez). Mas o arquivo de hoje ainda nao tem as colunas de afastamento,
-- e "arquivo sem as colunas" e "arquivo dizendo que ninguem esta
-- afastado" sao afirmacoes diferentes que um array vazio nao distingue.
-- SQL nao consegue ver a diferenca; o angry-man consegue. SKIP e como
-- ele diz "nao pergunte ao meu silencio".
--
-- Consequencia: SNAPSHOT com bloco vazio segue RECUSADO aqui tambem, e
-- a mensagem aponta o SKIP como saida.
--
--
-- TUDO-OU-NADA
-- -------------
-- Toda validacao acontece ANTES de qualquer escrita, como na 090. Uma
-- linha invalida derruba a carga inteira e devolve `invalidas`. Nada
-- pela metade, e em particular nada de cadastro atualizado com ledger
-- parado.
--
-- ATENCAO para quem for evoluir: NAO criar sobrecarga desta funcao.
-- CREATE OR REPLACE casa por ASSINATURA — uma segunda versao com numero
-- diferente de argumentos vira funcao NOVA, e a chamada do angry-man
-- passa a dar "function is not unique". Licao registrada na 077 e
-- repetida na 090. Para mudar o contrato, altere ESTA assinatura e faca
-- o redeploy do angry-man junto.
--
-- Depende de: 086/087 (consultor_vigencia), 089/090 (afastamento).
-- Executar no Supabase SQL Editor, depois da 093.
-- =====================================================


-- ===========================================
-- 0. Guarda — as dependencias precisam existir
-- ===========================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'consultor_vigencia'
    ) THEN
        RAISE EXCEPTION
            'Tabela public.consultor_vigencia ausente. Aplique 086 e 087 '
            'antes desta.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'fn_afastamentos_replace'
    ) THEN
        RAISE EXCEPTION
            'Funcao public.fn_afastamentos_replace ausente. Aplique '
            '090_fn_afastamentos_replace.sql antes desta.';
    END IF;
END;
$$;


-- ===========================================
-- 1. fn_headcount_replace
--
-- Formato de cada linha de p_rows (todas as chaves opcionais menos
-- `nome`; ausente e string vazia sao equivalentes):
--
--   {
--     "nome":               "FULANO DE TAL",
--     "loja_id":            "<uuid>",
--     "status":             "Ativo (a)",
--     "data_admissao":      "2025-06-02",
--     "data_desligamento":  "2026-04-15",
--     "afastamento_tipo":   "LICENCA_MATERNIDADE",
--     "afastamento_inicio": "2026-05-04",
--     "afastamento_fim":    "2026-11-04",
--     "observacao":         "texto livre"
--   }
--
-- `loja_id` chega RESOLVIDO pelo chamador, como em
-- fn_supervisores_replace: o angry-man ja carrega o lookup de lojas e
-- reporta linha a linha o que nao resolveu, o que da mensagem melhor
-- que um nome de loja perdido dentro do SQL.
-- ===========================================

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
    v_sem_loja    integer := 0;
    v_adm_upd     integer := 0;
    v_adm_new     integer := 0;
    v_desl_upd    integer := 0;
    v_reabertas   integer := 0;
    v_nao_canon   integer := 0;
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

    -- Quem ja existe e contado ANTES. O truque `RETURNING xmax = 0`
    -- distinguiria insert de update em uma passada, mas depende de
    -- detalhe interno nao garantido pela documentacao; a contagem
    -- previa custa um index scan e nao depende de nada.
    -- DISTINCT porque o INSERT abaixo tambem deduplica: sem isso, a
    -- mesma (pessoa, loja) repetida no arquivo contaria duas vezes aqui
    -- e uma so la, e `inseridos` sairia negativo.
    SELECT count(DISTINCT (pl.nome, pl.loja_id))::integer INTO v_cad_upd
    FROM pg_temp.hc_plan pl
    JOIN public.consultores c
      ON c.nome = pl.nome AND c.loja_id = pl.loja_id
    WHERE pl.loja_id IS NOT NULL;

    -- DISTINCT ON: a mesma (pessoa, loja) duas vezes no arquivo faria
    -- ON CONFLICT DO UPDATE tocar a mesma linha duas vezes na mesma
    -- instrucao, que o Postgres recusa com erro.
    INSERT INTO public.consultores (nome, loja_id, status)
    SELECT DISTINCT ON (nome, loja_id)
           nome, loja_id, coalesce(status, 'Ativo (a)')
    FROM pg_temp.hc_plan
    WHERE loja_id IS NOT NULL
    ORDER BY nome, loja_id
    ON CONFLICT (nome, loja_id) DO UPDATE
        SET status = EXCLUDED.status;
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
            'ativos_com_janela_fechada', v_fechadas,
            'reabertas',                 v_reabertas,
            'status_nao_canonico',       v_nao_canon),
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
    'p_reabrir_ativos e ato explicito. SECURITY DEFINER; EXECUTE so para '
    'service_role. NAO criar sobrecarga (ver 077/090).';

REVOKE ALL ON FUNCTION public.fn_headcount_replace(jsonb, text, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_headcount_replace(jsonb, text, boolean)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_headcount_replace(jsonb, text, boolean)
    TO service_role;


-- =====================================================
-- ANTES DE CARREGAR O ARQUIVO REAL — LEIA
--
-- A copia de `configuracao/HC_Colaboradores.xlsx` no repositorio e um
-- EXPORT DE MARCO. Medido em 2026-08-21: 47 dos 242 nomes divergem do
-- banco, e 45 deles estao 'Ativo (a)' na planilha e 'Desligado (a)' no
-- banco.
--
-- Esta funcao faz UPSERT em `consultores.status`. Carregar aquele
-- arquivo REATIVARIA 45 desligados no cadastro. Nao e hipotese: e o
-- resultado exato da simulacao. Exija um export fresco.
--
-- O mesmo numero explica o `ativos_com_janela_fechada` que o envelope
-- devolveria: 46 = os 45 acima + HELOINA DE AQUINO, que esta em licenca
-- maternidade e nao foi desligada. E por isso que `p_reabrir_ativos`
-- NAO e o padrao — com ele ligado, essa carga reabriria 46 janelas e
-- inflaria o denominador de varias competencias de uma vez.
-- =====================================================


-- =====================================================
-- VALIDACAO — rodar apos aplicar
--
-- 1) Assinatura unica e grants (esperado: 1 linha, service_role apenas):
--
--    SELECT p.proname,
--           pg_get_function_identity_arguments(p.oid) AS args,
--           p.proacl
--    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--    WHERE n.nspname = 'public' AND p.proname = 'fn_headcount_replace';
--    -- Mais de uma linha = sobrecarga criada por engano. Ver 077/090.
--
--
-- 2) Recusas — nenhuma delas escreve nada, entao podem rodar a seco.
--    Todas retornam antes do advisory lock.
--
--    SELECT public.fn_headcount_replace('[]'::jsonb);
--    -- {"count":0,"error":"Arquivo vazio. Nada a aplicar."}
--
--    SELECT public.fn_headcount_replace(
--        '[{"nome":"TESTE"}]'::jsonb, 'MODO_QUE_NAO_EXISTE');
--    -- error: "Modo de afastamento invalido..."
--
--    SELECT public.fn_headcount_replace(
--        '[{"nome":"TESTE","data_admissao":"03/2025"}]'::jsonb, 'SKIP');
--    -- error: "Linhas invalidas", com a linha em `invalidas`.
--
--    SELECT public.fn_headcount_replace('[{"nome":"TESTE"}]'::jsonb);
--    -- Modo default e SNAPSHOT e o bloco esta vazio -> recusa apontando
--    -- SKIP como saida. Esta e a guarda que impede o arquivo de hoje
--    -- (sem colunas de afastamento) de fechar todas as janelas.
--
--    SELECT public.fn_headcount_replace(
--        '[{"nome":"A","data_admissao":"2025-01-01"},
--          {"nome":"A","data_admissao":"2025-02-01"}]'::jsonb, 'SKIP');
--    -- error: mesma pessoa duas vezes com data.
--
--
-- 3) DRY RUN — a unica forma honesta de validar funcao de escrita.
--    Rode o bloco INTEIRO de uma vez; o ROLLBACK e obrigatorio.
--
--    BEGIN;
--      SELECT jsonb_pretty(public.fn_headcount_replace('[
--        {"nome": "ERICA CRISTINA MARINS DA SILVA",
--         "loja_id": "76b4e76f-044e-4889-9de7-efad0d194a74",
--         "status": "Ativo (a)",
--         "data_admissao": "2025-11-03"}
--      ]'::jsonb, 'SKIP'));
--    ROLLBACK;
--
--    Esperado — DUAS guardas disparam no mesmo caso real:
--      admissao.aplicadas = 0
--      admissao.divergencias  contem ERICA com
--          planilha = 2025-11-03, primeiro_contrato = 2025-10-01
--      (producao prova presenca ANTES da admissao declarada)
--    E, se a data fosse plausivel, a segunda guarda pegaria: a primeira
--    janela de ERICA tem origem MANUAL (088/089), entao cairia em
--    `divergencias_manual` em vez de sobrescrever.
--
--    Trocando para "data_admissao": "2025-10-01" o resultado vira
--    `sem_efeito`/`divergencia_manual` — nunca escrita. Confirme com:
--
--    SELECT vigencia_inicio, vigencia_fim, origem
--    FROM public.consultor_vigencia
--    WHERE nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA'
--    ORDER BY vigencia_inicio;
--    -- Esperado (inalterado pelo dry run):
--    --   2025-10-01 -> 2026-06-19  MANUAL
--    --   2026-06-19 -> NULL        MANUAL
--
--
-- 4) Idempotencia. Rodar a MESMA carga duas vezes tem de devolver
--    admissao.aplicadas = 0 e desligamento.aplicados = 0 na segunda.
--    Verifique tambem que o volume do ledger nao cresceu:
--
--    SELECT origem, count(*) AS linhas,
--           count(*) FILTER (WHERE vigencia_fim IS NULL) AS abertas
--    FROM public.consultor_vigencia GROUP BY origem ORDER BY origem;
--    -- Estado em 2026-08-21, antes de qualquer carga:
--    --   BACKFILL_CENSURADO  124 linhas,  45 abertas
--    --   BACKFILL_PISO         1 linha,    1 aberta
--    --   BACKFILL_PRODUCAO   269 linhas, 121 abertas
--    --   MANUAL                2 linhas,   1 aberta
--
--
-- 5) DEPOIS de qualquer carga que altere o ledger, rematerializar o
--    Caderno das competencias afetadas — senao o bereshit publica um
--    denominador e o dashboard mostra outro:
--
--    SELECT public.fn_materializar_caderno(mes, ano);
-- =====================================================
