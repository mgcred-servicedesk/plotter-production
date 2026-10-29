-- =====================================================
-- Migracao 144: regra unica de nome de pessoa (fn_normalizar_nome)
-- Data: 2026-10-29
-- Depende de: 089, 090, 101, 113, 115, 116, 120, 129 e 136 (versoes
--             vigentes das 12 funcoes substituidas aqui)
--
-- PROBLEMA
-- Dashboard e Caderno comparam o nome do consultor no contrato com o do
-- supervisor e com os ledgers de vigencia, mas cada lado fazia metade da
-- normalizacao:
--   SQL (076 em diante): upper + btrim + espacos colapsados, SEM dobrar
--                        acento;
--   Python (normalizar_nome, src/shared/texto.py): upper + strip +
--                        acento dobrado, SEM colapsar espaco interno.
-- `JOAO DA SILVA` x `JOÃO DA SILVA` casava no dashboard e nao no Caderno;
-- `MARIA  SILVA` (espaco duplo) casava no Caderno e nao no dashboard.
--
-- DECISAO DO USUARIO (2026-10-29): os dois lados aplicam as duas regras —
-- tirar acento e colapsar espaco. Esta migration faz o lado SQL; o
-- normalizar_nome ganhou o colapso de espaco no mesmo dia. Mudar uma das
-- duas sem a outra volta a separar dashboard e Caderno.
--
-- O QUE MUDA
--   1. public.fn_normalizar_nome(text): NFKD, remove os diacriticos
--      combinantes, colapsa [[:space:]], btrim e upper. SQL, IMMUTABLE,
--      PARALLEL SAFE e sem SET search_path (padrao da 067/130: inlinavel).
--      Sem unaccent, que nao esta instalada: normalize() e IMMUTABLE no
--      PG 17 e o banco e UTF8. O NFKD tambem troca o espaco nao separavel
--      (U+00A0) por espaco comum.
--   2. nome_normalizado de supervisor_vigencia, consultor_vigencia e
--      consultor_afastamento passa a ser gerado pela funcao (ALTER COLUMN
--      ... SET EXPRESSION, PG 17). Reescreve as tres tabelas e os indices.
--   3. As 12 funcoes vivas que normalizavam inline trocam a expressao
--      antiga pela funcao, mantendo o argumento: 35 ocorrencias, nada mais
--      muda. Corpos copiados das migrations vigentes e conferidos por md5
--      contra o prosrc em producao em 2026-10-29 (o banco guarda CRLF na
--      maioria; o repositorio, LF). Cabecalhos conferidos contra pg_proc
--      (SECURITY DEFINER e SETs), porque CREATE OR REPLACE redefine todos.
--      Os SECURITY DEFINER e os search_path = '' chamam a funcao
--      qualificada (public.fn_normalizar_nome).
--
-- O QUE NAO MUDA (medido em 2026-10-29)
--   - Nenhum nome tem acento ou espaco repetido hoje: 0 de 61 linhas em
--     supervisor_vigencia, 0 de 425 em consultor_vigencia, 0 de 2 em
--     consultor_afastamento, 0 de 461 em consultores, 0 de 45 em
--     supervisores e 0 de 473 nomes de consultor em contratos pagos desde
--     2025. Nenhuma chave muda, nenhum indice unico colide e nenhum numero
--     do dashboard ou do Caderno se move. A troca e preventiva.
--   - contratos.cliente_norm (nome de cliente, nao de pessoa da rede)
--     fica como esta.
--
-- CUIDADO
--   - O consultantId do snapshot individual e o nome normalizado. Um nome
--     com acento que entrar daqui em diante ja nasce na regra nova; nao ha
--     historico a reconciliar, porque nao havia nenhum.
--   - Alterar fn_normalizar_nome depois exige recalcular as colunas
--     geradas (SET EXPRESSION de novo): CREATE OR REPLACE nao regrava
--     valor ja armazenado.
--
-- Executar no Supabase SQL Editor. Nao exige deploy do Bereshit nem do
-- dashboard; o normalizar_nome pode sair antes ou depois.
-- =====================================================

-- ===========================================
-- 1. A regra
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_normalizar_nome(p_nome TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT upper(btrim(regexp_replace(
        regexp_replace(normalize(p_nome, NFKD), '[̀-ͯ]', '', 'g'),
        '[[:space:]]+', ' ', 'g'
    )));
$$;

COMMENT ON FUNCTION public.fn_normalizar_nome(TEXT) IS
    'Chave de comparacao de nome de pessoa entre fontes: NFKD sem '
    'diacriticos, espacos colapsados, btrim e upper. NULL fica NULL. '
    'Espelhada em normalizar_nome (src/shared/texto.py) do dashboard — '
    'mudar uma exige mudar a outra e recalcular as colunas geradas.';

GRANT EXECUTE ON FUNCTION public.fn_normalizar_nome(TEXT)
    TO anon, authenticated;

-- ===========================================
-- 2. Colunas geradas dos ledgers
-- ===========================================

ALTER TABLE public.supervisor_vigencia
    ALTER COLUMN nome_normalizado
    SET EXPRESSION AS (public.fn_normalizar_nome(nome));

ALTER TABLE public.consultor_vigencia
    ALTER COLUMN nome_normalizado
    SET EXPRESSION AS (public.fn_normalizar_nome(nome));

ALTER TABLE public.consultor_afastamento
    ALTER COLUMN nome_normalizado
    SET EXPRESSION AS (public.fn_normalizar_nome(nome));

COMMENT ON COLUMN public.supervisor_vigencia.nome_normalizado IS
    'Gerada por fn_normalizar_nome(nome) (144). Chave de match com '
    'consultores.nome / v_contratos_dashboard.consultor.';

COMMENT ON COLUMN public.consultor_vigencia.nome_normalizado IS
    'Gerada por fn_normalizar_nome(nome) (144). Chave de match com '
    'consultores.nome, supervisor_vigencia.nome_normalizado e '
    'v_contratos_dashboard.consultor.';

-- ===========================================
-- 3. Funcoes que normalizavam inline
-- ===========================================

-- fn_registrar_afastamento — vigente na 089; 1 troca(s)
CREATE OR REPLACE FUNCTION public.fn_registrar_afastamento(
    p_nome   TEXT,
    p_tipo   TEXT,
    p_inicio DATE,
    p_fim    DATE DEFAULT NULL,
    p_origem TEXT DEFAULT 'ETL'
)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_nn TEXT;
    v_id UUID;
BEGIN
    v_nn := public.fn_normalizar_nome(btrim(coalesce(p_nome, '')));
    IF v_nn = '' THEN
        RAISE EXCEPTION 'nome vazio';
    END IF;

    SELECT id INTO v_id
    FROM consultor_afastamento
    WHERE nome_normalizado = v_nn
      AND data_fim IS NULL;

    IF v_id IS NULL THEN
        INSERT INTO consultor_afastamento (nome, tipo, data_inicio, data_fim, origem)
        VALUES (btrim(p_nome), p_tipo, p_inicio, p_fim, p_origem);
        RETURN 'ABERTO';
    END IF;

    -- Ja existe janela aberta: fechar (se veio p_fim) ou corrigir inicio.
    UPDATE consultor_afastamento
    SET data_fim    = coalesce(p_fim, data_fim),
        data_inicio = p_inicio,
        tipo        = p_tipo,
        origem      = p_origem
    WHERE id = v_id;

    RETURN CASE WHEN p_fim IS NOT NULL THEN 'FECHADO' ELSE 'ATUALIZADO' END;
END;
$$;


-- fn_fechar_afastamentos_por_producao — vigente na 089; 1 troca(s)
CREATE OR REPLACE FUNCTION public.fn_fechar_afastamentos_por_producao(
    p_ate DATE DEFAULT current_date
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_fechados integer;
BEGIN
    WITH retorno AS (
        SELECT
            a.id,
            min(ct.data_cadastro::date) AS dia_retorno
        FROM consultor_afastamento a
        JOIN consultores cs
          ON public.fn_normalizar_nome(btrim(coalesce(cs.nome, ''))) = a.nome_normalizado
        JOIN contratos ct
          ON ct.consultor_id = cs.id
        WHERE a.data_fim IS NULL
          AND ct.data_cadastro::date > a.data_inicio
          AND ct.data_cadastro::date <= p_ate
        GROUP BY a.id
    )
    UPDATE consultor_afastamento a
    SET data_fim = r.dia_retorno
    FROM retorno r
    WHERE a.id = r.id;

    GET DIAGNOSTICS v_fechados = ROW_COUNT;
    RETURN v_fechados;
END;
$$;


-- fn_afastamentos_replace — vigente na 090; 2 troca(s)
CREATE OR REPLACE FUNCTION public.fn_afastamentos_replace(
    p_rows jsonb,
    p_modo text DEFAULT 'SNAPSHOT'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $fn$
DECLARE
    v_modo        text;
    v_len         integer;
    v_invalidas   jsonb;
    v_row         jsonb;
    v_nome        text;
    v_nn          text;
    v_tipo        text;
    v_inicio      date;
    v_fim         date;
    v_obs         text;
    v_id          uuid;
    v_ins         integer := 0;
    v_upd         integer := 0;
    v_fech_prod   integer := 0;
    v_fech_aus    integer := 0;
    v_abertos_ini integer;
BEGIN
    v_modo := upper(btrim(coalesce(p_modo, 'SNAPSHOT')));

    IF v_modo NOT IN ('SNAPSHOT', 'UPSERT') THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format('Modo invalido: %s. Use SNAPSHOT ou UPSERT.', p_modo));
    END IF;

    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Payload ausente ou nao e um array JSON.');
    END IF;

    v_len := jsonb_array_length(p_rows);

    IF v_modo = 'SNAPSHOT' AND v_len = 0 THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'SNAPSHOT vazio recusado: fecharia todas as janelas '
                     'abertas de uma vez. Para encerrar afastamentos, use '
                     'modo UPSERT com data_fim preenchida por pessoa.');
    END IF;

    -- Serializa cargas concorrentes (mesmo padrao da 077).
    PERFORM pg_advisory_xact_lock(20260820);

    -- ---- validacao TOTAL antes de aplicar QUALQUER linha ----
    SELECT jsonb_agg(r) INTO v_invalidas
    FROM jsonb_array_elements(p_rows) r
    WHERE btrim(coalesce(r->>'nome', '')) = ''
       OR upper(btrim(coalesce(r->>'tipo', ''))) NOT IN (
              'AFASTAMENTO_MEDICO', 'LICENCA_MATERNIDADE',
              'LICENCA_NAO_REMUNERADA', 'FERIAS')
       OR coalesce(r->>'data_inicio', '') !~ '^\d{4}-\d{2}-\d{2}$'
       OR (coalesce(r->>'data_fim', '') <> ''
           AND r->>'data_fim' !~ '^\d{4}-\d{2}-\d{2}$');

    IF v_invalidas IS NOT NULL THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Linhas invalidas — nada foi aplicado.',
            'invalidas', v_invalidas);
    END IF;

    SELECT count(*) INTO v_abertos_ini
    FROM consultor_afastamento WHERE data_fim IS NULL;

    -- ---- aplica linha a linha ----
    -- Volume e de dezenas, nao de milhares: laco explicito vale mais que
    -- DML em lote pela clareza da resolucao de identidade abaixo.
    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows) LOOP
        v_nome   := btrim(v_row->>'nome');
        v_nn     := public.fn_normalizar_nome(v_nome);
        v_tipo   := upper(btrim(v_row->>'tipo'));
        v_inicio := (v_row->>'data_inicio')::date;
        v_fim    := nullif(btrim(coalesce(v_row->>'data_fim', '')), '')::date;
        v_obs    := nullif(btrim(coalesce(v_row->>'observacao', '')), '');

        -- Resolucao de identidade, nesta ordem:
        --   1. mesma pessoa e mesmo data_inicio  -> e a MESMA janela;
        --   2. senao, a janela ABERTA da pessoa  -> e o caso "corrigir
        --      informacao equivocada" (inclusive data_inicio errada);
        --   3. senao, e afastamento novo.
        SELECT id INTO v_id
        FROM consultor_afastamento
        WHERE nome_normalizado = v_nn AND data_inicio = v_inicio;

        IF v_id IS NULL THEN
            SELECT id INTO v_id
            FROM consultor_afastamento
            WHERE nome_normalizado = v_nn AND data_fim IS NULL;
        END IF;

        IF v_id IS NULL THEN
            INSERT INTO consultor_afastamento
                (nome, tipo, data_inicio, data_fim, origem, observacao)
            VALUES (v_nome, v_tipo, v_inicio, v_fim, 'ETL', v_obs);
            v_ins := v_ins + 1;
        ELSE
            UPDATE consultor_afastamento
            SET nome        = v_nome,
                tipo        = v_tipo,
                data_inicio = v_inicio,
                data_fim    = v_fim,
                origem      = 'ETL',
                observacao  = coalesce(v_obs, observacao)
            WHERE id = v_id;
            v_upd := v_upd + 1;
        END IF;
    END LOOP;

    -- ---- fechamento (so no SNAPSHOT) ----
    IF v_modo = 'SNAPSHOT' THEN
        -- 1o: producao fecha com data exata (ver cabecalho).
        v_fech_prod := public.fn_fechar_afastamentos_por_producao();

        -- 2o: sumiu do arquivo e nao tem producao que prove o dia.
        -- O filtro data_inicio < current_date respeita chk_ca_ordem:
        -- janela aberta HOJE nao pode fechar HOJE.
        UPDATE consultor_afastamento a
        SET data_fim = current_date
        WHERE a.data_fim IS NULL
          AND a.data_inicio < current_date
          AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements(p_rows) r
              WHERE public.fn_normalizar_nome(btrim(coalesce(r->>'nome', ''))) = a.nome_normalizado);
        GET DIAGNOSTICS v_fech_aus = ROW_COUNT;
    END IF;

    RETURN jsonb_build_object(
        'modo',                  v_modo,
        'count',                 v_len,
        'inseridos',             v_ins,
        'atualizados',           v_upd,
        'fechados_por_producao', v_fech_prod,
        'fechados_por_ausencia', v_fech_aus,
        'abertos_antes',         v_abertos_ini,
        'abertos_depois', (SELECT count(*) FROM consultor_afastamento
                           WHERE data_fim IS NULL));
END;
$fn$;


-- obter_produtividade_individual — vigente na 101; 2 troca(s)
CREATE OR REPLACE FUNCTION public.obter_produtividade_individual(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE sql
STABLE
PARALLEL SAFE
SET search_path = ''
AS $fn$
WITH
periodo_base AS (
    SELECT
        make_date(p_ano, p_mes, 1) AS mes_inicio,
        (make_date(p_ano, p_mes, 1) + interval '1 month')::date AS mes_fim
),
periodo AS (
    SELECT
        pb.*,
        (pb.mes_fim - 1) AS ancora,
        ((pb.mes_fim - 1)
          - (extract(isodow FROM pb.mes_fim - 1)::integer % 7))::date
            AS semana_fim
    FROM periodo_base pb
),
parametros AS (
    SELECT
        p.*,
        (p.semana_fim - 55)::date AS semana_inicio
    FROM periodo p
),
dias_calendario AS (
    SELECT g::date AS dia
    FROM parametros p
    CROSS JOIN LATERAL generate_series(
        least(p.mes_inicio, p.semana_inicio),
        greatest(p.mes_fim - 1, p.semana_fim),
        interval '1 day'
    ) g
),
dias_uteis AS (
    SELECT d.dia
    FROM dias_calendario d
    WHERE extract(isodow FROM d.dia) < 6
      AND NOT EXISTS (
          SELECT 1
          FROM public.feriados f
          WHERE f.data = d.dia
      )
),
semanas AS (
    SELECT
        s::date AS semana_inicio,
        (s + interval '6 days')::date AS semana_fim
    FROM parametros p
    CROSS JOIN LATERAL generate_series(
        p.semana_inicio,
        p.semana_fim - 6,
        interval '7 days'
    ) s
),
dias_periodo_mensal AS (
    SELECT count(*)::integer AS total
    FROM dias_uteis d
    CROSS JOIN parametros p
    WHERE d.dia >= p.mes_inicio
      AND d.dia < p.mes_fim
),
dias_periodo_semanal AS (
    SELECT
        s.semana_inicio,
        s.semana_fim,
        count(d.dia)::integer AS total
    FROM semanas s
    LEFT JOIN dias_uteis d
      ON d.dia BETWEEN s.semana_inicio AND s.semana_fim
    GROUP BY s.semana_inicio, s.semana_fim
),
supervisores AS (
    -- Mesma ancora de competencia da 085/096: quem era supervisor no
    -- ultimo dia do mes fica fora do numerador e do denominador inteiro.
    SELECT DISTINCT sv.nome_normalizado AS consultant_id
    FROM public.supervisor_vigencia sv
    CROSS JOIN parametros p
    WHERE sv.vigencia_inicio <= p.ancora
      AND (sv.vigencia_fim IS NULL OR sv.vigencia_fim > p.ancora)
),
vinculos_diarios_base AS (
    SELECT
        d.dia,
        cv.nome_normalizado AS consultant_id,
        cv.nome AS consultant,
        cv.loja_id,
        l.nome AS store,
        coalesce(r.nome, l.gerente, '') AS manager
    FROM public.consultor_vigencia cv
    JOIN dias_uteis d
      ON d.dia >= cv.vigencia_inicio
     AND (cv.vigencia_fim IS NULL OR d.dia < cv.vigencia_fim)
    JOIN public.lojas l
      ON l.id = cv.loja_id
     AND coalesce(l.ativo, true)
    LEFT JOIN LATERAL (
        SELECT lrv.regiao_id
        FROM public.loja_regiao_vigencia lrv
        WHERE lrv.loja_id = cv.loja_id
          AND lrv.vigencia_inicio <= d.dia
          AND (lrv.vigencia_fim IS NULL OR lrv.vigencia_fim > d.dia)
        ORDER BY lrv.vigencia_inicio DESC, lrv.id DESC
        LIMIT 1
    ) rv ON true
    LEFT JOIN public.regioes r
      ON r.id = coalesce(rv.regiao_id, l.regiao_id)
    WHERE cv.nome_normalizado <> ''
      AND upper(btrim(coalesce(l.nome, ''))) <> 'VAI E VEM'
),
vinculos_diarios AS (
    SELECT v.*
    FROM vinculos_diarios_base v
    WHERE NOT EXISTS (
        SELECT 1
        FROM supervisores s
        WHERE s.consultant_id = v.consultant_id
    )
),
eventos_pagos AS (
    -- A view resolve status pago, categoria e valor consolidado. O join
    -- pela PK devolve loja_id sem casar loja por texto.
    SELECT
        v.data_status_pagamento::date AS dia,
        per.mes,
        per.ano,
        public.fn_normalizar_nome(btrim(coalesce(v.consultor, ''))) AS consultant_id,
        coalesce(v.consultor, '') AS consultant,
        c.loja_id,
        coalesce(v.loja, '') AS store,
        coalesce(v.regiao, '') AS manager,
        CASE
            WHEN coalesce(v.conta_valor, true) = false THEN 0
            ELSE coalesce(v.valor_consolidado, 0)
        END::numeric AS paid_effective
    FROM public.v_contratos_dashboard v
    JOIN public.contratos c ON c.id = v.id
    LEFT JOIN public.periodos per ON per.id = v.periodo_id
    LEFT JOIN supervisores s
      ON s.consultant_id = public.fn_normalizar_nome(btrim(coalesce(v.consultor, '')))
    CROSS JOIN parametros p
    WHERE s.consultant_id IS NULL
      AND upper(btrim(coalesce(v.loja, ''))) <> 'VAI E VEM'
      AND (
          (per.mes = p_mes AND per.ano = p_ano)
          OR v.data_status_pagamento::date
               BETWEEN p.semana_inicio AND p.semana_fim
      )
),
denominador_mensal AS (
    SELECT
        v.consultant_id,
        (array_agg(v.consultant ORDER BY v.dia DESC))[1] AS consultant,
        v.loja_id,
        (array_agg(v.store ORDER BY v.dia DESC))[1] AS store,
        (array_agg(v.manager ORDER BY v.dia DESC))[1] AS manager,
        count(*)::integer AS considered_days
    FROM vinculos_diarios v
    CROSS JOIN parametros p
    WHERE v.dia >= p.mes_inicio
      AND v.dia < p.mes_fim
    GROUP BY v.consultant_id, v.loja_id
),
pago_mensal AS (
    SELECT
        e.consultant_id,
        (array_agg(e.consultant ORDER BY e.consultant DESC))[1] AS consultant,
        e.loja_id,
        (array_agg(e.store ORDER BY e.store DESC))[1] AS store,
        (array_agg(e.manager ORDER BY e.manager DESC))[1] AS manager,
        sum(e.paid_effective)::numeric AS paid_effective
    FROM eventos_pagos e
    WHERE e.mes = p_mes AND e.ano = p_ano
    GROUP BY e.consultant_id, e.loja_id
),
mensal AS (
    SELECT
        coalesce(d.consultant_id, pg.consultant_id) AS consultant_id,
        coalesce(d.consultant, pg.consultant, '') AS consultant,
        coalesce(d.loja_id, pg.loja_id) AS loja_id,
        coalesce(d.store, pg.store, '') AS store,
        coalesce(d.manager, pg.manager, '') AS manager,
        coalesce(pg.paid_effective, 0)::numeric AS paid_effective,
        du.total AS period_days,
        coalesce(d.considered_days, 0)::integer AS considered_days
    FROM denominador_mensal d
    FULL JOIN pago_mensal pg
      ON pg.consultant_id = d.consultant_id
     AND pg.loja_id = d.loja_id
    CROSS JOIN dias_periodo_mensal du
),
denominador_semanal AS (
    SELECT
        s.semana_inicio,
        s.semana_fim,
        v.consultant_id,
        (array_agg(v.consultant ORDER BY v.dia DESC))[1] AS consultant,
        v.loja_id,
        (array_agg(v.store ORDER BY v.dia DESC))[1] AS store,
        (array_agg(v.manager ORDER BY v.dia DESC))[1] AS manager,
        count(*)::integer AS considered_days
    FROM semanas s
    JOIN vinculos_diarios v
      ON v.dia BETWEEN s.semana_inicio AND s.semana_fim
    GROUP BY s.semana_inicio, s.semana_fim,
             v.consultant_id, v.loja_id
),
pago_semanal AS (
    SELECT
        date_trunc('week', e.dia)::date AS semana_inicio,
        (date_trunc('week', e.dia)::date + 6) AS semana_fim,
        e.consultant_id,
        (array_agg(e.consultant ORDER BY e.consultant DESC))[1] AS consultant,
        e.loja_id,
        (array_agg(e.store ORDER BY e.store DESC))[1] AS store,
        (array_agg(e.manager ORDER BY e.manager DESC))[1] AS manager,
        sum(e.paid_effective)::numeric AS paid_effective
    FROM eventos_pagos e
    CROSS JOIN parametros p
    WHERE e.dia BETWEEN p.semana_inicio AND p.semana_fim
    GROUP BY date_trunc('week', e.dia)::date,
             e.consultant_id, e.loja_id
),
semanal AS (
    SELECT
        coalesce(d.semana_inicio, pg.semana_inicio) AS semana_inicio,
        coalesce(d.semana_fim, pg.semana_fim) AS semana_fim,
        coalesce(d.consultant_id, pg.consultant_id) AS consultant_id,
        coalesce(d.consultant, pg.consultant, '') AS consultant,
        coalesce(d.loja_id, pg.loja_id) AS loja_id,
        coalesce(d.store, pg.store, '') AS store,
        coalesce(d.manager, pg.manager, '') AS manager,
        coalesce(pg.paid_effective, 0)::numeric AS paid_effective,
        du.total AS period_days,
        coalesce(d.considered_days, 0)::integer AS considered_days
    FROM denominador_semanal d
    FULL JOIN pago_semanal pg
      ON pg.semana_inicio = d.semana_inicio
     AND pg.consultant_id = d.consultant_id
     AND pg.loja_id = d.loja_id
    JOIN dias_periodo_semanal du
      ON du.semana_inicio = coalesce(d.semana_inicio, pg.semana_inicio)
),
duplicidades_dia AS (
    SELECT count(*)::integer AS total
    FROM (
        SELECT v.consultant_id, v.dia
        FROM vinculos_diarios v
        GROUP BY v.consultant_id, v.dia
        HAVING count(*) > 1
    ) x
),
diagnostico AS (
    SELECT
        (SELECT count(*) FROM mensal
         WHERE paid_effective > 0 AND considered_days = 0)::integer
            AS mensal_sem_vinculo,
        (SELECT count(*) FROM semanal
         WHERE paid_effective > 0 AND considered_days = 0)::integer
            AS semanal_sem_vinculo,
        (SELECT total FROM duplicidades_dia) AS vinculo_sobreposto,
        (SELECT coalesce(sum(paid_effective), 0) FROM mensal)::numeric
            AS pago_mensal,
        (SELECT count(*) FROM mensal)::integer AS linhas_mensais,
        (SELECT count(*) FROM semanal)::integer AS linhas_semanais
)
SELECT jsonb_build_object(
    'competence', jsonb_build_object(
        'month', p_mes,
        'year', p_ano,
        'label', format('%s/%s', lpad(p_mes::text, 2, '0'), p_ano)
    ),
    'consultantProductivity', coalesce((
        SELECT jsonb_agg(
            jsonb_build_object(
                'consultantId', m.consultant_id,
                'consultant', m.consultant,
                'storeId', m.loja_id,
                'store', m.store,
                'manager', m.manager,
                'paidEffective', m.paid_effective,
                'periodWorkingDays', m.period_days,
                'consideredWorkingDays', m.considered_days,
                'consideredDaysBasis', 'ELIGIBLE_LINK_DAYS',
                'absenceCoverage', 'NONE',
                'dailyProductivity', CASE
                    WHEN m.considered_days > 0
                    THEN m.paid_effective / m.considered_days
                    ELSE 0
                END,
                'ruleRevision', 1
            )
            ORDER BY m.store, m.consultant_id
        )
        FROM mensal m
    ), '[]'::jsonb),
    'consultantWeeklyProductivity', coalesce((
        SELECT jsonb_agg(
            jsonb_build_object(
                'consultantId', s.consultant_id,
                'consultant', s.consultant,
                'storeId', s.loja_id,
                'store', s.store,
                'manager', s.manager,
                'weekStart', s.semana_inicio,
                'weekEnd', s.semana_fim,
                'paidEffective', s.paid_effective,
                'periodWorkingDays', s.period_days,
                'consideredWorkingDays', s.considered_days,
                'consideredDaysBasis', 'ELIGIBLE_LINK_DAYS',
                'absenceCoverage', 'NONE',
                'dailyProductivity', CASE
                    WHEN s.considered_days > 0
                    THEN s.paid_effective / s.considered_days
                    ELSE 0
                END,
                'ruleRevision', 1
            )
            ORDER BY s.semana_inicio, s.store, s.consultant_id
        )
        FROM semanal s
    ), '[]'::jsonb),
    'diagnostics', jsonb_build_object(
        'consideredDaysBasis', 'ELIGIBLE_LINK_DAYS',
        'absenceCoverage', 'NONE',
        'ruleRevision', 1,
        'monthlyRows', d.linhas_mensais,
        'weeklyRows', d.linhas_semanais,
        'monthlyPaidTotal', d.pago_mensal,
        'monthlyUnlinkedPaidRows', d.mensal_sem_vinculo,
        'weeklyUnlinkedPaidRows', d.semanal_sem_vinculo,
        'overlappingEligibleDays', d.vinculo_sobreposto
    )
)
FROM diagnostico d;
$fn$;


-- fn_supervisores_replace — vigente na 113; 1 troca(s)
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
            public.fn_normalizar_nome(btrim(j.nome))
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


-- fn_aplicar_mudanca_supervisor — vigente na 113; 2 troca(s)
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

    v_nome_norm := public.fn_normalizar_nome(btrim(coalesce(p_nome, '')));
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
         WHERE public.fn_normalizar_nome(btrim(s.nome))
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


-- fn_headcount_replace — vigente na 115; 4 troca(s)
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
    WHERE public.fn_normalizar_nome(btrim(r->>'nome')) IN (
        SELECT public.fn_normalizar_nome(btrim(r2->>'nome'))
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
            public.fn_normalizar_nome(btrim(r->>'nome'))          AS nn,
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
            public.fn_normalizar_nome(btrim(cs.nome)) AS nn,
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


-- fn_diag_vinculo_divergente — vigente na 116; 2 troca(s)
CREATE OR REPLACE FUNCTION public.fn_diag_vinculo_divergente()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $fn$
WITH
foto AS (
    -- Copia fiel de `consultores_mais_recentes` (092). Ver cabecalho.
    SELECT DISTINCT ON (n.nome_normalizado)
        c.id,
        c.nome,
        c.loja_id,
        c.status,
        c.updated_at,
        n.nome_normalizado AS nn
    FROM public.consultores c
    CROSS JOIN LATERAL (
        SELECT public.fn_normalizar_nome(btrim(coalesce(c.nome, ''))) AS nome_normalizado
    ) n
    WHERE n.nome_normalizado <> ''
    ORDER BY n.nome_normalizado, c.updated_at DESC NULLS LAST, c.id DESC
),
ativos AS (
    -- Mesmo predicado da 092: status vazio conta como ativo.
    SELECT * FROM foto
    WHERE btrim(coalesce(status, '')) = ''
       OR upper(btrim(status)) LIKE 'ATIVO%'
),
janelas AS (
    SELECT
        v.nome_normalizado AS nn,
        count(*)::integer  AS n_abertas,
        (array_agg(v.loja_id
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS loja_ledger,
        (array_agg(v.vigencia_inicio
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS desde,
        (array_agg(v.origem
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS origem
    FROM public.consultor_vigencia v
    WHERE v.vigencia_fim IS NULL
    GROUP BY 1
),
producao AS (
    -- Ultimo contrato da pessoa e a loja dele. E o unico fato objetivo
    -- disponivel para quem for julgar a divergencia: producao prova
    -- presenca. `data_cadastro`, nunca `data_status_pagamento` —
    -- pagamento arrasta depois da transferencia (105).
    SELECT DISTINCT ON (t.nn) t.nn, t.loja_id AS loja_ultimo, t.data_cadastro AS ultimo
    FROM (
        SELECT public.fn_normalizar_nome(btrim(cs.nome)) AS nn,
               ct.loja_id,
               ct.data_cadastro::date AS data_cadastro
        FROM public.contratos ct
        JOIN public.consultores cs ON cs.id = ct.consultor_id
        WHERE ct.data_cadastro IS NOT NULL
    ) t
    ORDER BY t.nn, t.data_cadastro DESC
),
supervisao AS (
    SELECT
        v.nome_normalizado AS nn,
        (array_agg(v.loja_id
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS loja_sup,
        (array_agg(v.vigencia_inicio
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS sup_desde
    FROM public.supervisor_vigencia v
    WHERE v.vigencia_fim IS NULL
    GROUP BY 1
)
SELECT jsonb_build_object(
    'gerado_em', now(),
    'ativos_avaliados', (SELECT count(*) FROM ativos),

    -- 1. Foto e ledger discordam da loja.
    'divergencias', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',            a.nome,
                   'loja_foto',       lf.nome,
                   'loja_ledger',     ll.nome,
                   'ledger_desde',    j.desde,
                   'ledger_origem',   j.origem,
                   'ultimo_contrato', p.ultimo,
                   'loja_ultimo_contrato', lu.nome,
                   'cadastro_atualizado_em', a.updated_at)
               ORDER BY a.nome), '[]'::jsonb)
        FROM ativos a
        JOIN janelas j        ON j.nn = a.nn AND j.n_abertas = 1
        LEFT JOIN producao p  ON p.nn = a.nn
        LEFT JOIN public.lojas lf ON lf.id = a.loja_id
        LEFT JOIN public.lojas ll ON ll.id = j.loja_ledger
        LEFT JOIN public.lojas lu ON lu.id = p.loja_ultimo
        WHERE a.loja_id IS DISTINCT FROM j.loja_ledger
    ),

    -- 2. Ativo na foto, invisivel para o denominador.
    'sem_janela_aberta', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',            a.nome,
                   'loja_foto',       lf.nome,
                   'status',          a.status,
                   'ultimo_contrato', p.ultimo)
               ORDER BY a.nome), '[]'::jsonb)
        FROM ativos a
        LEFT JOIN janelas j   ON j.nn = a.nn
        LEFT JOIN producao p  ON p.nn = a.nn
        LEFT JOIN public.lojas lf ON lf.id = a.loja_id
        WHERE j.nn IS NULL
    ),

    -- 3. Peso repartido entre lojas — legitimo, mas confira.
    'multiplas_janelas', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',     f.nome,
                   'abertas',  j.n_abertas,
                   'lojas',    (SELECT coalesce(jsonb_agg(l2.nome ORDER BY l2.nome),
                                                '[]'::jsonb)
                                FROM public.consultor_vigencia v2
                                LEFT JOIN public.lojas l2 ON l2.id = v2.loja_id
                                WHERE v2.nome_normalizado = j.nn
                                  AND v2.vigencia_fim IS NULL))
               ORDER BY f.nome), '[]'::jsonb)
        FROM janelas j
        JOIN foto f ON f.nn = j.nn
        WHERE j.n_abertas > 1
    ),

    -- 4. Residuo de cadastro pronto para receber producao fantasma.
    --    `tem_escopo_usuario` importa: usuario_escopos.consultor_id e
    --    ON DELETE CASCADE, entao remover a linha levaria o escopo junto
    --    (foi a guarda que a 109 precisou ter na etapa 6).
    'cadastros_orfaos', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',       c.nome,
                   'loja',       l.nome,
                   'status',     c.status,
                   'criado_em',  c.created_at,
                   'tem_escopo_usuario', EXISTS (
                       SELECT 1 FROM public.usuario_escopos ue
                       WHERE ue.consultor_id = c.id))
               ORDER BY c.nome), '[]'::jsonb)
        FROM public.consultores c
        LEFT JOIN public.lojas l ON l.id = c.loja_id
        WHERE NOT EXISTS (SELECT 1 FROM foto f WHERE f.id = c.id)
          AND NOT EXISTS (SELECT 1 FROM public.contratos ct
                          WHERE ct.consultor_id = c.id)
    ),

    -- 5. Supervisiona uma loja, tem vinculo de consultor em outra.
    'papel_sem_vinculo', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',            f.nome,
                   'loja_supervisao', ls.nome,
                   'supervisao_desde', s.sup_desde,
                   'loja_consultor',  lc.nome,
                   'consultor_desde', j.desde)
               ORDER BY f.nome), '[]'::jsonb)
        FROM supervisao s
        JOIN janelas j ON j.nn = s.nn AND j.n_abertas = 1
        JOIN foto f    ON f.nn = s.nn
        LEFT JOIN public.lojas ls ON ls.id = s.loja_sup
        LEFT JOIN public.lojas lc ON lc.id = j.loja_ledger
        WHERE s.loja_sup IS DISTINCT FROM j.loja_ledger
    )
);
$fn$;


-- fn_movimentacoes_replace — vigente na 120; 7 troca(s)
CREATE OR REPLACE FUNCTION public.fn_movimentacoes_replace(
    p_movimentos     jsonb,
    p_validar_apenas boolean DEFAULT true
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '120s'
AS $fn$
DECLARE
    v_len            integer;
    v_pendencias     jsonb;
    v_divergencias   jsonb;
    v_cv_fechadas    integer := 0;
    v_cv_abertas     integer := 0;
    v_sv_fechadas    integer := 0;
    v_sv_abertas     integer := 0;
    v_sv_sucessao    integer := 0;
    v_foto_ins       integer := 0;
    v_foto_del       integer := 0;
    v_row            record;
    v_loja_atual     uuid;
    v_n              integer;
BEGIN
    IF p_movimentos IS NULL OR jsonb_typeof(p_movimentos) <> 'array' THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'O payload deve ser um array JSON.',
            'pendencias', jsonb_build_array(jsonb_build_object(
                'linha', 0, 'codigo', 'PAYLOAD_INVALIDO')));
    END IF;

    v_len := jsonb_array_length(p_movimentos);

    IF v_len = 0 THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Nenhuma movimentacao recebida.',
            'pendencias', '[]'::jsonb);
    END IF;

    -- Serializa contra outra carga de movimentacao. Chave diferente da
    -- 097 (20260831) de proposito: as duas funcoes tocam os mesmos
    -- ledgers e nao podem correr juntas.
    PERFORM pg_catalog.pg_advisory_xact_lock(20260909);

    -- `ON COMMIT DROP` so libera o nome no COMMIT: duas chamadas na MESMA
    -- transacao (dry-run e aplicacao juntos, por exemplo) falhariam com
    -- "relation already exists" antes de validar nada. Guarda igual a da
    -- 095 para `hc_plan`.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relname = 'mv_pendencias'
          AND c.relnamespace = pg_catalog.pg_my_temp_schema()
    ) THEN
        DROP TABLE pg_temp.mv_pendencias;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relname = 'mv_raw'
          AND c.relnamespace = pg_catalog.pg_my_temp_schema()
    ) THEN
        DROP TABLE pg_temp.mv_raw;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relname = 'mv'
          AND c.relnamespace = pg_catalog.pg_my_temp_schema()
    ) THEN
        DROP TABLE pg_temp.mv;
    END IF;

    CREATE TEMP TABLE mv_pendencias (
        linha  integer NOT NULL,
        codigo text    NOT NULL
    ) ON COMMIT DROP;

    CREATE TEMP TABLE mv_raw ON COMMIT DROP AS
    SELECT
        CASE WHEN coalesce(e.value->>'linha', '') ~ '^[0-9]+$'
             THEN (e.value->>'linha')::integer
             ELSE e.ordinality::integer + 1 END           AS linha,
        btrim(coalesce(e.value->>'nome', ''))             AS nome,
        public.fn_normalizar_nome(btrim(coalesce(e.value->>'nome', '')))   AS nn,
        upper(btrim(coalesce(e.value->>'tipo', '')))      AS tipo,
        btrim(coalesce(e.value->>'loja_destino', ''))     AS destino_txt,
        btrim(coalesce(e.value->>'data_efetiva', ''))     AS data_txt
    FROM jsonb_array_elements(p_movimentos)
         WITH ORDINALITY AS e(value, ordinality);

    -- ---- Fase 1: sintaxe ----
    -- Separada das demais para que NENHUMA expressao tente converter
    -- texto malformado, mesmo se o otimizador reordenar predicados.
    -- Mesmo cuidado (e mesmo motivo) da 097.
    INSERT INTO mv_pendencias
    SELECT linha,
           CASE
             WHEN nome = '' THEN 'NOME_AUSENTE'
             WHEN tipo NOT IN ('TRANSFERENCIA', 'PROMOCAO', 'REBAIXAMENTO')
               THEN 'TIPO_INVALIDO'
             WHEN data_txt !~ '^\d{4}-\d{2}-\d{2}$' THEN 'DATA_INVALIDA'
             ELSE 'LOJA_INVALIDA'
           END
    FROM mv_raw
    WHERE nome = ''
       OR tipo NOT IN ('TRANSFERENCIA', 'PROMOCAO', 'REBAIXAMENTO')
       OR data_txt !~ '^\d{4}-\d{2}-\d{2}$'
       -- destino e obrigatorio em TRANSFERENCIA e PROMOCAO; opcional em
       -- REBAIXAMENTO (vazio = mantem a loja de consultor onde esta).
       OR (tipo IN ('TRANSFERENCIA', 'PROMOCAO') AND destino_txt = '')
       OR (destino_txt <> '' AND destino_txt !~
           '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$');

    IF EXISTS (SELECT 1 FROM mv_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object('linha', linha, 'codigo', codigo)
                         ORDER BY linha)
          INTO v_pendencias FROM mv_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias, 'recebidas', v_len);
    END IF;

    -- Componentes fora de faixa, ainda sem chamar to_date.
    INSERT INTO mv_pendencias
    SELECT linha, 'DATA_INVALIDA' FROM mv_raw
    WHERE substring(data_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
       OR substring(data_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
       OR substring(data_txt, 9, 2)::integer NOT BETWEEN 1 AND 31;

    IF EXISTS (SELECT 1 FROM mv_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object('linha', linha, 'codigo', codigo)
                         ORDER BY linha)
          INTO v_pendencias FROM mv_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias, 'recebidas', v_len);
    END IF;

    -- MUDANCA 120 — o dia contra o ULTIMO DIA DO MES, sem to_date.
    -- Mesmo defeito e mesma correcao de fn_movimentacoes_rh_import: o
    -- round-trip que estava aqui herdou o desenho da 097 e herdou junto
    -- o furo. Nesta versao do PostgreSQL `to_date` LANCA em vez de
    -- normalizar, entao 2026-02-31 escapava como excecao 22008 em vez de
    -- virar pendencia DATA_INVALIDA. Medido em 2026-09-09.
    --
    -- `make_date(y, m, 1)` e seguro: ano e mes ja passaram pela faixa no
    -- bloco anterior, e o dia 1 existe em todo mes.
    INSERT INTO mv_pendencias
    SELECT linha, 'DATA_INVALIDA' FROM mv_raw
    WHERE substring(data_txt, 9, 2)::integer > pg_catalog.date_part('day',
              pg_catalog.make_date(
                  substring(data_txt, 1, 4)::integer,
                  substring(data_txt, 6, 2)::integer, 1)
                  + interval '1 month' - interval '1 day');

    IF EXISTS (SELECT 1 FROM mv_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object('linha', linha, 'codigo', codigo)
                         ORDER BY linha)
          INTO v_pendencias FROM mv_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias, 'recebidas', v_len);
    END IF;

    -- ---- Fase 2: semantica ----
    -- `mv` ja tem os tipos convertidos e a loja atual de cada pessoa
    -- resolvida uma vez so, para as validacoes e a aplicacao usarem a
    -- MESMA leitura. Reconsultar na aplicacao abriria janela para o
    -- estado mudar entre validar e escrever.
    CREATE TEMP TABLE mv ON COMMIT DROP AS
    SELECT
        r.linha, r.nome, r.nn, r.tipo,
        nullif(r.destino_txt, '')::uuid AS loja_destino,
        r.data_txt::date                AS data_efetiva,
        cv.id       AS cv_id,
        cv.loja_id  AS cv_loja,
        cv.vigencia_inicio AS cv_inicio,
        cv.origem   AS cv_origem,
        cv.n_abertas,
        sv.id       AS sv_id,
        sv.loja_id  AS sv_loja,
        sv.vigencia_inicio AS sv_inicio,
        sv.origem   AS sv_origem
    FROM mv_raw r
    LEFT JOIN LATERAL (
        -- A janela de consultor aberta mais recente. `n_abertas` conta
        -- todas: mais de uma e cobertura temporaria (103/111) e a funcao
        -- nao adivinha qual fechar.
        SELECT v.id, v.loja_id, v.vigencia_inicio, v.origem,
               count(*) OVER ()::integer AS n_abertas
        FROM public.consultor_vigencia v
        WHERE v.nome_normalizado = r.nn AND v.vigencia_fim IS NULL
        ORDER BY v.vigencia_inicio DESC, v.id DESC
        LIMIT 1
    ) cv ON true
    LEFT JOIN LATERAL (
        SELECT v.id, v.loja_id, v.vigencia_inicio, v.origem
        FROM public.supervisor_vigencia v
        WHERE v.nome_normalizado = r.nn AND v.vigencia_fim IS NULL
        ORDER BY v.vigencia_inicio DESC, v.id DESC
        LIMIT 1
    ) sv ON true;

    -- A mesma pessoa duas vezes na mesma carga: a segunda linha leria um
    -- estado que a primeira ja mudou, e `mv` foi resolvida ANTES de
    -- qualquer escrita. Duas movimentacoes da mesma pessoa exigem duas
    -- cargas, em ordem.
    INSERT INTO mv_pendencias
    SELECT min(linha), 'PESSOA_DUPLICADA'
    FROM mv GROUP BY nn HAVING count(*) > 1;

    INSERT INTO mv_pendencias
    SELECT m.linha, 'PESSOA_NAO_ENCONTRADA'
    FROM mv m
    WHERE NOT EXISTS (SELECT 1 FROM public.consultores c
                      WHERE public.fn_normalizar_nome(btrim(c.nome)) = m.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisores s
                      WHERE public.fn_normalizar_nome(btrim(s.nome)) = m.nn)
      AND NOT EXISTS (SELECT 1 FROM public.consultor_vigencia v
                      WHERE v.nome_normalizado = m.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisor_vigencia v
                      WHERE v.nome_normalizado = m.nn);

    INSERT INTO mv_pendencias
    SELECT m.linha, 'LOJA_NAO_ENCONTRADA'
    FROM mv m
    WHERE m.loja_destino IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM public.lojas l WHERE l.id = m.loja_destino);

    -- TRANSFERENCIA e PROMOCAO precisam de janela de consultor para
    -- fechar. Sem ela nao ha de onde transferir, e ABRIR sozinho
    -- inventaria um vinculo cuja data de inicio ninguem declarou.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'SEM_JANELA_ABERTA'
    FROM mv m
    WHERE m.tipo IN ('TRANSFERENCIA', 'PROMOCAO') AND m.cv_id IS NULL;

    INSERT INTO mv_pendencias
    SELECT m.linha, 'SEM_SUPERVISAO_ABERTA'
    FROM mv m
    WHERE m.tipo = 'REBAIXAMENTO' AND m.sv_id IS NULL;

    -- Mais de uma janela aberta e cobertura temporaria. Qual fechar nao
    -- se deduz: para e pede decisao humana.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'MULTIPLAS_JANELAS_ABERTAS'
    FROM mv m
    WHERE m.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
      AND coalesce(m.n_abertas, 0) > 1;

    -- Transferir para a loja onde a pessoa ja esta e no-op disfarcado:
    -- fecharia e reabriria a mesma janela, quebrando o historico em duas
    -- sem que nada tenha mudado.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'DESTINO_IGUAL_ORIGEM'
    FROM mv m
    WHERE m.tipo = 'TRANSFERENCIA' AND m.loja_destino = m.cv_loja;

    INSERT INTO mv_pendencias
    SELECT m.linha, 'JA_SUPERVISIONA_DESTINO'
    FROM mv m
    WHERE m.tipo = 'PROMOCAO' AND m.sv_id IS NOT NULL
      AND m.sv_loja = m.loja_destino;

    -- Fechar em data <= inicio violaria chk_cv_vigencia_ordem /
    -- chk_sv_vigencia_ordem. Recusa antes de tentar.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'JANELA_INCOMPATIVEL'
    FROM mv m
    WHERE (m.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
           AND m.cv_inicio IS NOT NULL AND m.data_efetiva <= m.cv_inicio)
       OR (m.tipo IN ('PROMOCAO', 'REBAIXAMENTO')
           AND m.sv_inicio IS NOT NULL AND m.data_efetiva <= m.sv_inicio);

    -- Correcao humana anterior nao se desfaz por carga. Vale tambem aqui:
    -- esta funcao escreve MANUAL, mas uma linha errada dela nao pode
    -- passar por cima de outra correcao MANUAL sem que alguem veja.
    -- Reaplicar de proposito exige corrigir a janela antes.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'CORRECAO_MANUAL_EXISTENTE'
    FROM mv m
    WHERE (m.tipo IN ('TRANSFERENCIA', 'PROMOCAO') AND m.cv_origem = 'MANUAL'
           AND m.cv_inicio = m.data_efetiva)
       OR (m.tipo IN ('PROMOCAO', 'REBAIXAMENTO') AND m.sv_origem = 'MANUAL'
           AND m.sv_inicio = m.data_efetiva);

    IF EXISTS (SELECT 1 FROM mv_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object('linha', linha, 'codigo', codigo)
                         ORDER BY linha)
          INTO v_pendencias
        FROM (SELECT DISTINCT linha, codigo FROM mv_pendencias) p;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias, 'recebidas', v_len);
    END IF;

    -- ---- Divergencias: producao do lado errado da fronteira ----
    -- REPORTA, nao bloqueia. Ver cabecalho: uma guarda estrita teria
    -- recusado a transferencia da CAROLINA por 1 contrato avulso.
    SELECT jsonb_agg(d ORDER BY linha, d->>'codigo') INTO v_divergencias
    FROM (
        SELECT m.linha,
               jsonb_build_object(
                   'linha', m.linha,
                   'codigo', 'PRODUCAO_NA_ORIGEM_APOS_CORTE',
                   'contratos', count(*)::integer,
                   'ultimo', max(ct.data_cadastro::date)) AS d
        FROM mv m
        JOIN public.consultores cs
          ON public.fn_normalizar_nome(btrim(cs.nome)) = m.nn
        JOIN public.contratos ct ON ct.consultor_id = cs.id
        WHERE m.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
          AND ct.loja_id = m.cv_loja
          AND ct.data_cadastro >= m.data_efetiva
        GROUP BY m.linha

        UNION ALL

        SELECT m.linha,
               jsonb_build_object(
                   'linha', m.linha,
                   'codigo', 'PRODUCAO_NO_DESTINO_ANTES_DO_CORTE',
                   'contratos', count(*)::integer,
                   'primeiro', min(ct.data_cadastro::date)) AS d
        FROM mv m
        JOIN public.consultores cs
          ON public.fn_normalizar_nome(btrim(cs.nome)) = m.nn
        JOIN public.contratos ct ON ct.consultor_id = cs.id
        WHERE m.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
          AND ct.loja_id = m.loja_destino
          AND ct.data_cadastro < m.data_efetiva
        GROUP BY m.linha
    ) t;

    IF p_validar_apenas THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', true, 'error', NULL,
            'pendencias', '[]'::jsonb,
            'divergencias', coalesce(v_divergencias, '[]'::jsonb),
            'recebidas', v_len);
    END IF;

    -- ---- Fase 3: aplicacao ----
    -- Linha a linha e em ordem, porque PROMOCAO faz quatro escritas
    -- interdependentes e a sucessao do antecessor depende da data desta
    -- pessoa. Volume esperado: unidades por carga.
    FOR v_row IN SELECT * FROM mv ORDER BY linha LOOP

        -- (1) Consultor: fecha a janela atual e abre na loja nova.
        --     REBAIXAMENTO so entra aqui se `loja_destino` vier e for
        --     diferente da atual — rebaixar nao move de loja por si.
        v_loja_atual := v_row.cv_loja;

        IF v_row.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
           OR (v_row.tipo = 'REBAIXAMENTO'
               AND v_row.loja_destino IS NOT NULL
               AND v_row.loja_destino IS DISTINCT FROM v_loja_atual
               AND v_row.cv_id IS NOT NULL) THEN

            -- PROMOCAO para a loja onde a pessoa JA e consultora nao
            -- mexe no vinculo: so o papel muda.
            IF v_row.loja_destino IS DISTINCT FROM v_loja_atual THEN
                UPDATE public.consultor_vigencia
                   SET vigencia_fim = v_row.data_efetiva,
                       origem       = 'MANUAL'
                 WHERE id = v_row.cv_id;
                v_cv_fechadas := v_cv_fechadas + 1;

                -- `uq_cv_consultor_loja_aberta` impede duas abertas para
                -- a mesma (pessoa, loja). Se ja houver uma na loja de
                -- destino — retorno a uma loja anterior sem ter fechado
                -- la — o INSERT violaria o indice; o NOT EXISTS torna o
                -- caso um no-op em vez de abortar a carga inteira.
                INSERT INTO public.consultor_vigencia
                    (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
                SELECT v_row.nome, v_row.loja_destino, v_row.data_efetiva,
                       NULL, 'MANUAL'
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.consultor_vigencia w
                    WHERE w.nome_normalizado = v_row.nn
                      AND w.loja_id = v_row.loja_destino
                      AND w.vigencia_fim IS NULL);
                -- ROW_COUNT, nao `+ 1`: o NOT EXISTS acima pode nao ter
                -- inserido nada, e o envelope tem de dizer o que
                -- aconteceu, nao o que se pretendia.
                GET DIAGNOSTICS v_n = ROW_COUNT;
                v_cv_abertas := v_cv_abertas + v_n;
            END IF;
        END IF;

        -- (2) Supervisao.
        IF v_row.tipo = 'PROMOCAO' THEN
            -- Fecha a supervisao anterior DA PESSOA, se houver (mudanca
            -- de loja supervisionada).
            IF v_row.sv_id IS NOT NULL THEN
                UPDATE public.supervisor_vigencia
                   SET vigencia_fim = v_row.data_efetiva,
                       origem       = 'MANUAL'
                 WHERE id = v_row.sv_id;
                v_sv_fechadas := v_sv_fechadas + 1;
            END IF;

            -- Sucessao: o antecessor da loja de destino fecha na data do
            -- sucessor. A cadeira nao fica vaga nem com dois ocupantes —
            -- mesma regra da 082, e o que a 110 fez a mao para BARBARA.
            -- `vigencia_inicio < data` evita violar chk_sv_vigencia_ordem
            -- quando o antecessor comecou no mesmo dia ou depois.
            UPDATE public.supervisor_vigencia v
               SET vigencia_fim = v_row.data_efetiva,
                   origem       = 'MANUAL'
             WHERE v.loja_id = v_row.loja_destino
               AND v.vigencia_fim IS NULL
               AND v.nome_normalizado <> v_row.nn
               AND v.vigencia_inicio < v_row.data_efetiva;
            GET DIAGNOSTICS v_sv_sucessao = ROW_COUNT;
            v_sv_fechadas := v_sv_fechadas + v_sv_sucessao;

            DELETE FROM public.supervisores s
             WHERE s.loja_id = v_row.loja_destino
               AND public.fn_normalizar_nome(btrim(s.nome)) <> v_row.nn;
            -- Acumula: `GET DIAGNOSTICS` sobrescreve, e o loop passa por
            -- varias linhas. Somar e o que faz o envelope descrever a
            -- carga inteira em vez da ultima iteracao.
            GET DIAGNOSTICS v_n = ROW_COUNT;
            v_foto_del := v_foto_del + v_n;

            INSERT INTO public.supervisor_vigencia
                (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
            SELECT v_row.nome, v_row.loja_destino, v_row.data_efetiva,
                   NULL, 'MANUAL'
            WHERE NOT EXISTS (
                SELECT 1 FROM public.supervisor_vigencia w
                WHERE w.nome_normalizado = v_row.nn
                  AND w.loja_id = v_row.loja_destino
                  AND w.vigencia_fim IS NULL);
            GET DIAGNOSTICS v_n = ROW_COUNT;
            v_sv_abertas := v_sv_abertas + v_n;

            INSERT INTO public.supervisores (nome, loja_id, regiao_id)
            SELECT v_row.nome, v_row.loja_destino, l.regiao_id
            FROM public.lojas l WHERE l.id = v_row.loja_destino
            ON CONFLICT (nome, loja_id) DO NOTHING;
            GET DIAGNOSTICS v_n = ROW_COUNT;
            v_foto_ins := v_foto_ins + v_n;

        ELSIF v_row.tipo = 'REBAIXAMENTO' THEN
            UPDATE public.supervisor_vigencia
               SET vigencia_fim = v_row.data_efetiva,
                   origem       = 'MANUAL'
             WHERE id = v_row.sv_id;
            v_sv_fechadas := v_sv_fechadas + 1;

            -- Sai da foto de supervisores. A janela de consultor
            -- permanece: a pessoa volta a ser contada no denominador da
            -- loja, que e justamente o efeito do rebaixamento.
            DELETE FROM public.supervisores s
             WHERE public.fn_normalizar_nome(btrim(s.nome)) = v_row.nn
               AND s.loja_id IS NOT DISTINCT FROM v_row.sv_loja;
            GET DIAGNOSTICS v_n = ROW_COUNT;
            v_foto_del := v_foto_del + v_n;
        END IF;
    END LOOP;

    RETURN jsonb_build_object(
        'aplicado', true, 'validar_apenas', false, 'error', NULL,
        'pendencias', '[]'::jsonb,
        'divergencias', coalesce(v_divergencias, '[]'::jsonb),
        'recebidas', v_len,
        'consultor_vigencia', jsonb_build_object(
            'fechadas', v_cv_fechadas, 'abertas', v_cv_abertas),
        'supervisor_vigencia', jsonb_build_object(
            'fechadas', v_sv_fechadas, 'abertas', v_sv_abertas),
        'foto_supervisores', jsonb_build_object(
            'inseridos', v_foto_ins, 'removidos', v_foto_del));
END;
$fn$;


-- fn_movimentacoes_rh_import — vigente na 120; 9 troca(s)
CREATE OR REPLACE FUNCTION public.fn_movimentacoes_rh_import(
    p_afastamentos  jsonb,
    p_desligamentos jsonb,
    p_validar_apenas boolean DEFAULT true
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '120s'
AS $fn$
DECLARE
    v_pendencias       jsonb;
    v_afast_len        integer;
    v_desl_len         integer;
    v_afast_inseridos  integer := 0;
    v_afast_atualizados integer := 0;
    v_afast_inalterados integer := 0;
    v_afast_prod       integer := 0;
    v_desl_consultores integer := 0;
    v_desl_supervisores integer := 0;
    v_desl_cadastros   integer := 0;
    v_desl_afast       integer := 0;
    v_desl_producao    integer := 0;
    v_divergencias     jsonb;
    v_row              record;
    v_id               uuid;
    v_tipo_atual       text;
    v_inicio_atual     date;
    v_fim_atual        date;
BEGIN
    IF p_afastamentos IS NULL OR jsonb_typeof(p_afastamentos) <> 'array'
       OR p_desligamentos IS NULL OR jsonb_typeof(p_desligamentos) <> 'array' THEN
        RETURN jsonb_build_object(
            'aplicado', false,
            'validar_apenas', p_validar_apenas,
            'error', 'Os dois payloads devem ser arrays JSON.',
            'pendencias', jsonb_build_array(jsonb_build_object(
                'linha', 0, 'origem', 'ARQUIVO', 'codigo', 'PAYLOAD_INVALIDO')));
    END IF;

    v_afast_len := jsonb_array_length(p_afastamentos);
    v_desl_len := jsonb_array_length(p_desligamentos);

    IF v_afast_len + v_desl_len = 0 THEN
        RETURN jsonb_build_object(
            'aplicado', false,
            'validar_apenas', p_validar_apenas,
            'error', 'Nenhuma movimentacao valida recebida.',
            'pendencias', '[]'::jsonb);
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(20260831);

    CREATE TEMP TABLE mrh_pendencias (
        linha integer NOT NULL,
        origem text NOT NULL,
        codigo text NOT NULL
    ) ON COMMIT DROP;

    CREATE TEMP TABLE mrh_afast_raw ON COMMIT DROP AS
    SELECT
        CASE WHEN coalesce(e.value->>'linha', '') ~ '^[0-9]+$'
             THEN (e.value->>'linha')::integer
             ELSE e.ordinality::integer + 4 END AS linha,
        btrim(coalesce(e.value->>'nome', '')) AS nome,
        public.fn_normalizar_nome(btrim(coalesce(e.value->>'nome', ''))) AS nn,
        upper(btrim(coalesce(e.value->>'tipo', ''))) AS tipo,
        btrim(coalesce(e.value->>'data_inicio', '')) AS inicio_txt,
        btrim(coalesce(e.value->>'data_fim', '')) AS fim_txt
    FROM jsonb_array_elements(p_afastamentos) WITH ORDINALITY AS e(value, ordinality);

    CREATE TEMP TABLE mrh_desl_raw ON COMMIT DROP AS
    SELECT
        CASE WHEN coalesce(e.value->>'linha', '') ~ '^[0-9]+$'
             THEN (e.value->>'linha')::integer
             ELSE e.ordinality::integer + 4 END AS linha,
        btrim(coalesce(e.value->>'nome', '')) AS nome,
        public.fn_normalizar_nome(btrim(coalesce(e.value->>'nome', ''))) AS nn,
        btrim(coalesce(e.value->>'loja_id', '')) AS loja_txt,
        btrim(coalesce(e.value->>'data_desligamento', '')) AS desl_txt
    FROM jsonb_array_elements(p_desligamentos) WITH ORDINALITY AS e(value, ordinality);

    -- Validacao sintatica primeiro. As fases sao separadas para nenhuma
    -- expressao tentar converter texto malformado, mesmo se o otimizador
    -- reordenar predicados do WHERE.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO',
           CASE
             WHEN nome = '' THEN 'NOME_AUSENTE'
             WHEN tipo NOT IN ('AFASTAMENTO_MEDICO', 'LICENCA_MATERNIDADE',
                               'LICENCA_NAO_REMUNERADA', 'FERIAS') THEN 'TIPO_INVALIDO'
             WHEN inicio_txt !~ '^\d{4}-\d{2}-\d{2}$' THEN 'DATA_INICIO_INVALIDA'
             ELSE 'DATA_FIM_INVALIDA'
           END
    FROM mrh_afast_raw
    WHERE nome = ''
       OR tipo NOT IN ('AFASTAMENTO_MEDICO', 'LICENCA_MATERNIDADE',
                       'LICENCA_NAO_REMUNERADA', 'FERIAS')
       OR inicio_txt !~ '^\d{4}-\d{2}-\d{2}$'
       OR (fim_txt <> '' AND fim_txt !~ '^\d{4}-\d{2}-\d{2}$');

    INSERT INTO mrh_pendencias
    SELECT linha, 'DESLIGAMENTO',
           CASE
             WHEN nome = '' THEN 'NOME_AUSENTE'
             WHEN loja_txt <> '' AND loja_txt !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
               THEN 'LOJA_INVALIDA'
             ELSE 'DATA_DESLIGAMENTO_INVALIDA'
           END
    FROM mrh_desl_raw
    WHERE nome = ''
       OR (loja_txt <> '' AND loja_txt !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
       OR desl_txt !~ '^\d{4}-\d{2}-\d{2}$';

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM mrh_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias);
    END IF;

    -- Componentes fora de faixa, ainda sem chamar to_date.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO',
           CASE WHEN substring(inicio_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
                  OR substring(inicio_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
                  OR substring(inicio_txt, 9, 2)::integer NOT BETWEEN 1 AND 31
                THEN 'DATA_INICIO_INVALIDA' ELSE 'DATA_FIM_INVALIDA' END
    FROM mrh_afast_raw
    WHERE substring(inicio_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
       OR substring(inicio_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
       OR substring(inicio_txt, 9, 2)::integer NOT BETWEEN 1 AND 31
       OR (fim_txt <> '' AND (
           substring(fim_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
        OR substring(fim_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
        OR substring(fim_txt, 9, 2)::integer NOT BETWEEN 1 AND 31));

    INSERT INTO mrh_pendencias
    SELECT linha, 'DESLIGAMENTO', 'DATA_DESLIGAMENTO_INVALIDA'
    FROM mrh_desl_raw
    WHERE substring(desl_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
       OR substring(desl_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
       OR substring(desl_txt, 9, 2)::integer NOT BETWEEN 1 AND 31;

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM mrh_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias);
    END IF;

    -- MUDANCA 120 — o dia contra o ULTIMO DIA DO MES, sem to_date.
    --
    -- Aqui ficava um round-trip `to_char(to_date(t)) <> t`, escrito para
    -- pegar 31/02. Ele NAO pega: nesta versao do PostgreSQL `to_date`
    -- LANCA em vez de normalizar, entao a comparacao nunca acontece e a
    -- excecao escapa da funcao. Medido em 2026-09-09 contra o banco:
    -- 31/02, 31/04 e 29/02 de ano nao bissexto devolviam
    -- `22008 date/time field value out of range` em vez de pendencia.
    --
    -- O efeito pratico e ruim justamente onde este arquivo vive: o RH e
    -- digitado a mao a partir de e-mails, onde 31/04 acontece, e quem
    -- importa via um erro opaco de banco em vez de "linha 12: data
    -- invalida".
    --
    -- A checagem nova nao chama to_date nenhuma vez. `make_date(y, m, 1)`
    -- e seguro porque ano e mes JA passaram pela faixa no bloco anterior,
    -- e o dia 1 existe em todo mes. Somar um mes e voltar um dia da o
    -- ultimo dia real — 28 ou 29 em fevereiro, conforme o ano.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO',
           CASE WHEN substring(inicio_txt, 9, 2)::integer > pg_catalog.date_part('day',
                         pg_catalog.make_date(
                             substring(inicio_txt, 1, 4)::integer,
                             substring(inicio_txt, 6, 2)::integer, 1)
                             + interval '1 month' - interval '1 day')
                THEN 'DATA_INICIO_INVALIDA'
                ELSE 'DATA_FIM_INVALIDA' END
    FROM mrh_afast_raw
    WHERE substring(inicio_txt, 9, 2)::integer > pg_catalog.date_part('day',
              pg_catalog.make_date(
                  substring(inicio_txt, 1, 4)::integer,
                  substring(inicio_txt, 6, 2)::integer, 1)
                  + interval '1 month' - interval '1 day')
       OR (fim_txt <> '' AND substring(fim_txt, 9, 2)::integer > pg_catalog.date_part('day',
              pg_catalog.make_date(
                  substring(fim_txt, 1, 4)::integer,
                  substring(fim_txt, 6, 2)::integer, 1)
                  + interval '1 month' - interval '1 day'));

    INSERT INTO mrh_pendencias
    SELECT linha, 'DESLIGAMENTO', 'DATA_DESLIGAMENTO_INVALIDA'
    FROM mrh_desl_raw
    WHERE substring(desl_txt, 9, 2)::integer > pg_catalog.date_part('day',
              pg_catalog.make_date(
                  substring(desl_txt, 1, 4)::integer,
                  substring(desl_txt, 6, 2)::integer, 1)
                  + interval '1 month' - interval '1 day');

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM mrh_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias);
    END IF;

    -- Ordem das datas. Separada da validade e DEPOIS do portao acima:
    -- so agora o cast `::date` e seguro para as duas pontas. Antes da
    -- 120 esta comparacao dividia o mesmo INSERT com o round-trip, e era
    -- por isso que uma data impossivel a alcancava.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO', 'ORDEM_DATAS_INVALIDA'
    FROM mrh_afast_raw
    WHERE fim_txt <> '' AND fim_txt::date <= inicio_txt::date;

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM mrh_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias);
    END IF;

    CREATE TEMP TABLE mrh_afast ON COMMIT DROP AS
    SELECT linha, nome, nn, tipo,
           inicio_txt::date AS data_inicio,
           nullif(fim_txt, '')::date AS data_fim
    FROM mrh_afast_raw;

    -- `data_efetiva` e a data que vai para os ledgers. Ela so diverge da
    -- data do arquivo quando ha producao em ou depois dela: nesse caso o
    -- corte e o dia SEGUINTE ao ultimo contrato, porque vigencia_fim e
    -- exclusivo e o dia do ultimo contrato foi trabalhado.
    CREATE TEMP TABLE mrh_desl ON COMMIT DROP AS
    SELECT r.linha, r.nome, r.nn, nullif(r.loja_txt, '')::uuid AS loja_id,
           r.desl_txt::date AS data_desligamento,
           p.ultima_producao,
           CASE WHEN p.ultima_producao IS NULL THEN r.desl_txt::date
                ELSE greatest(r.desl_txt::date, p.ultima_producao + 1)
           END AS data_efetiva,
           CASE WHEN p.ultima_producao IS NULL THEN 0
                ELSE (p.ultima_producao - r.desl_txt::date)
           END AS dias_apos
    FROM mrh_desl_raw r
    LEFT JOIN LATERAL (
        -- Filtro de data obrigatorio em `contratos`; a propria condicao
        -- da regra ja o fornece.
        SELECT max(ct.data_cadastro::date) AS ultima_producao
        FROM public.consultores c
        JOIN public.contratos ct ON ct.consultor_id = c.id
        WHERE public.fn_normalizar_nome(btrim(c.nome)) = r.nn
          AND ct.data_cadastro::date >= r.desl_txt::date
    ) p ON true;

    INSERT INTO mrh_pendencias
    SELECT min(linha), 'AFASTAMENTO', 'PESSOA_DUPLICADA'
    FROM mrh_afast GROUP BY nn HAVING count(*) > 1;

    INSERT INTO mrh_pendencias
    SELECT min(linha), 'DESLIGAMENTO', 'PESSOA_DUPLICADA'
    FROM mrh_desl GROUP BY nn HAVING count(*) > 1;

    INSERT INTO mrh_pendencias
    SELECT a.linha, 'AFASTAMENTO', 'PESSOA_NAO_ENCONTRADA'
    FROM mrh_afast a
    WHERE NOT EXISTS (SELECT 1 FROM public.consultores c
                      WHERE public.fn_normalizar_nome(btrim(c.nome)) = a.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisores s
                      WHERE public.fn_normalizar_nome(btrim(s.nome)) = a.nn)
      AND NOT EXISTS (SELECT 1 FROM public.consultor_vigencia v WHERE v.nome_normalizado = a.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisor_vigencia v WHERE v.nome_normalizado = a.nn);

    INSERT INTO mrh_pendencias
    SELECT d.linha, 'DESLIGAMENTO', 'PESSOA_NAO_ENCONTRADA'
    FROM mrh_desl d
    WHERE NOT EXISTS (SELECT 1 FROM public.consultores c
                      WHERE public.fn_normalizar_nome(btrim(c.nome)) = d.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisores s
                      WHERE public.fn_normalizar_nome(btrim(s.nome)) = d.nn)
      AND NOT EXISTS (SELECT 1 FROM public.consultor_vigencia v WHERE v.nome_normalizado = d.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisor_vigencia v WHERE v.nome_normalizado = d.nn);

    INSERT INTO mrh_pendencias
    SELECT d.linha, 'DESLIGAMENTO', 'LOJA_NAO_ENCONTRADA'
    FROM mrh_desl d
    WHERE d.loja_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM public.lojas l WHERE l.id = d.loja_id);

    -- Correcao humana e fato posterior de producao vencem o arquivo.
    INSERT INTO mrh_pendencias
    SELECT DISTINCT a.linha, 'AFASTAMENTO', 'CORRECAO_MANUAL_EXISTENTE'
    FROM mrh_afast a JOIN public.consultor_afastamento ca
      ON ca.nome_normalizado = a.nn
     AND (ca.data_fim IS NULL OR ca.data_inicio = a.data_inicio)
    WHERE ca.origem = 'MANUAL';

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'CORRECAO_MANUAL_EXISTENTE'
    FROM mrh_desl d
    WHERE EXISTS (SELECT 1 FROM public.consultor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.origem = 'MANUAL')
       OR EXISTS (SELECT 1 FROM public.consultor_afastamento a
                  WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL
                    AND a.origem = 'MANUAL')
       -- MUDANCA 114: o terceiro ledger entra na guarda. Ate aqui a
       -- funcao consultava dois ledgers e ESCREVIA em tres — o UPDATE
       -- de supervisor_vigencia, mais abaixo, nao tinha condicao
       -- nenhuma. Uma promocao registrada a mao (110) era desfeita por
       -- um desligamento vindo do arquivo, sem aparecer em pendencia
       -- nem em divergencia.
       OR EXISTS (SELECT 1 FROM public.supervisor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.origem = 'MANUAL');

    -- Ate 30 dias a janela fecha pela producao e a linha e reportada como
    -- divergencia. Acima disso nao ha aviso previo que explique, e a
    -- carga para.
    INSERT INTO mrh_pendencias
    SELECT d.linha, 'DESLIGAMENTO', 'PRODUCAO_POSTERIOR_OU_IGUAL'
    FROM mrh_desl d
    WHERE d.dias_apos > 30;

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'JANELA_INCOMPATIVEL'
    FROM mrh_desl d
    WHERE EXISTS (SELECT 1 FROM public.consultor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.vigencia_inicio >= d.data_efetiva)
       OR EXISTS (SELECT 1 FROM public.supervisor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.vigencia_inicio >= d.data_efetiva)
       OR EXISTS (SELECT 1 FROM public.consultor_afastamento a
                  WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL
                    AND a.data_inicio >= d.data_efetiva);

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'ORDEM_MOVIMENTACOES_INVALIDA'
    FROM mrh_desl d JOIN mrh_afast a ON a.nn = d.nn
    WHERE a.data_inicio >= d.data_efetiva;

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM (SELECT DISTINCT linha, origem, codigo FROM mrh_pendencias) p;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias,
            'afastamentos_recebidos', v_afast_len,
            'desligamentos_recebidos', v_desl_len);
    END IF;

    -- Sem nome: o envelope e agregado por desenho e pode ser logado
    -- inteiro. A linha da planilha basta para a conferencia.
    SELECT count(*), jsonb_agg(jsonb_build_object(
               'linha', linha, 'codigo', 'FECHADO_POR_PRODUCAO',
               'dias', dias_apos, 'data_arquivo', data_desligamento,
               'data_aplicada', data_efetiva) ORDER BY linha)
      INTO v_desl_producao, v_divergencias
    FROM mrh_desl WHERE ultima_producao IS NOT NULL;

    IF p_validar_apenas THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', true, 'error', NULL,
            'pendencias', '[]'::jsonb,
            'divergencias', coalesce(v_divergencias, '[]'::jsonb),
            'afastamentos_recebidos', v_afast_len,
            'desligamentos_recebidos', v_desl_len);
    END IF;

    -- Afastamentos: evento exato ja fechado por producao nao reabre.
    -- Isso torna a repeticao do mesmo arquivo um no-op real.
    FOR v_row IN SELECT * FROM mrh_afast ORDER BY linha LOOP
        v_id := NULL;
        SELECT a.id, a.tipo, a.data_inicio, a.data_fim
          INTO v_id, v_tipo_atual, v_inicio_atual, v_fim_atual
        FROM public.consultor_afastamento a
        WHERE a.nome_normalizado = v_row.nn
          AND a.data_inicio = v_row.data_inicio
        ORDER BY a.created_at, a.id
        LIMIT 1;

        IF v_id IS NULL THEN
            SELECT a.id, a.tipo, a.data_inicio, a.data_fim
              INTO v_id, v_tipo_atual, v_inicio_atual, v_fim_atual
            FROM public.consultor_afastamento a
            WHERE a.nome_normalizado = v_row.nn AND a.data_fim IS NULL
            LIMIT 1;
        END IF;

        IF v_id IS NULL THEN
            INSERT INTO public.consultor_afastamento
                (nome, tipo, data_inicio, data_fim, origem)
            VALUES (v_row.nome, v_row.tipo, v_row.data_inicio,
                    v_row.data_fim, 'ETL');
            v_afast_inseridos := v_afast_inseridos + 1;
        ELSIF v_tipo_atual IS DISTINCT FROM v_row.tipo
           OR (v_fim_atual IS NULL AND v_inicio_atual IS DISTINCT FROM v_row.data_inicio)
           OR (v_row.data_fim IS NOT NULL AND v_fim_atual IS DISTINCT FROM v_row.data_fim) THEN
            UPDATE public.consultor_afastamento
               SET nome = v_row.nome,
                   tipo = v_row.tipo,
                   data_inicio = v_row.data_inicio,
                   data_fim = coalesce(v_row.data_fim, data_fim),
                   origem = 'ETL'
             WHERE id = v_id;
            v_afast_atualizados := v_afast_atualizados + 1;
        ELSE
            v_afast_inalterados := v_afast_inalterados + 1;
        END IF;
    END LOOP;

    -- Desligamento encerra todos os papeis atuais da pessoa. A loja do
    -- arquivo e informativa e opcional (099): a identidade e global por
    -- nome, como nos tres ledgers existentes.
    UPDATE public.consultor_vigencia v
       SET vigencia_fim = d.data_efetiva,
           -- A origem diz de onde veio a DATA, nao de onde veio o evento.
           origem = CASE WHEN d.ultima_producao IS NULL THEN 'ETL'
                         ELSE 'BACKFILL_PRODUCAO' END
      FROM mrh_desl d
     WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
       AND v.vigencia_inicio < d.data_efetiva;
    GET DIAGNOSTICS v_desl_consultores = ROW_COUNT;

    -- Mesma regra de procedencia do consultor logo acima: a origem diz
    -- de onde veio a DATA. `origem <> 'MANUAL'` e redundante com a
    -- pendencia (a linha inteira ja teria parado a carga) e fica como
    -- rede: se um dia a pendencia virar aviso, o UPDATE nao passa a
    -- apagar correcao humana em silencio por conta disso.
    UPDATE public.supervisor_vigencia v
       SET vigencia_fim = d.data_efetiva,
           origem = CASE WHEN d.ultima_producao IS NULL THEN 'ETL'
                         ELSE 'BACKFILL_PRODUCAO' END
      FROM mrh_desl d
     WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
       AND v.vigencia_inicio < d.data_efetiva
       AND v.origem <> 'MANUAL';
    GET DIAGNOSTICS v_desl_supervisores = ROW_COUNT;

    UPDATE public.consultor_afastamento a
       SET data_fim = d.data_efetiva
      FROM mrh_desl d
     WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL
       AND a.data_inicio < d.data_efetiva;
    GET DIAGNOSTICS v_desl_afast = ROW_COUNT;

    UPDATE public.consultores c SET status = 'Desligado (a)'
    FROM mrh_desl d
    WHERE public.fn_normalizar_nome(btrim(c.nome)) = d.nn
      AND c.status IS DISTINCT FROM 'Desligado (a)';
    GET DIAGNOSTICS v_desl_cadastros = ROW_COUNT;

    DELETE FROM public.supervisores s USING mrh_desl d
    WHERE public.fn_normalizar_nome(btrim(s.nome)) = d.nn;

    -- Producao somente fecha ausencia; nunca a cria.
    v_afast_prod := public.fn_fechar_afastamentos_por_producao();

    RETURN jsonb_build_object(
        'aplicado', true, 'validar_apenas', false, 'error', NULL,
        'pendencias', '[]'::jsonb,
        'afastamentos', jsonb_build_object(
            'recebidos', v_afast_len, 'inseridos', v_afast_inseridos,
            'atualizados', v_afast_atualizados,
            'inalterados', v_afast_inalterados,
            'fechados_por_producao', v_afast_prod),
        'divergencias', coalesce(v_divergencias, '[]'::jsonb),
        'desligamentos', jsonb_build_object(
            'recebidos', v_desl_len,
            'fechados_por_producao', v_desl_producao,
            'vigencias_consultor_fechadas', v_desl_consultores,
            'vigencias_supervisor_fechadas', v_desl_supervisores,
            'cadastros_consultor_atualizados', v_desl_cadastros,
            'afastamentos_fechados', v_desl_afast));
END;
$fn$;


-- fn_contar_pagamentos_sem_vinculo_origem — vigente na 129; 2 troca(s)
CREATE OR REPLACE FUNCTION public.fn_contar_pagamentos_sem_vinculo_origem(p_mes integer, p_ano integer)
 RETURNS integer
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
WITH
periodo_base AS (
    SELECT
        make_date(p_ano, p_mes, 1) AS mes_inicio,
        (make_date(p_ano, p_mes, 1) + interval '1 month')::date AS mes_fim
),
periodo AS (
    SELECT
        pb.*,
        (pb.mes_fim - 1) AS ancora,
        ((pb.mes_fim - 1)
          - (extract(isodow FROM pb.mes_fim - 1)::integer % 7))::date
            AS semana_fim
    FROM periodo_base pb
),
parametros AS (
    SELECT p.*, (p.semana_fim - 55)::date AS semana_inicio
    FROM periodo p
),
supervisores AS (
    SELECT DISTINCT sv.nome_normalizado AS consultant_id
    FROM public.supervisor_vigencia sv
    CROSS JOIN parametros p
    WHERE sv.vigencia_inicio <= p.ancora
      AND (sv.vigencia_fim IS NULL OR sv.vigencia_fim > p.ancora)
),
eventos_pagos AS (
    SELECT
        v.id,
        v.data_cadastro::date AS data_origem,
        public.fn_normalizar_nome(btrim(coalesce(v.consultor, ''))) AS consultant_id,
        c.loja_id,
        -- 129: loja reinaugurada (PDV -> HELP) e a MESMA loja. O ETL
        -- rotula pelo lote de carga, nao pela data, entao a guarda
        -- compara a loja canonica dos dois lados.
        coalesce(lj.sucessora_id, c.loja_id) AS loja_canonica,
        CASE
            WHEN coalesce(v.conta_valor, true) = false THEN 0
            ELSE coalesce(v.valor_consolidado, 0)
        END::numeric AS paid_effective
    FROM public.v_contratos_dashboard v
    JOIN public.contratos c ON c.id = v.id
    LEFT JOIN public.lojas lj ON lj.id = c.loja_id
    LEFT JOIN public.periodos per ON per.id = v.periodo_id
    LEFT JOIN supervisores s
      ON s.consultant_id = public.fn_normalizar_nome(btrim(coalesce(v.consultor, '')))
    CROSS JOIN parametros p
    WHERE s.consultant_id IS NULL
      AND upper(btrim(coalesce(v.loja, ''))) <> 'VAI E VEM'
      AND (
          (per.mes = p_mes AND per.ano = p_ano)
          OR v.data_status_pagamento::date
               BETWEEN p.semana_inicio AND p.semana_fim
      )
),
sem_vinculo AS (
    SELECT e.id
    FROM eventos_pagos e
    WHERE e.paid_effective > 0
      AND (
          e.data_origem IS NULL
          OR e.consultant_id = ''
          OR e.loja_id IS NULL
          OR NOT EXISTS (
              SELECT 1
              FROM public.consultor_vigencia cv
              JOIN public.lojas lcv ON lcv.id = cv.loja_id
              WHERE cv.nome_normalizado = e.consultant_id
                AND coalesce(lcv.sucessora_id, lcv.id) = e.loja_canonica
                AND e.data_origem >= cv.vigencia_inicio
                AND (cv.vigencia_fim IS NULL
                     OR e.data_origem < cv.vigencia_fim)
          )
      )
)
SELECT count(*)::integer FROM sem_vinculo;
$function$;


-- obter_caderno_fechamento — vigente na 136; 2 troca(s)
CREATE OR REPLACE FUNCTION public.obter_caderno_fechamento(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
WITH
lojas_backoffice AS (
    -- Fonte unica do literal: um novo ponto de backoffice entra aqui e
    -- passa a valer para todos os eixos comparativos de uma vez.
    SELECT unnest(ARRAY['VAI E VEM']) AS nome
),
periodos_ano AS (
    SELECT id, mes, ano, referencia
    FROM public.periodos
    WHERE ano = p_ano
      AND mes BETWEEN 1 AND p_mes
),
periodo AS (
    SELECT *
    FROM periodos_ano
    WHERE mes = p_mes
),
pontos_categoria_ano AS (
    SELECT
        per.id AS periodo_id,
        pc.categoria_codigo,
        pc.pontos
    FROM periodos_ano per
    CROSS JOIN LATERAL public.obter_pontuacao_periodo(per.mes, per.ano) pc
),
contratos_canonicos AS (
    SELECT
        v.*,
        per.mes AS competencia_mes,
        per.ano AS competencia_ano,
        -- 135/136: modalidade da tabela no MES DO CADASTRO (versionada).
        v.modalidade AS modalidade_tabela,
        coalesce(
            v.categoria_codigo,
            CASE upper(btrim(coalesce(v.tipo_produto, '')))
                WHEN 'CNC' THEN 'CNC'
                WHEN 'CNC 13º' THEN 'CNC_13'
                WHEN 'CNC 13' THEN 'CNC_13'
                WHEN 'CNC ANT' THEN 'ANT_BENEF'
                WHEN 'ANT. DE BENEF.' THEN 'ANT_BENEF'
                WHEN 'SAQUE' THEN 'SAQUE'
                WHEN 'SAQUE BENEFICIO' THEN 'SAQUE_BENEFICIO'
                WHEN 'CONSIG' THEN 'CONSIG_BMG'
                WHEN 'CONSIG BMG' THEN 'CONSIG_BMG'
                WHEN 'CONSIG PRIV' THEN 'CONSIG_PRIV'
                WHEN 'CLT' THEN 'CONSIG_PRIV'
                WHEN 'CONSIG ITAU' THEN 'CONSIG_ITAU'
                WHEN 'CONSIG C6' THEN 'CONSIG_C6'
                WHEN 'FGTS' THEN 'FGTS'
                WHEN 'EMISSAO' THEN 'CARTAO'
                WHEN 'EMISSAO CB' THEN 'CARTAO'
                WHEN 'EMISSAO CC' THEN 'CARTAO'
                WHEN 'PORTABILIDADE' THEN 'PORTABILIDADE'
            END
        ) AS categoria_canonica
    FROM public.v_contratos_dashboard v
    JOIN periodos_ano per ON per.id = v.periodo_id
),
contratos_classificados AS (
    SELECT
        v.contrato_id,
        v.periodo_id,
        v.competencia_mes,
        v.competencia_ano,
        v.loja,
        v.regiao,
        v.regiao_atual,
        v.consultor,
        v.categoria_canonica AS categoria_codigo,
        v.banco,
        v.subtipo,
        v.prazo,
        v.modalidade_tabela,
        CASE
            WHEN coalesce(v.conta_valor, true) = false THEN 0
            ELSE coalesce(v.valor_consolidado, 0)
        END::numeric AS valor_pago,
        CASE
            WHEN v.categoria_canonica = 'PORTABILIDADE'
             AND (v.competencia_ano > 2026
                  OR (v.competencia_ano = 2026 AND v.competencia_mes >= 10))
             AND EXISTS (
                    SELECT 1 FROM pontos_categoria_ano pp
                     WHERE pp.periodo_id = v.periodo_id
                       AND pp.categoria_codigo = 'PORTABILIDADE'
                 )
                THEN 'PORTABILIDADE'
            WHEN v.categoria_canonica = 'PORTABILIDADE' THEN
                CASE upper(btrim(coalesce(v.banco, '')))
                    WHEN 'BMG' THEN 'CONSIG_BMG'
                    WHEN 'BANCO BMG' THEN 'CONSIG_BMG'
                    WHEN 'C6 BANK' THEN 'CONSIG_C6'
                    WHEN 'C6' THEN 'CONSIG_C6'
                    WHEN 'BANCO C6' THEN 'CONSIG_C6'
                    WHEN 'ITAU' THEN 'CONSIG_ITAU'
                    WHEN 'ITAÚ' THEN 'CONSIG_ITAU'
                    WHEN 'BANCO ITAU' THEN 'CONSIG_ITAU'
                    WHEN 'BANCO ITAÚ' THEN 'CONSIG_ITAU'
                END
            WHEN v.categoria_canonica IN ('SAQUE', 'SAQUE_BENEFICIO')
             AND upper(btrim(coalesce(v.convenio, ''))) = 'GOVERNO DO RJ'
             AND (v.competencia_ano > 2026
                  OR (v.competencia_ano = 2026 AND v.competencia_mes >= 9))
             AND EXISTS (
                    SELECT 1 FROM pontos_categoria_ano pg
                     WHERE pg.periodo_id = v.periodo_id
                       AND pg.categoria_codigo = 'CARTAO_GOV'
                 )
                THEN 'CARTAO_GOV'
            ELSE v.categoria_canonica
        END AS categoria_pontos,
        CASE
            WHEN v.modalidade_tabela = 'FLEX' THEN 'FLEX'
            WHEN v.categoria_canonica IN ('CONSIG_BMG', 'CONSIG_ITAU', 'CONSIG_C6')
             AND upper(btrim(coalesce(v.subtipo, ''))) = 'NOVO'
             AND nullif(regexp_replace(coalesce(v.prazo, ''), '[^0-9]', '', 'g'), '')::integer < 96
                THEN 'FLEX'
            WHEN v.modalidade_tabela = 'NORMAL' THEN 'NORMAL'
            ELSE 'DESCONHECIDA'
        END AS classificacao_validade,
        CASE
            WHEN v.categoria_canonica IN ('CNC', 'CNC_13', 'SUPER_CONTA') THEN 'CNC'
            WHEN v.categoria_canonica = 'FGTS' THEN 'FGTS'
            WHEN v.categoria_canonica IN ('SAQUE', 'SAQUE_BENEFICIO') THEN 'SAQUE'
            WHEN v.categoria_canonica = 'CONSIG_PRIV' THEN 'CLT'
            WHEN v.categoria_canonica = 'ANT_BENEF' THEN 'ANTECIP_BENEFICIO'
            WHEN v.categoria_canonica IN ('CONSIG_BMG', 'CONSIG_ITAU', 'CONSIG_C6', 'PORTABILIDADE') THEN 'CONSIGNADO'
        END AS grupo_mix,
        coalesce(v.conta_pontuacao, true) AS conta_pontuacao
    FROM contratos_canonicos v
),
base_ano AS (
    SELECT
        c.*,
        coalesce(pc.pontos, 0)::numeric AS multiplicador_pontos,
        CASE WHEN c.conta_pontuacao
             THEN c.valor_pago * coalesce(pc.pontos, 0)
             ELSE 0 END::numeric AS pontos_efetivos,
        CASE WHEN c.classificacao_validade = 'NORMAL'
             THEN c.valor_pago ELSE 0 END::numeric AS valor_valido,
        CASE WHEN c.classificacao_validade = 'FLEX'
             THEN c.valor_pago ELSE 0 END::numeric AS valor_flex
    FROM contratos_classificados c
    LEFT JOIN pontos_categoria_ano pc
      ON pc.periodo_id = c.periodo_id
     AND pc.categoria_codigo = c.categoria_pontos
),
base AS (
    SELECT *
    FROM base_ano
    WHERE competencia_mes = p_mes
),
metas_ano AS (
    SELECT
        per.mes AS competencia_mes,
        per.ano AS competencia_ano,
        m.loja,
        m.regiao,
        m.nivel,
        m.valor
    FROM periodos_ano per
    CROSS JOIN LATERAL public.obter_metas_geral_loja(per.mes, per.ano) m
),
metas_loja AS (
    SELECT
        loja,
        max(regiao) AS regiao,
        sum(valor) FILTER (WHERE nivel = 'PRATA')::numeric AS meta_prata,
        sum(valor) FILTER (WHERE nivel = 'OURO')::numeric AS meta_ouro
    FROM metas_ano
    WHERE competencia_mes = p_mes
    GROUP BY loja
),
lojas AS (
    SELECT
        coalesce(b.loja, m.loja) AS loja,
        coalesce(max(b.regiao), max(m.regiao), '') AS regiao,
        coalesce(sum(b.valor_pago), 0)::numeric AS pago,
        coalesce(sum(b.valor_valido), 0)::numeric AS valido,
        coalesce(sum(b.pontos_efetivos), 0)::numeric AS pontos,
        coalesce(max(m.meta_prata), 0)::numeric AS meta_prata,
        coalesce(max(m.meta_ouro), 0)::numeric AS meta_ouro
    FROM base b
    FULL JOIN metas_loja m ON m.loja = b.loja
    WHERE upper(btrim(coalesce(b.loja, m.loja, '')))
          NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY coalesce(b.loja, m.loja)
),
ranking AS (
    SELECT
        row_number() OVER (
            ORDER BY CASE WHEN meta_prata > 0 THEN pontos / meta_prata ELSE 0 END DESC,
                     pontos DESC, loja
        ) AS position,
        loja AS store,
        regiao AS manager,
        pago AS "paidEffective",
        valido AS "validProduction",
        pontos AS "effectivePoints",
        meta_prata AS "silverGoal",
        meta_ouro AS "goldGoal",
        CASE WHEN meta_prata > 0 THEN pontos / meta_prata ELSE 0 END AS "silverAchievement",
        CASE WHEN meta_ouro > 0 THEN pontos / meta_ouro ELSE 0 END AS "goldAchievement"
    FROM lojas
),
pontos_mensais_loja AS (
    SELECT
        competencia_mes,
        loja,
        regiao,
        sum(pontos_efetivos)::numeric AS pontos
    FROM base_ano
    WHERE loja IS NOT NULL
    GROUP BY competencia_mes, loja, regiao
),
metas_mensais_loja AS (
    SELECT
        competencia_mes,
        loja,
        regiao,
        coalesce(sum(valor) FILTER (WHERE nivel = 'PRATA'), 0)::numeric AS meta_prata,
        coalesce(sum(valor) FILTER (WHERE nivel = 'OURO'), 0)::numeric AS meta_ouro
    FROM metas_ano
    WHERE upper(btrim(coalesce(loja, '')))
          NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY competencia_mes, loja, regiao
),
desempenho_mensal_base AS (
    SELECT
        coalesce(p.competencia_mes, m.competencia_mes) AS competencia_mes,
        coalesce(p.loja, m.loja) AS loja,
        coalesce(p.regiao, m.regiao, '') AS regiao,
        coalesce(p.pontos, 0)::numeric AS pontos,
        coalesce(m.meta_prata, 0)::numeric AS meta_prata,
        coalesce(m.meta_ouro, 0)::numeric AS meta_ouro
    FROM pontos_mensais_loja p
    FULL JOIN metas_mensais_loja m
      ON m.competencia_mes = p.competencia_mes
     AND m.loja = p.loja
     AND m.regiao = p.regiao
),
desempenho_mensal AS (
    SELECT
        competencia_mes AS month,
        loja AS store,
        regiao AS manager,
        CASE
            WHEN upper(btrim(coalesce(loja, '')))
                 IN (SELECT nome FROM lojas_backoffice)
                THEN 'NETWORK_ONLY'
            ELSE 'STORE_REGION'
        END AS "comparisonScope",
        pontos AS "effectivePoints",
        meta_prata AS "silverGoal",
        meta_ouro AS "goldGoal",
        CASE WHEN meta_prata > 0 THEN pontos / meta_prata ELSE 0 END AS "silverAchievement",
        CASE WHEN meta_ouro > 0 THEN pontos / meta_ouro ELSE 0 END AS "goldAchievement",
        CASE
            WHEN meta_ouro > 0 AND pontos >= meta_ouro THEN 'OURO'
            WHEN meta_prata > 0 AND pontos >= meta_prata THEN 'PRATA'
            WHEN meta_prata = 0 AND meta_ouro = 0 THEN 'SEM_META'
            ELSE 'ABAIXO'
        END AS level
    FROM desempenho_mensal_base
),
consultores_mais_recentes AS (
    SELECT DISTINCT ON (n.nome_normalizado)
        c.id,
        c.nome,
        c.loja_id,
        c.status,
        c.updated_at,
        n.nome_normalizado
    FROM public.consultores c
    CROSS JOIN LATERAL (
        SELECT public.fn_normalizar_nome(btrim(coalesce(c.nome, ''))) AS nome_normalizado
    ) n
    WHERE n.nome_normalizado <> ''
    ORDER BY n.nome_normalizado, c.updated_at DESC NULLS LAST, c.id DESC
),
competencia_ancora AS (
    -- Ancora de leitura REVISADA em 2026-08-18 (ver cabecalho): o papel
    -- vigente no ULTIMO DIA da competencia vale para o mes inteiro —
    -- quem fechou o mes responde por ele. Continua sendo UMA regra so
    -- para producao e headcount, entao nenhum mes fica com a pessoa
    -- dentro do ranking e fora do denominador ao mesmo tempo.
    --
    -- Janela meio-aberta [inicio, fim): quem encerra exatamente no
    -- ultimo dia do mes NAO cobre esse dia, entao o mes pertence ao
    -- sucessor. E a mesma convencao usada em todo o ledger.
    SELECT (make_date(p_ano, p_mes, 1)
            + INTERVAL '1 month - 1 day')::date AS dia
),
supervisores_normalizados AS (
    -- POINT-IN-TIME (076/077/078/084): quem era supervisor NA COMPETENCIA,
    -- nao quem e supervisor hoje. Antes desta versao a foto do presente
    -- filtrava toda a historia, entao uma promocao apagava
    -- retroativamente os meses em que a pessoa vendia como consultora e
    -- uma saida da supervisao devolvia os meses em que ela supervisionava.
    SELECT DISTINCT v.nome_normalizado
    FROM public.supervisor_vigencia v
    CROSS JOIN competencia_ancora a
    WHERE v.vigencia_inicio <= a.dia
      AND (v.vigencia_fim IS NULL OR v.vigencia_fim > a.dia)
),
pago_consultores AS (
    -- Producao que entra na PRODUTIVIDADE — sem supervisor.
    --
    -- Ate a 095 a produtividade era `pago / peso`, com `pago` incluindo a
    -- producao de quem era supervisor e `peso` excluindo a capacidade
    -- dele. Media por consultor calculada sobre populacoes diferentes.
    --
    -- A regra do projeto e explicita (docs/agents/business-rules.md,
    -- "Exclusao de supervisores"): aplicar ANTES de rankings, contagens
    -- de consultores e MEDIAS POR CONSULTOR. A excecao de 2026-08-10
    -- devolveu supervisor ao TOTAL — e so ao total; media nunca.
    --
    -- Medido em 07/2026 antes da correcao: R$ 130.617,59 (1,29% do pago)
    -- vinham de 17 supervisores, dos quais 16 supervisionaram o mes
    -- inteiro e pesavam ZERO no denominador. Na rede isso inflava a
    -- produtividade em 1,30%; em HELP PRACA SECA, que tem peso 1,00 e
    -- recebeu R$ 77.202 de uma supervisora, inflava 89,2% — e
    -- `productivity` e o que ORDENA o ranking publicado.
    --
    -- `paidEffective` continua sendo o total COM supervisor: e a regra
    -- de 2026-08-10 e nao muda aqui. Por isso a produtividade passa a
    -- expor o proprio numerador (`paidByConsultants`), senao quem
    -- dividir `paidEffective / weightedHeadcount` a mao continua sem
    -- fechar — exatamente a armadilha que o contrato de ETL ja alertou.
    SELECT
        b.loja,
        coalesce(sum(b.valor_pago), 0)::numeric AS pago
    FROM base b
    LEFT JOIN supervisores_normalizados s
      ON s.nome_normalizado = public.fn_normalizar_nome(btrim(coalesce(b.consultor, '')))
    WHERE s.nome_normalizado IS NULL
      AND upper(btrim(coalesce(b.loja, '')))
          NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY b.loja
),
consultores_ativos AS (
    -- Status vazio conta como ativo (linhas legadas sem status); match por
    -- prefixo para "Inativo (a)" nunca entrar. Mesma regra do dashboard.
    SELECT c.*
    FROM consultores_mais_recentes c
    WHERE btrim(coalesce(c.status, '')) = ''
       OR upper(btrim(c.status)) LIKE 'ATIVO%'
),
consultores_classificados AS (
    -- As quatro categorias abaixo particionam o cadastro ativo: cada
    -- consultor cai em exatamente uma, e so a ultima entra no headcount.
    SELECT
        l.nome AS loja,
        (s.nome_normalizado IS NOT NULL) AS eh_supervisor,
        (l.id IS NOT NULL AND coalesce(l.ativo, true)) AS tem_loja_ativa,
        (upper(btrim(coalesce(l.nome, '')))
             IN (SELECT nome FROM lojas_backoffice)) AS eh_backoffice
    FROM consultores_ativos c
    LEFT JOIN public.lojas l ON l.id = c.loja_id
    LEFT JOIN supervisores_normalizados s
      ON s.nome_normalizado = c.nome_normalizado
),
headcount_loja AS (
    SELECT
        loja,
        count(*)::integer AS total
    FROM consultores_classificados
    WHERE NOT eh_supervisor
      AND tem_loja_ativa
      AND NOT eh_backoffice
    GROUP BY loja
),
headcount_diagnostico AS (
    SELECT
        count(*)::integer AS ativos_cadastro,
        count(*) FILTER (WHERE eh_supervisor)::integer AS supervisores,
        count(*) FILTER (
            WHERE NOT eh_supervisor AND NOT tem_loja_ativa
        )::integer AS sem_loja_ativa,
        count(*) FILTER (
            WHERE NOT eh_supervisor AND tem_loja_ativa AND eh_backoffice
        )::integer AS backoffice
    FROM consultores_classificados
),
headcount_ponderado AS (
    -- FONTE DO NUMERO PUBLICADO (091). `cabecas` e a contagem inteira
    -- point-in-time; `peso` e o gente-mes que divide o pago.
    --
    -- A 091 devolve TODA loja com vinculo, inclusive backoffice e loja
    -- inativa — ela responde "quem estava onde", nao "o que entra no
    -- Caderno". Os dois filtros que o headcount do cadastro ja aplicava
    -- (`tem_loja_ativa`, `NOT eh_backoffice`) sao reaplicados aqui.
    SELECT
        h.loja,
        h.peso,
        h.cabecas
    FROM public.fn_headcount_ponderado(p_mes, p_ano) h
    JOIN public.lojas l ON l.id = h.loja_id
    WHERE coalesce(l.ativo, true)
      AND upper(btrim(coalesce(h.loja, '')))
          NOT IN (SELECT nome FROM lojas_backoffice)
),
headcount AS (
    SELECT
        coalesce(sum(cabecas), 0)::integer AS total,
        coalesce(sum(peso), 0)::numeric    AS peso_total
    FROM headcount_ponderado
),
headcount_cadastro AS (
    -- O antigo `activeConsultants` (cadastro de HOJE). Deixa de ser o
    -- numero publicado e vira linha de auditoria em
    -- headcountDiagnostics.countedInRegistry, onde a identidade da 075
    -- continua fechando.
    SELECT coalesce(sum(total), 0)::integer AS total
    FROM headcount_loja
),
produtividade_base AS (
    SELECT
        l.loja,
        l.regiao,
        l.pago,
        coalesce(h.cabecas, 0)::integer AS ativos,
        coalesce(h.peso, 0)::numeric    AS peso,
        coalesce(pc.pago, 0)::numeric   AS pago_consultores,
        -- Denominador PONDERADO (R2/R3). Peso 0 devolve 0, mesmo idioma
        -- que a 085 usava para ativos 0: loja sem ninguem no ledger nao
        -- tem produtividade definida, e inventar uma seria pior.
        --
        -- Numerador SEM supervisor (096): mesma populacao do denominador.
        CASE WHEN coalesce(h.peso, 0) > 0
             THEN coalesce(pc.pago, 0) / h.peso
             ELSE 0 END::numeric AS produtividade
    FROM lojas l
    LEFT JOIN headcount_ponderado h ON h.loja = l.loja
    LEFT JOIN pago_consultores    pc ON pc.loja = l.loja
    -- `lojas` ja exclui o backoffice; filtro redundante removido aqui.
),
produtividade AS (
    SELECT
        row_number() OVER (ORDER BY produtividade DESC, pago DESC, loja) AS position,
        loja AS store,
        regiao AS manager,
        pago AS "paidEffective",
        pago_consultores AS "paidByConsultants",
        ativos AS "activeConsultants",
        peso AS "weightedHeadcount",
        produtividade AS productivity
    FROM produtividade_base
),
resumo AS (
    SELECT
        coalesce(sum(valor_pago), 0)::numeric AS pago,
        coalesce(sum(valor_valido), 0)::numeric AS valido,
        coalesce(sum(valor_flex), 0)::numeric AS flex,
        coalesce(sum(pontos_efetivos), 0)::numeric AS pontos,
        count(*) FILTER (WHERE classificacao_validade = 'DESCONHECIDA')::integer AS desconhecidos
    FROM base
),
backoffice AS (
    SELECT
        coalesce(sum(valor_pago), 0)::numeric AS pago,
        coalesce(sum(valor_valido), 0)::numeric AS valido,
        coalesce(sum(pontos_efetivos), 0)::numeric AS pontos
    FROM base
    WHERE upper(btrim(coalesce(loja, ''))) IN (SELECT nome FROM lojas_backoffice)
),
mix AS (
    SELECT
        grupo_mix AS product,
        sum(valor_pago)::numeric AS "paidEffective",
        CASE WHEN sum(sum(valor_pago)) OVER () > 0
             THEN sum(valor_pago) / sum(sum(valor_pago)) OVER ()
             ELSE 0 END::numeric AS share
    FROM base
    WHERE grupo_mix IS NOT NULL
    GROUP BY grupo_mix
),
produto_lojas AS (
    SELECT
        grupo_mix AS product,
        loja AS store,
        max(regiao) AS manager,
        sum(valor_pago)::numeric AS "paidEffective",
        sum(valor_valido)::numeric AS "validProduction",
        sum(pontos_efetivos)::numeric AS "effectivePoints"
    FROM base
    WHERE grupo_mix IS NOT NULL
      AND loja IS NOT NULL
      AND upper(btrim(loja)) NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY grupo_mix, loja
),
produto_ranking AS (
    SELECT
        product,
        row_number() OVER (PARTITION BY product ORDER BY "paidEffective" DESC, store) AS position,
        store,
        manager,
        "paidEffective",
        "validProduction",
        "effectivePoints"
    FROM produto_lojas
)
SELECT jsonb_build_object(
    'competence', jsonb_build_object('month', p_mes, 'year', p_ano, 'label', max(per.referencia)),
    'summary', jsonb_build_object(
        'paidEffective', max(r.pago),
        'validProduction', max(r.valido),
        'flexProduction', max(r.flex),
        'effectivePoints', max(r.pontos),
        'silverGoal', coalesce((SELECT sum(meta_prata) FROM lojas), 0),
        'storeCount', (SELECT count(*) FROM lojas),
        'activeConsultants', max(h.total),
        'weightedHeadcount', max(h.peso_total),
        'unknownClassificationCount', max(r.desconhecidos),
        'backoffice', jsonb_build_object(
            'paidEffective', max(bo.pago),
            'validProduction', max(bo.valido),
            'effectivePoints', max(bo.pontos)
        ),
        'headcountDiagnostics', jsonb_build_object(
            'activeRegistered', max(hd.ativos_cadastro),
            'supervisorsExcluded', max(hd.supervisores),
            'withoutActiveStore', max(hd.sem_loja_ativa),
            'backofficeExcluded', max(hd.backoffice),
            'countedInRegistry', max(hcad.total)
        )
    ),
    'ranking', coalesce((SELECT jsonb_agg(to_jsonb(rk) ORDER BY rk.position) FROM ranking rk), '[]'::jsonb),
    'monthlyPoints', coalesce((
        SELECT jsonb_agg(to_jsonb(dm) ORDER BY dm.month, dm.manager, dm.store)
        FROM desempenho_mensal dm
    ), '[]'::jsonb),
    'productivity', coalesce((
        SELECT jsonb_agg(to_jsonb(prd) ORDER BY prd.position)
        FROM produtividade prd
    ), '[]'::jsonb),
    'mix', coalesce((SELECT jsonb_agg(to_jsonb(mx) ORDER BY mx."paidEffective" DESC) FROM mix mx), '[]'::jsonb),
    'productRanking', coalesce((
        SELECT jsonb_agg(to_jsonb(pr) ORDER BY pr.product, pr.position)
        FROM produto_ranking pr
    ), '[]'::jsonb)
)
FROM periodo per
CROSS JOIN resumo r
CROSS JOIN headcount h
CROSS JOIN backoffice bo
CROSS JOIN headcount_diagnostico hd
CROSS JOIN headcount_cadastro hcad;
$$;


-- ===========================================
-- Verificacao — rodar ANTES e DEPOIS
-- ===========================================
--
-- 0) ANTES de aplicar, guardar a referencia (cada chamada leva ~4-7 s):
--
--    SELECT m, md5(public.obter_caderno_fechamento(m, 2026)::text)
--      FROM unnest(ARRAY[8, 9]) m;
--    SELECT m, public.fn_contar_pagamentos_sem_vinculo_origem(m, 2026)
--      FROM generate_series(1, 9) m;
--    -- Esperado DEPOIS: identicos. Nenhum nome muda de chave hoje.
--
-- 1) Nenhuma funcao viva com a regra antiga:
--
--    SELECT proname FROM pg_proc
--     WHERE pronamespace = 'public'::regnamespace
--       AND prosrc LIKE '%[[:space:]]+%';
--    -- Esperado: so fn_normalizar_nome.
--
-- 2) As tres colunas geradas pela funcao:
--
--    SELECT table_name, generation_expression
--      FROM information_schema.columns
--     WHERE table_schema = 'public' AND column_name = 'nome_normalizado';
--    -- Esperado: fn_normalizar_nome(nome) em supervisor_vigencia,
--    -- consultor_vigencia e consultor_afastamento.
--
-- 3) Mesma chave do normalizar_nome do dashboard:
--
--    SELECT public.fn_normalizar_nome(E'  João   da Silva\t');
--    -- Esperado: JOAO DA SILVA
