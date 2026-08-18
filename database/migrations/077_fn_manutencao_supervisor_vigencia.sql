-- =====================================================
-- Migracao 077: manutencao do ledger supervisor_vigencia
--
--   (a) fn_aplicar_mudanca_supervisor(nome, loja, data_efetiva, acao)
--       — operacao atomica p/ promocao, remanejamento e saida.
--   (b) CREATE OR REPLACE fn_supervisores_replace(p_rows jsonb)
--       — o import da planilha deixa de dar DELETE cego e passa a
--         DIFERENCIAR contra as linhas abertas do ledger.
--
-- Estagio 2 do rollout da 076. Ainda NAO muda numero publicado: nada
-- le o ledger antes da 079.
--
-- Motivo (076): `supervisores` e a foto do presente e era usada como
-- filtro retroativo sobre toda a historia. Sem manutencao versionada,
-- cada promocao apagava o passado de consultor da pessoa e cada saida
-- da planilha devolvia o passado de supervisor dela para os rankings.
--
-- DATA EFETIVA vs ANCORA DE LEITURA — separacao deliberada:
--   * o ledger guarda a data REAL do evento (04/08/2026 = 04/08/2026);
--   * a ancora "papel vigente no 1o dia da competencia" e regra de
--     LEITURA, aplicada na 079.
--   Assim o ETL nao precisa conhecer a ancora: promovido em 04/08 ou
--   importado em 18/08, os dois caem em agosto e a leitura resolve
--   igual (agosto fecha como consultor, setembro e o 1o mes como
--   supervisor). Guardar a data real tambem deixa a ancora
--   reversivel — mudar a regra e reescrever a 079, nao o historico.
--
-- Por isso fn_supervisores_replace MANTEM a assinatura (p_rows jsonb)
-- e deriva a data efetiva internamente (current_date). Adicionar um
-- parametro com DEFAULT criaria uma SEGUNDA funcao (CREATE OR REPLACE
-- casa por assinatura) e a chamada de 1 argumento do angry-man ficaria
-- ambigua — "function is not unique". Consequencia pratica: **o
-- angry-man nao precisa de redeploy** para esta migration.
--
-- Executar no Supabase SQL Editor, depois da 076.
-- =====================================================


-- ===========================================
-- 1. fn_aplicar_mudanca_supervisor
--
-- Padrao da 049 (fn_aplicar_remanejamento_regiao): tudo dentro de uma
-- funcao plpgsql => 1 transacao. Mantem as DUAS pontas em sincronia,
-- como a 049 faz com lojas.regiao_id:
--   1. o ledger (janelas historicas);
--   2. `supervisores` (ponteiro do organograma atual).
--
-- acao:
--   'INICIO'        promocao/contratacao como supervisor da loja.
--   'FIM'           saida da supervisao (desligamento ou rebaixamento).
--                   Sem loja => encerra TODAS as lojas da pessoa.
--   'REMANEJAMENTO' troca de loja: encerra as abertas e abre na nova.
--
-- Idempotente: repetir 'INICIO' com a mesma loja, ou 'FIM' de quem ja
-- nao supervisiona, e no-op.
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
BEGIN
    v_acao := upper(btrim(coalesce(p_acao, '')));
    IF v_acao NOT IN ('INICIO', 'FIM', 'REMANEJAMENTO') THEN
        RAISE EXCEPTION
            'acao invalida: % (use INICIO, FIM ou REMANEJAMENTO)', p_acao;
    END IF;

    v_nome_norm := upper(regexp_replace(
        btrim(coalesce(p_nome, '')), '[[:space:]]+', ' ', 'g'));
    IF v_nome_norm = '' THEN
        RAISE EXCEPTION 'nome do supervisor vazio';
    END IF;

    IF p_data_efetiva IS NULL THEN
        RAISE EXCEPTION 'data_efetiva obrigatoria (nome: %)', p_nome;
    END IF;

    -- Loja: obrigatoria em INICIO/REMANEJAMENTO, opcional em FIM.
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

    -- Idempotencia do INICIO: ja ha linha aberta nessa loja => no-op,
    -- so garante o ponteiro.
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

    -- Guarda temporal (049): a data efetiva tem de ser POSTERIOR ao
    -- inicio de toda linha aberta que sera fechada — senao criaria
    -- janela invalida (chk_sv_vigencia_ordem) ou sobreposta.
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

    -- 1) Encerrar vigencias abertas (FIM e REMANEJAMENTO).
    IF v_acao IN ('FIM', 'REMANEJAMENTO') THEN
        UPDATE public.supervisor_vigencia
           SET vigencia_fim = p_data_efetiva
         WHERE nome_normalizado = v_nome_norm
           AND vigencia_fim IS NULL
           AND (v_acao = 'REMANEJAMENTO'
                OR v_loja_id IS NULL
                OR loja_id IS NOT DISTINCT FROM v_loja_id);
        GET DIAGNOSTICS v_fechadas = ROW_COUNT;

        -- Ponteiro atual: o par deixa de existir na foto.
        DELETE FROM public.supervisores s
         WHERE upper(regexp_replace(btrim(s.nome), '[[:space:]]+', ' ', 'g'))
               = v_nome_norm
           AND (v_acao = 'REMANEJAMENTO'
                OR v_loja_id IS NULL
                OR s.loja_id IS NOT DISTINCT FROM v_loja_id);
    END IF;

    -- 2) Abrir a nova vigencia (INICIO e REMANEJAMENTO).
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
    'Aplica INICIO / FIM / REMANEJAMENTO do papel de supervisor a partir '
    'de data_efetiva, atomico: mantem supervisor_vigencia (janelas) e '
    '`supervisores` (ponteiro atual) em sincronia. Idempotente. Usada '
    'para correcoes retroativas — o caminho do dia a dia e '
    'fn_supervisores_replace. Escrita: so service_role/owner.';

REVOKE ALL ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_aplicar_mudanca_supervisor(TEXT, TEXT, DATE, TEXT)
    TO service_role;


-- ===========================================
-- 2. fn_supervisores_replace — agora ledger-aware
--
-- Mantem TODAS as garantias da 063 (minimo de 30 linhas, advisory lock
-- 20260709, DELETE+INSERT de `supervisores` na mesma transacao,
-- DISTINCT ON deduplicando inclusive pares com loja NULL, mesmo
-- envelope de retorno) e acrescenta o diff do ledger:
--
--   * par (pessoa, loja) na planilha SEM linha aberta  => abre vigencia;
--   * linha aberta AUSENTE da planilha                 => fecha vigencia;
--   * par presente dos dois lados                      => intocado.
--
-- `supervisores` continua sendo reescrita por inteiro — ela e a foto,
-- e o ledger e que passa a ser a memoria. Sem isso, a 063 apagava
-- historia a cada rodizio: foi assim que os 5 ex-supervisores sumiram
-- e 86 contratos voltaram a contar como producao de consultor.
--
-- data efetiva = current_date (data real do evento). A ancora de
-- leitura (1o dia da competencia) fica na 079 — ver cabecalho.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_supervisores_replace(p_rows jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_min_linhas   integer := 30;
    v_payload_len  integer;
    v_count_before integer := 0;
    v_count_after  integer := 0;
    v_sem_loja     integer := 0;
    v_vig_abertas  integer := 0;
    v_vig_fechadas integer := 0;
    v_data_efetiva date := current_date;
BEGIN
    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Payload ausente ou nao e um array JSON.'
        );
    END IF;

    v_payload_len := jsonb_array_length(p_rows);

    IF v_payload_len < v_min_linhas THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format(
                'Planilha com %s linhas — abaixo do minimo esperado (%s). '
                'Substituicao abortada (base preservada).',
                v_payload_len, v_min_linhas
            )
        );
    END IF;

    PERFORM pg_advisory_xact_lock(20260709);

    SELECT count(*) INTO v_count_before FROM supervisores;

    -- Foto normalizada da planilha, deduplicada (regra da 063).
    CREATE TEMP TABLE _sup_incoming ON COMMIT DROP AS
    SELECT DISTINCT ON (r.nome_norm, r.loja_key)
        r.nome,
        r.loja_id,
        COALESCE(l.regiao_id, r.regiao_id) AS regiao_id,
        r.nome_norm,
        r.loja_key
    FROM (
        SELECT
            j.nome,
            j.loja_id,
            j.regiao_id,
            upper(regexp_replace(btrim(j.nome), '[[:space:]]+', ' ', 'g'))
                AS nome_norm,
            coalesce(j.loja_id, '00000000-0000-0000-0000-000000000000'::uuid)
                AS loja_key
        FROM jsonb_to_recordset(p_rows)
             AS j(nome text, loja_id uuid, regiao_id uuid)
        WHERE j.nome IS NOT NULL AND btrim(j.nome) <> ''
    ) r
    LEFT JOIN lojas l ON l.id = r.loja_id;

    -- (a) Fecha vigencias abertas que sumiram da planilha.
    --     A guarda temporal evita janela invalida quando a linha foi
    --     aberta hoje mesmo (chk_sv_vigencia_ordem).
    UPDATE supervisor_vigencia v
       SET vigencia_fim = v_data_efetiva
     WHERE v.vigencia_fim IS NULL
       AND v.vigencia_inicio < v_data_efetiva
       AND NOT EXISTS (
           SELECT 1 FROM _sup_incoming i
           WHERE i.nome_norm = v.nome_normalizado
             AND i.loja_key = coalesce(
                 v.loja_id, '00000000-0000-0000-0000-000000000000'::uuid)
       );
    GET DIAGNOSTICS v_vig_fechadas = ROW_COUNT;

    -- (b) Abre vigencia para pares novos da planilha.
    INSERT INTO supervisor_vigencia (nome, loja_id, vigencia_inicio)
    SELECT i.nome, i.loja_id, v_data_efetiva
    FROM _sup_incoming i
    WHERE NOT EXISTS (
        SELECT 1 FROM supervisor_vigencia v
        WHERE v.nome_normalizado = i.nome_norm
          AND coalesce(v.loja_id, '00000000-0000-0000-0000-000000000000'::uuid)
              = i.loja_key
          AND v.vigencia_fim IS NULL
    );
    GET DIAGNOSTICS v_vig_abertas = ROW_COUNT;

    -- (c) `supervisores` segue sendo a foto: reescrita por inteiro.
    --     `WHERE true` requerido pela extensao safeupdate do Supabase.
    DELETE FROM supervisores WHERE true;

    INSERT INTO supervisores (nome, loja_id, regiao_id)
    SELECT i.nome, i.loja_id, i.regiao_id FROM _sup_incoming i;

    GET DIAGNOSTICS v_count_after = ROW_COUNT;

    SELECT count(*) INTO v_sem_loja
    FROM supervisores
    WHERE loja_id IS NULL;

    RETURN jsonb_build_object(
        'count',            v_count_after,
        'count_before',     v_count_before,
        'sem_loja',         v_sem_loja,
        'vigencias_abertas',  v_vig_abertas,
        'vigencias_fechadas', v_vig_fechadas,
        'data_efetiva',     v_data_efetiva,
        'error',            NULL
    );

EXCEPTION WHEN OTHERS THEN
    -- Transacao implicita revertida: nem a foto nem o ledger persistem.
    RETURN jsonb_build_object(
        'count', 0,
        'error', SQLERRM
    );
END;
$$;

COMMENT ON FUNCTION public.fn_supervisores_replace(jsonb) IS
    'Substitui atomicamente `supervisores` a partir da planilha '
    '(angry-man) E versiona a mudanca em supervisor_vigencia: par novo '
    'abre vigencia, par ausente fecha (nao apaga historia). Data '
    'efetiva = current_date; a ancora de leitura (1o dia da '
    'competencia) mora na 079. Assinatura inalterada — angry-man nao '
    'precisa de redeploy. Minimo de 30 linhas, advisory lock 20260709. '
    'SECURITY DEFINER; EXECUTE so para service_role.';

REVOKE ALL ON FUNCTION public.fn_supervisores_replace(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_supervisores_replace(jsonb) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_supervisores_replace(jsonb) TO service_role;


-- ===========================================
-- Validacao pos-migracao
-- ===========================================
-- 1) Guarda de minimo continua de pe (nao toca a base nem o ledger):
--
--    SELECT public.fn_supervisores_replace(
--        jsonb_build_array(jsonb_build_object('nome', 'X')));
--    -- { "count": 0, "error": "Planilha com 1 linhas ..." }
--    SELECT count(*) FROM supervisores;         -- inalterado
--    SELECT count(*) FROM supervisor_vigencia;  -- inalterado
--
-- 2) Invariante apos qualquer import: linha aberta do ledger espelha
--    exatamente a foto.
--
--    SELECT
--      (SELECT count(*) FROM supervisor_vigencia WHERE vigencia_fim IS NULL)
--        AS abertas,
--      (SELECT count(*) FROM supervisores) AS foto;
--    -- Esperado: iguais.
--
--    SELECT s.nome, l.nome AS loja
--    FROM supervisores s
--    LEFT JOIN lojas l ON l.id = s.loja_id
--    WHERE NOT EXISTS (
--        SELECT 1 FROM supervisor_vigencia v
--        WHERE v.nome_normalizado = upper(regexp_replace(
--                  btrim(s.nome), '[[:space:]]+', ' ', 'g'))
--          AND v.loja_id IS NOT DISTINCT FROM s.loja_id
--          AND v.vigencia_fim IS NULL);
--    -- Esperado: 0 linhas.
--
-- 3) Smoke da funcao de correcao (rollback manual no fim):
--
--    BEGIN;
--    SELECT public.fn_aplicar_mudanca_supervisor(
--        'NOME DE TESTE', 'HELP BANGU', DATE '2026-08-01', 'INICIO');
--    SELECT public.fn_aplicar_mudanca_supervisor(
--        'NOME DE TESTE', NULL, DATE '2026-09-01', 'FIM');
--    SELECT nome, vigencia_inicio, vigencia_fim
--    FROM supervisor_vigencia WHERE nome = 'NOME DE TESTE';
--    -- Esperado: 1 linha [2026-08-01, 2026-09-01)
--    ROLLBACK;
-- =====================================================
