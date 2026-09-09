-- =====================================================
-- Migracao 113: procedencia em supervisor_vigencia
-- Data: 2026-09-09
-- Depende de: 076 (supervisor_vigencia), 082 (fn_supervisores_replace e
--             fn_aplicar_mudanca_supervisor)
--
-- O TERCEIRO LEDGER ERA O UNICO SEM PROCEDENCIA
-- ----------------------------------------------
-- `consultor_vigencia` (086) e `consultor_afastamento` (089) nascerem com
-- `origem` nao foi detalhe: e a coluna que sustenta a doutrina "correcao
-- humana nao se desfaz por carga de arquivo". A 077 reporta divergencia
-- em vez de aplicar, a 095 classifica `divergencia_manual`, e a 100
-- bloqueia a linha com `CORRECAO_MANUAL_EXISTENTE`.
--
-- `supervisor_vigencia` (076) nasceu sem a coluna, e por isso ficou de
-- fora das tres guardas. O buraco e verificavel na 100: o teste de
-- `CORRECAO_MANUAL_EXISTENTE` consulta `consultor_vigencia` e
-- `consultor_afastamento` e NAO consulta `supervisor_vigencia` — que a
-- mesma funcao atualiza logo adiante, sem condicao nenhuma. Um
-- desligamento vindo do arquivo de RH desfaz em silencio uma promocao
-- registrada a mao.
--
-- Nao e hipotese: a 110 (aplicada em 2026-09-08) abriu a supervisao de
-- HUGO em HELP MADUREIRA e fechou a de BARBARA na mesma data. Enquanto
-- essas duas linhas forem indistinguiveis de escrita de ETL, o proximo
-- arquivo de RH que traga qualquer um dos dois nomes as sobrescreve.
--
--
-- POR QUE 'LEGADO' E NAO 'ETL' NAS LINHAS QUE JA EXISTEM
-- -------------------------------------------------------
-- Decisao do usuario (2026-09-09): so o que vier daqui pra frente e
-- distinguivel — nao ha backfill de procedencia. As 078, 081, 084, 088 e
-- 110 escreveram correcoes humanas nesta tabela, mas depois do fato nao
-- ha como separa-las das linhas de import, e adivinhar produziria uma
-- protecao falsa (pior que nenhuma: bloquearia carga legitima alegando
-- correcao que ninguem fez).
--
-- Entao as linhas existentes recebem 'LEGADO', que afirma exatamente o
-- que se sabe: procedencia desconhecida. Elas seguem SEM protecao — o
-- comportamento delas nao muda em nada com esta migration. A guarda de
-- MANUAL vale so para o que for escrito a partir de agora.
--
-- Marcar tudo como 'ETL' seria mais curto e diria uma inverdade sobre
-- pelo menos cinco migrations conhecidas. 'LEGADO' custa um valor a mais
-- no CHECK e nao mente.
--
-- Executar no Supabase SQL Editor, depois da 112.
-- =====================================================

BEGIN;

LOCK TABLE public.supervisor_vigencia IN SHARE ROW EXCLUSIVE MODE;


-- ===========================================
-- 1. A coluna
--
-- O bloco todo e condicionado a AUSENCIA da coluna: numa reexecucao nada
-- acontece. Isso importa porque o carimbo de 'LEGADO' e "toda linha que
-- existe agora" — reexecutar sem a guarda re-carimbaria como LEGADO as
-- linhas MANUAL escritas depois da primeira aplicacao.
-- ===========================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute a
         WHERE a.attrelid = 'public.supervisor_vigencia'::regclass
           AND a.attname  = 'origem'
           AND NOT a.attisdropped
    ) THEN
        RAISE NOTICE 'Migration 113: coluna origem ja existe — nada a fazer.';
        RETURN;
    END IF;

    ALTER TABLE public.supervisor_vigencia
        ADD COLUMN origem TEXT NOT NULL DEFAULT 'ETL';

    -- Carimbo do legado. Roda uma vez so, dentro da guarda acima, e
    -- alcanca exatamente as linhas anteriores a esta migration.
    UPDATE public.supervisor_vigencia SET origem = 'LEGADO' WHERE true;

    -- 'BACKFILL_PRODUCAO' esta no vocabulario porque a 114 precisa dele:
    -- quando o desligamento fecha pela producao (doutrina da 100), a
    -- janela de SUPERVISOR fecha na mesma data derivada, e a procedencia
    -- tem de dizer que a data veio da producao, nao do arquivo. Mesmo
    -- valor e mesmo significado que em consultor_vigencia (086).
    -- 'BACKFILL_PISO' fica de fora: nao ha piso de supervisao, e valor
    -- que nunca pode ocorrer nao pertence a um CHECK.
    ALTER TABLE public.supervisor_vigencia
        ADD CONSTRAINT chk_sv_origem
        CHECK (origem IN ('ETL', 'MANUAL', 'LEGADO', 'BACKFILL_PRODUCAO'));

    RAISE NOTICE
        'Migration 113: coluna origem criada; % linha(s) carimbada(s) como LEGADO.',
        (SELECT count(*) FROM public.supervisor_vigencia WHERE origem = 'LEGADO');
END
$$;

COMMENT ON COLUMN public.supervisor_vigencia.origem IS
    'Procedencia da linha, espelhando a coluna homonima de '
    'consultor_vigencia (086). ETL = escrita por carga de arquivo '
    '(fn_supervisores_replace). MANUAL = correcao humana explicita '
    '(fn_aplicar_mudanca_supervisor ou migration pontual); carga de '
    'arquivo nao a sobrescreve, apenas reporta. BACKFILL_PRODUCAO = a '
    'DATA foi derivada da producao, nao informada (114). LEGADO = '
    'anterior a migration 113, procedencia desconhecida e sem protecao.';


-- ===========================================
-- 2. fn_supervisores_replace — grava ETL e preserva MANUAL
--
-- Duas mudancas, nenhuma na assinatura:
--
--   (a) o INSERT de janela nova grava origem = 'ETL';
--   (b) o fechamento por ausencia PULA janelas MANUAL e as devolve em
--       `manuais_preservadas`.
--
-- (b) e a razao de ser desta migration. Ausencia na planilha ja significa
-- "fechar" (082), e sob essa regra a promocao do HUGO desaparece no
-- primeiro import em que a Supervisores.xlsx nao o liste — inclusive por
-- atraso de atualizacao da planilha, que e o modo de falha normal dela.
--
-- O custo do lado oposto, declarado: supervisao MANUAL que terminou de
-- verdade nao fecha por arquivo, e fica aberta ate alguem rodar
-- fn_aplicar_mudanca_supervisor(..., 'FIM'). E o mesmo custo que a 095
-- aceita em `divergencia_manual` para o consultor — declarado vence
-- inferido, e ausencia numa planilha e inferencia.
--
-- Campo novo no envelope; nada removido nem renomeado.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_supervisores_replace(p_rows jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_min_linhas    integer := 30;
    v_sentinela     uuid := '00000000-0000-0000-0000-000000000000';
    v_payload_len   integer;
    v_count_before  integer := 0;
    v_count_after   integer := 0;
    v_sem_loja      integer := 0;
    v_abertas       integer := 0;
    v_fechadas      integer := 0;
    v_por_sucessao  integer := 0;
    v_sem_data      integer := 0;
    v_recusados     integer := 0;
    v_manuais       jsonb;
    v_divergencias  jsonb;
    v_hoje          date := current_date;
BEGIN
    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Payload ausente ou nao e um array JSON.');
    END IF;

    v_payload_len := jsonb_array_length(p_rows);

    IF v_payload_len < v_min_linhas THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format(
                'Planilha com %s linhas — abaixo do minimo esperado (%s). '
                'Substituicao abortada (base preservada).',
                v_payload_len, v_min_linhas));
    END IF;

    PERFORM pg_advisory_xact_lock(20260709);

    SELECT count(*) INTO v_count_before FROM supervisores;

    DROP TABLE IF EXISTS _sup_incoming;
    CREATE TEMP TABLE _sup_incoming ON COMMIT DROP AS
    SELECT DISTINCT ON (r.nome_norm, r.loja_key)
        r.nome,
        r.loja_id,
        COALESCE(l.regiao_id, r.regiao_id) AS regiao_id,
        r.nome_norm,
        r.loja_key,
        COALESCE(r.vigencia_inicio, v_hoje) AS inicio,
        r.vigencia_inicio                   AS inicio_informado
    FROM (
        SELECT
            j.nome,
            j.loja_id,
            j.regiao_id,
            j.vigencia_inicio,
            upper(regexp_replace(btrim(j.nome), '[[:space:]]+', ' ', 'g'))
                AS nome_norm,
            coalesce(j.loja_id, v_sentinela) AS loja_key
        FROM jsonb_to_recordset(p_rows)
             AS j(nome text, loja_id uuid, regiao_id uuid,
                  vigencia_inicio date)
        WHERE j.nome IS NOT NULL AND btrim(j.nome) <> ''
    ) r
    LEFT JOIN lojas l ON l.id = r.loja_id;

    -- (a) Pares novos — precisam ser conhecidos ANTES de abrir, porque a
    --     data deles e o que fecha o antecessor da mesma loja.
    DROP TABLE IF EXISTS _sup_novos;
    CREATE TEMP TABLE _sup_novos ON COMMIT DROP AS
    SELECT i.*
    FROM _sup_incoming i
    WHERE NOT EXISTS (
        SELECT 1 FROM supervisor_vigencia v
        WHERE v.nome_normalizado = i.nome_norm
          AND coalesce(v.loja_id, v_sentinela) = i.loja_key
          AND v.vigencia_fim IS NULL
    );

    -- (b) Saidas, com a data resolvida por sucessao quando houver.
    --     `origem` entra aqui para o UPDATE poder preservar MANUAL.
    DROP TABLE IF EXISTS _sup_saidas;
    CREATE TEMP TABLE _sup_saidas ON COMMIT DROP AS
    SELECT
        v.id,
        v.nome,
        v.loja_id,
        v.vigencia_inicio,
        v.origem,
        suc.inicio IS NOT NULL AS por_sucessao,
        coalesce(suc.inicio, v_hoje) AS fim
    FROM supervisor_vigencia v
    LEFT JOIN LATERAL (
        -- Sucessor = supervisor novo da MESMA loja. Loja nula nao tem
        -- "mesma loja" que faca sentido, entao nao sucede.
        SELECT min(n.inicio) AS inicio
        FROM _sup_novos n
        WHERE v.loja_id IS NOT NULL
          AND n.loja_key = v.loja_id
    ) suc ON true
    WHERE v.vigencia_fim IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM _sup_incoming i
          WHERE i.nome_norm = v.nome_normalizado
            AND i.loja_key = coalesce(v.loja_id, v_sentinela)
      );

    -- Fecha so as janelas validas. Uma data de fim <= inicio criaria
    -- janela invalida (chk_sv_vigencia_ordem) ou de duracao zero: nao
    -- fecha e reporta, em vez de abortar o import inteiro.
    --
    -- MUDANCA 113: `origem <> 'MANUAL'`. Correcao humana nao se desfaz
    -- por ausencia numa planilha; sai em `manuais_preservadas`.
    UPDATE supervisor_vigencia v
       SET vigencia_fim = s.fim
      FROM _sup_saidas s
     WHERE s.id = v.id
       AND s.fim > v.vigencia_inicio
       AND s.origem <> 'MANUAL';
    GET DIAGNOSTICS v_fechadas = ROW_COUNT;

    SELECT
        count(*) FILTER (WHERE origem <> 'MANUAL'
                           AND por_sucessao AND fim > vigencia_inicio),
        count(*) FILTER (WHERE origem <> 'MANUAL'
                           AND NOT por_sucessao AND fim > vigencia_inicio),
        count(*) FILTER (WHERE origem <> 'MANUAL' AND fim <= vigencia_inicio)
      INTO v_por_sucessao, v_sem_data, v_recusados
    FROM _sup_saidas;

    SELECT jsonb_agg(jsonb_build_object(
               'nome', s.nome,
               'loja', l.nome,
               'desde', s.vigencia_inicio,
               'fim_que_seria_aplicado', s.fim))
      INTO v_manuais
    FROM _sup_saidas s
    LEFT JOIN lojas l ON l.id = s.loja_id
    WHERE s.origem = 'MANUAL';

    -- (c) Abre os pares novos na data informada, marcando procedencia.
    INSERT INTO supervisor_vigencia (nome, loja_id, vigencia_inicio, origem)
    SELECT n.nome, n.loja_id, n.inicio, 'ETL' FROM _sup_novos n;
    GET DIAGNOSTICS v_abertas = ROW_COUNT;

    -- (d) Divergencias: planilha discorda de vigencia JA aberta.
    --     Decisao do usuario: apenas reportar. Corrigir e ato explicito,
    --     via fn_aplicar_mudanca_supervisor(..., 'CORRIGIR_INICIO').
    SELECT jsonb_agg(jsonb_build_object(
               'nome', i.nome,
               'loja', l.nome,
               'planilha', i.inicio_informado,
               'ledger', v.vigencia_inicio,
               'origem', v.origem))
      INTO v_divergencias
    FROM _sup_incoming i
    JOIN supervisor_vigencia v
      ON v.nome_normalizado = i.nome_norm
     AND coalesce(v.loja_id, v_sentinela) = i.loja_key
     AND v.vigencia_fim IS NULL
    LEFT JOIN lojas l ON l.id = i.loja_id
    WHERE i.inicio_informado IS NOT NULL
      AND i.inicio_informado <> v.vigencia_inicio;

    -- (e) `supervisores` segue sendo a foto: reescrita por inteiro.
    --     `WHERE true` requerido pela extensao safeupdate do Supabase.
    DELETE FROM supervisores WHERE true;

    INSERT INTO supervisores (nome, loja_id, regiao_id)
    SELECT i.nome, i.loja_id, i.regiao_id FROM _sup_incoming i;
    GET DIAGNOSTICS v_count_after = ROW_COUNT;

    SELECT count(*) INTO v_sem_loja FROM supervisores WHERE loja_id IS NULL;

    RETURN jsonb_build_object(
        'count',                 v_count_after,
        'count_before',          v_count_before,
        'sem_loja',              v_sem_loja,
        'vigencias_abertas',     v_abertas,
        'vigencias_fechadas',    v_fechadas,
        'fechadas_por_sucessao', v_por_sucessao,
        'fechadas_sem_data',     v_sem_data,
        'fechamentos_recusados', v_recusados,
        'manuais_preservadas',   coalesce(v_manuais, '[]'::jsonb),
        'divergencias',          coalesce(v_divergencias, '[]'::jsonb),
        'data_efetiva',          v_hoje,
        'error',                 NULL
    );

EXCEPTION WHEN OTHERS THEN
    -- Transacao implicita revertida: nem a foto nem o ledger persistem.
    RETURN jsonb_build_object('count', 0, 'error', SQLERRM);
END;
$$;

COMMENT ON FUNCTION public.fn_supervisores_replace(jsonb) IS
    'Substitui `supervisores` a partir da planilha E versiona em '
    'supervisor_vigencia. Janela nova nasce com origem = ETL; janela '
    'MANUAL nao e fechada por ausencia na planilha, apenas reportada em '
    '`manuais_preservadas` (migration 113).';

REVOKE ALL ON FUNCTION public.fn_supervisores_replace(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_supervisores_replace(jsonb) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_supervisores_replace(jsonb) TO service_role;


-- ===========================================
-- 3. fn_aplicar_mudanca_supervisor — o que passa por aqui e MANUAL
--
-- Esta funcao E o caminho explicito de correcao humana (082): se o que
-- ela escreve nao for MANUAL, a protecao da secao 2 nunca alcanca nada
-- e a coluna vira enfeite.
--
-- Tres pontos de escrita, todos carimbados:
--   * CORRIGIR_INICIO — promove a linha corrigida a MANUAL. Corrigir a
--     data de uma janela de ETL e afirmacao humana sobre ela;
--   * INICIO / REMANEJAMENTO — INSERT nasce MANUAL;
--   * FIM / REMANEJAMENTO — o fechamento carimba a linha que fecha.
--
-- O `UPDATE ... SET vigencia_fim` NAO ganha guarda de MANUAL: quem
-- chama esta funcao esta declarando o fato a mao, e a guarda existe
-- contra carga de arquivo, nao contra o operador.
--
-- Assinatura inalterada (TEXT, TEXT, DATE, TEXT).
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_aplicar_mudanca_supervisor(
    p_nome         TEXT,
    p_loja_nome    TEXT,
    p_data_efetiva DATE,
    p_acao         TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v_nome_norm    TEXT;
    v_loja_id      UUID;
    v_acao         TEXT;
    v_fechadas     INTEGER := 0;
    v_abertas      INTEGER := 0;
    v_inicio_min   DATE;
    v_fim_anterior DATE;
    v_antes        DATE;
BEGIN
    v_acao := upper(btrim(coalesce(p_acao, '')));
    IF v_acao NOT IN ('INICIO', 'FIM', 'REMANEJAMENTO', 'CORRIGIR_INICIO') THEN
        RAISE EXCEPTION
            'acao invalida: % (use INICIO, FIM, REMANEJAMENTO ou '
            'CORRIGIR_INICIO)', p_acao;
    END IF;

    v_nome_norm := upper(regexp_replace(
        btrim(coalesce(p_nome, '')), '[[:space:]]+', ' ', 'g'));
    IF v_nome_norm = '' THEN
        RAISE EXCEPTION 'nome do supervisor vazio';
    END IF;

    IF p_data_efetiva IS NULL THEN
        RAISE EXCEPTION 'data_efetiva obrigatoria (nome: %)', p_nome;
    END IF;

    IF btrim(coalesce(p_loja_nome, '')) <> '' THEN
        SELECT id INTO v_loja_id
        FROM public.lojas WHERE nome = btrim(p_loja_nome);
        IF v_loja_id IS NULL THEN
            RAISE EXCEPTION 'Loja nao encontrada: %', p_loja_nome;
        END IF;
    ELSIF v_acao <> 'FIM' THEN
        RAISE EXCEPTION 'loja obrigatoria para acao % (nome: %)',
                        v_acao, p_nome;
    END IF;

    -- ── CORRIGIR_INICIO ──────────────────────────────────────────
    IF v_acao = 'CORRIGIR_INICIO' THEN
        SELECT vigencia_inicio INTO v_antes
        FROM public.supervisor_vigencia
        WHERE nome_normalizado = v_nome_norm
          AND loja_id IS NOT DISTINCT FROM v_loja_id
          AND vigencia_fim IS NULL;

        IF v_antes IS NULL THEN
            RAISE EXCEPTION
                'nao ha vigencia aberta de % em % para corrigir',
                p_nome, p_loja_nome;
        END IF;

        IF v_antes = p_data_efetiva THEN
            RETURN format('no-op: vigencia de %s ja comeca em %s',
                          p_nome, p_data_efetiva);
        END IF;

        -- Nao invadir janela anterior ja fechada da mesma pessoa/loja.
        SELECT max(vigencia_fim) INTO v_fim_anterior
        FROM public.supervisor_vigencia
        WHERE nome_normalizado = v_nome_norm
          AND loja_id IS NOT DISTINCT FROM v_loja_id
          AND vigencia_fim IS NOT NULL;

        IF v_fim_anterior IS NOT NULL AND p_data_efetiva < v_fim_anterior THEN
            RAISE EXCEPTION
                'data % invade janela anterior de % (encerrada em %)',
                p_data_efetiva, p_nome, v_fim_anterior;
        END IF;

        UPDATE public.supervisor_vigencia
           SET vigencia_inicio = p_data_efetiva,
               origem          = 'MANUAL'
         WHERE nome_normalizado = v_nome_norm
           AND loja_id IS NOT DISTINCT FROM v_loja_id
           AND vigencia_fim IS NULL;

        RETURN format('CORRIGIR_INICIO: %s em %s: %s -> %s',
                      p_nome, p_loja_nome, v_antes, p_data_efetiva);
    END IF;

    -- ── INICIO (idempotente) ─────────────────────────────────────
    IF v_acao = 'INICIO' AND EXISTS (
        SELECT 1 FROM public.supervisor_vigencia
        WHERE nome_normalizado = v_nome_norm
          AND loja_id IS NOT DISTINCT FROM v_loja_id
          AND vigencia_fim IS NULL
    ) THEN
        INSERT INTO public.supervisores (nome, loja_id, regiao_id)
        SELECT btrim(p_nome), v_loja_id, l.regiao_id
        FROM public.lojas l WHERE l.id = v_loja_id
        ON CONFLICT (nome, loja_id) DO NOTHING;
        RETURN format('no-op: %s ja supervisiona %s', p_nome, p_loja_nome);
    END IF;

    IF v_acao IN ('FIM', 'REMANEJAMENTO') THEN
        SELECT min(vigencia_inicio) INTO v_inicio_min
        FROM public.supervisor_vigencia
        WHERE nome_normalizado = v_nome_norm
          AND vigencia_fim IS NULL
          AND (v_acao = 'REMANEJAMENTO'
               OR v_loja_id IS NULL
               OR loja_id IS NOT DISTINCT FROM v_loja_id);

        IF v_inicio_min IS NOT NULL AND p_data_efetiva <= v_inicio_min THEN
            RAISE EXCEPTION
                'data_efetiva % <= inicio da vigencia aberta (%) de %',
                p_data_efetiva, v_inicio_min, p_nome;
        END IF;
    END IF;

    IF v_acao IN ('FIM', 'REMANEJAMENTO') THEN
        UPDATE public.supervisor_vigencia
           SET vigencia_fim = p_data_efetiva,
               origem       = 'MANUAL'
         WHERE nome_normalizado = v_nome_norm
           AND vigencia_fim IS NULL
           AND (v_acao = 'REMANEJAMENTO'
                OR v_loja_id IS NULL
                OR loja_id IS NOT DISTINCT FROM v_loja_id);
        GET DIAGNOSTICS v_fechadas = ROW_COUNT;

        DELETE FROM public.supervisores s
         WHERE upper(regexp_replace(btrim(s.nome), '[[:space:]]+', ' ', 'g'))
               = v_nome_norm
           AND (v_acao = 'REMANEJAMENTO'
                OR v_loja_id IS NULL
                OR s.loja_id IS NOT DISTINCT FROM v_loja_id);
    END IF;

    IF v_acao IN ('INICIO', 'REMANEJAMENTO') THEN
        INSERT INTO public.supervisor_vigencia
            (nome, loja_id, vigencia_inicio, origem)
        VALUES (btrim(p_nome), v_loja_id, p_data_efetiva, 'MANUAL');
        v_abertas := 1;

        INSERT INTO public.supervisores (nome, loja_id, regiao_id)
        SELECT btrim(p_nome), v_loja_id, l.regiao_id
        FROM public.lojas l WHERE l.id = v_loja_id
        ON CONFLICT (nome, loja_id) DO NOTHING;
    END IF;

    RETURN format('%s: %s em %s (%s fechada(s), %s aberta(s))',
                  v_acao, p_nome, p_data_efetiva, v_fechadas, v_abertas);
END;
$$;

COMMENT ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT) IS
    'Aplica INICIO / FIM / REMANEJAMENTO / CORRIGIR_INICIO do papel de '
    'supervisor, atomico: mantem supervisor_vigencia e `supervisores` em '
    'sincronia. CORRIGIR_INICIO move a data de uma vigencia ABERTA (o que '
    'INICIO nao faz, por ser idempotente) e recusa invadir janela ja '
    'fechada. Toda escrita daqui carimba origem = MANUAL (migration 113): '
    'e o caminho explicito de correcao humana, e e o que a guarda de '
    'fn_supervisores_replace protege.';

REVOKE ALL ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    TO service_role;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) A coluna existe e TODAS as linhas atuais sao LEGADO:
--
--    SELECT origem, count(*) FROM supervisor_vigencia GROUP BY origem;
--    -- esperado: uma linha so, LEGADO, com o total da tabela
--    --           (medido em 2026-09-09: 59 linhas, 47 abertas + 12 fechadas).
--
-- 2) O CHECK recusa valor fora do vocabulario:
--
--    -- deve falhar com chk_sv_origem:
--    -- UPDATE supervisor_vigencia SET origem = 'X'
--    --  WHERE id = (SELECT id FROM supervisor_vigencia LIMIT 1);
--
-- 3) A guarda funciona ponta a ponta. Em ambiente de teste, marque uma
--    janela como MANUAL, rode o import sem aquele par e confirme que ela
--    NAO fechou e saiu em `manuais_preservadas`:
--
--    -- UPDATE supervisor_vigencia SET origem = 'MANUAL' WHERE id = '<uuid>';
--    -- SELECT public.fn_supervisores_replace('<payload sem esse par>');
--    -- esperado: vigencia_fim continua NULL; o nome aparece em
--    --           envelope->'manuais_preservadas'.
--
-- 4) fn_aplicar_mudanca_supervisor carimba MANUAL:
--
--    SELECT public.fn_aplicar_mudanca_supervisor(
--        '<NOME>', '<LOJA>', DATE '2026-10-01', 'INICIO');
--    SELECT origem FROM supervisor_vigencia
--     WHERE nome_normalizado = '<NOME>' AND vigencia_fim IS NULL;
--    -- esperado: MANUAL
--
--
-- NAO INCLUIDO DE PROPOSITO
-- -------------------------
-- As 2 linhas que a 110 escreveu (HUGO aberto em MADUREIRA desde
-- 2026-09-01; BARBARA fechada na mesma data) sao as unicas correcoes
-- humanas desta tabela que se pode provar sem inferencia — foram escritas
-- por migration nossa, ha um dia. Elas ficam LEGADO como todo o resto,
-- pela decisao de nao fazer backfill.
--
-- Se quiser proteger so essas duas, o comando e este, e nada mais:
--
--    UPDATE supervisor_vigencia v
--       SET origem = 'MANUAL'
--      FROM lojas l
--     WHERE l.id = v.loja_id
--       AND l.nome = 'HELP MADUREIRA'
--       AND v.nome_normalizado IN ('HUGO SANTOS BENTO DA SILVA',
--                                  'BARBARA DE SOUZA PECANHA')
--       AND DATE '2026-09-01' IN (v.vigencia_inicio, v.vigencia_fim);
--
--    -- esperado: UPDATE 2 (Hugo aberto desde 01/09; Barbara fechada em 01/09)
