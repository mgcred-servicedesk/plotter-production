-- =====================================================
-- Migracao 082: import de supervisores com DATA DE VIGENCIA
--
--   (a) CREATE OR REPLACE fn_supervisores_replace(p_rows jsonb)
--       — cada linha da planilha passa a poder trazer `vigencia_inicio`
--         (coluna DESDE), e a TROCA de supervisor numa loja fecha o
--         antecessor exatamente na data do sucessor.
--   (b) CREATE OR REPLACE fn_aplicar_mudanca_supervisor(...)
--       — nova acao CORRIGIR_INICIO, o caminho explicito para consertar
--         uma vigencia aberta com data errada.
--
-- Motivo: ate aqui o import derivava a data de `current_date` (077).
-- Sob a ancora do dia 1o isso ACERTA enquanto o import acontece no mesmo
-- mes da mudanca — promocao em 04/08 importada em 18/08 da o mesmo
-- resultado. Erra quando o import atrasa para o mes seguinte: a mesma
-- promocao importada em 02/09 abriria vigencia em 02/09 e a pessoa so
-- viraria supervisora em outubro, um mes tarde. A coluna DESDE fecha
-- essa janela e permite registrar mudanca retroativa.
--
-- Decisoes do usuario (2026-08-18):
--   * a data vai na PROPRIA Supervisores.xlsx (coluna DESDE), nao numa
--     aba de eventos nem num formulario — fonte unica, sem risco de a
--     foto e os eventos discordarem (a armadilha da 062);
--   * divergencia entre a planilha e uma vigencia JA aberta e apenas
--     REPORTADA, nunca aplicada em silencio. Um erro de digitacao na
--     coluna nao pode reescrever headcount e produtividade de meses ja
--     publicados — mesmo espirito do minimo de 30 linhas da 063.
--
-- Assinatura INALTERADA nas duas funcoes: `vigencia_inicio` entra no
-- recordset do payload, nao na lista de parametros. Um parametro novo
-- com DEFAULT criaria uma segunda funcao (CREATE OR REPLACE casa por
-- assinatura) e a chamada de 1 argumento do angry-man ficaria ambigua.
-- Retrocompativel: payload sem o campo cai no comportamento da 077.
--
-- Executar no Supabase SQL Editor, depois da 081.
-- =====================================================


-- ===========================================
-- 1. fn_supervisores_replace — com data por linha
--
-- Diff, agora datado:
--   * par na planilha SEM linha aberta  => abre em DESDE (ou hoje);
--   * linha aberta AUSENTE da planilha  => fecha. A data sai por
--     SUCESSAO: se a mesma loja ganhou supervisor novo, fecha na data
--     dele — a cadeira nao fica vaga nem sobreposta. Sem sucessor, cai
--     em current_date e o retorno REPORTA, porque a planilha nao tem
--     como dizer quando alguem que sumiu dela parou;
--   * par presente dos dois lados => intocado; se a data informada
--     diferir da vigente, entra em `divergencias`.
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
    DROP TABLE IF EXISTS _sup_saidas;
    CREATE TEMP TABLE _sup_saidas ON COMMIT DROP AS
    SELECT
        v.id,
        v.nome,
        v.vigencia_inicio,
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
    UPDATE supervisor_vigencia v
       SET vigencia_fim = s.fim
      FROM _sup_saidas s
     WHERE s.id = v.id
       AND s.fim > v.vigencia_inicio;
    GET DIAGNOSTICS v_fechadas = ROW_COUNT;

    SELECT
        count(*) FILTER (WHERE por_sucessao AND fim > vigencia_inicio),
        count(*) FILTER (WHERE NOT por_sucessao AND fim > vigencia_inicio),
        count(*) FILTER (WHERE fim <= vigencia_inicio)
      INTO v_por_sucessao, v_sem_data, v_recusados
    FROM _sup_saidas;

    -- (c) Abre os pares novos na data informada.
    INSERT INTO supervisor_vigencia (nome, loja_id, vigencia_inicio)
    SELECT n.nome, n.loja_id, n.inicio FROM _sup_novos n;
    GET DIAGNOSTICS v_abertas = ROW_COUNT;

    -- (d) Divergencias: planilha discorda de vigencia JA aberta.
    --     Decisao do usuario: apenas reportar. Corrigir e ato explicito,
    --     via fn_aplicar_mudanca_supervisor(..., 'CORRIGIR_INICIO').
    SELECT jsonb_agg(jsonb_build_object(
               'nome', i.nome,
               'loja', l.nome,
               'planilha', i.inicio_informado,
               'ledger', v.vigencia_inicio))
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
    'supervisor_vigencia, usando a data por linha (coluna DESDE) quando '
    'presente. Troca de supervisor na mesma loja fecha o antecessor na '
    'data do sucessor. Saida sem sucessor cai em current_date e e '
    'reportada. Divergencia com vigencia aberta e SO reportada, nunca '
    'aplicada — corrigir e ato explicito (CORRIGIR_INICIO). Assinatura '
    'inalterada; payload sem vigencia_inicio mantem o comportamento da '
    '077. Minimo de 30 linhas, advisory lock 20260709. SECURITY DEFINER; '
    'EXECUTE so para service_role.';

REVOKE ALL ON FUNCTION public.fn_supervisores_replace(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_supervisores_replace(jsonb) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_supervisores_replace(jsonb) TO service_role;


-- ===========================================
-- 2. fn_aplicar_mudanca_supervisor — acao CORRIGIR_INICIO
--
-- Como o import so REPORTA divergencia, e preciso um caminho explicito
-- para consertar uma vigencia aberta com data errada (import atrasado,
-- data digitada errado, promocao descoberta depois). 'INICIO' nao serve:
-- e no-op por idempotencia quando ja existe linha aberta — foi
-- exatamente por isso que a 078 precisou de UPDATEs manuais.
--
-- Guarda de sobreposicao: a data nova nao pode invadir uma janela ja
-- fechada da mesma pessoa/loja, senao o historico passa a ter dois
-- supervisores validos no mesmo instante.
--
-- Resto da funcao identico a 077 (INICIO / FIM / REMANEJAMENTO).
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
           SET vigencia_inicio = p_data_efetiva
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
           SET vigencia_fim = p_data_efetiva
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
            (nome, loja_id, vigencia_inicio)
        VALUES (btrim(p_nome), v_loja_id, p_data_efetiva);
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
    'fechada — e o caminho explicito para as divergencias que o import '
    'apenas reporta. Escrita: so service_role/owner.';

REVOKE ALL ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    TO service_role;


-- ===========================================
-- Validacao pos-migracao
-- ===========================================
-- 1) Retrocompatibilidade — payload SEM vigencia_inicio segue valendo
--    (guarda de minimo continua abortando sem tocar na base):
--
--    SELECT fn_supervisores_replace(
--        jsonb_build_array(jsonb_build_object('nome', 'X')));
--    -- { "count": 0, "error": "Planilha com 1 linhas ..." }
--
-- 2) Smoke da sucessao, com rollback (nao persiste):
--
--    BEGIN;
--    SELECT fn_aplicar_mudanca_supervisor(
--        'SUP TESTE A', 'HELP BANGU', DATE '2026-01-01', 'INICIO');
--    -- monte um payload >= 30 linhas com a foto atual, troque a linha
--    -- de HELP BANGU para 'SUP TESTE B' com DESDE = 2026-09-01 e chame
--    -- fn_supervisores_replace. Esperado no retorno:
--    --   fechadas_por_sucessao >= 1, fechadas_sem_data = 0
--    -- e no ledger: A encerrado em 2026-09-01, B aberto em 2026-09-01.
--    ROLLBACK;
--
-- 3) CORRIGIR_INICIO e sua guarda:
--
--    BEGIN;
--    SELECT fn_aplicar_mudanca_supervisor(
--        'SUP TESTE C', 'HELP BANGU', DATE '2026-09-01', 'INICIO');
--    SELECT fn_aplicar_mudanca_supervisor(
--        'SUP TESTE C', 'HELP BANGU', DATE '2026-08-01', 'CORRIGIR_INICIO');
--    -- Esperado: 'CORRIGIR_INICIO: ... 2026-09-01 -> 2026-08-01'
--    ROLLBACK;
--
-- 4) Divergencia so reporta, nao aplica: reenviar a foto atual com um
--    DESDE diferente do vigente para alguem ja aberto.
--    Esperado: `divergencias` com 1 entrada e vigencia_inicio INTACTA.
-- =====================================================
