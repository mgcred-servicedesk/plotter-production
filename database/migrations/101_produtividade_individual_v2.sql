-- =====================================================
-- Migracao 101: produtividade individual v2 materializada
--
-- Publica, em snapshot PRIVADO, a producao paga por dia util elegivel
-- de vinculo. A primeira revisao NAO consulta consultor_afastamento:
--
--   consideredDaysBasis = ELIGIBLE_LINK_DAYS
--   absenceCoverage      = NONE
--
-- O snapshot agregado do Caderno continua sem nomes e com os grants
-- atuais. O payload nominal fica em produtividade_individual_snapshot,
-- legivel somente pela service_role. fn_materializar_caderno passa a
-- congelar os dois payloads na mesma transacao e falha fechado quando:
--
--   * ha producao positiva sem dias de vinculo;
--   * o ledger atribui a mesma pessoa a duas lojas no mesmo dia;
--   * a soma individual por loja nao concilia (R$ 0,01) com
--     productivity.paidByConsultants da migration 096.
--
-- Depende de: 080, 085, 086/087, 092 e 096.
-- Nao depende de 097-100 e nao altera esses objetos.
-- =====================================================


-- ===========================================
-- 1. Snapshot nominal privado
-- ===========================================

CREATE TABLE IF NOT EXISTS public.produtividade_individual_snapshot (
    ano        smallint NOT NULL,
    mes        smallint NOT NULL,
    payload    jsonb NOT NULL,
    gerado_em  timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (ano, mes),
    CONSTRAINT chk_pis_mes CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT chk_pis_ano CHECK (ano BETWEEN 2020 AND 2100)
);

COMMENT ON TABLE public.produtividade_individual_snapshot IS
    'Snapshot PRIVADO da produtividade nominal por consultor. Contem as '
    'colecoes consultantProductivity e consultantWeeklyProductivity do '
    'contrato v2. SELECT somente para service_role; nao ampliar grants '
    'sem nova revisao de privacidade.';

COMMENT ON COLUMN public.produtividade_individual_snapshot.payload IS
    'Payload nominal congelado. Revisao inicial: dias uteis elegiveis de '
    'vinculo, sem desconto de afastamentos (absenceCoverage = NONE).';

ALTER TABLE public.produtividade_individual_snapshot ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_pis_deny
    ON public.produtividade_individual_snapshot;
CREATE POLICY pol_pis_deny
    ON public.produtividade_individual_snapshot
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

REVOKE ALL ON TABLE public.produtividade_individual_snapshot FROM PUBLIC;
REVOKE ALL ON TABLE public.produtividade_individual_snapshot
    FROM anon, authenticated;
GRANT SELECT ON TABLE public.produtividade_individual_snapshot TO service_role;


-- ===========================================
-- 2. Calculo puro: mensal + oito semanas ISO
-- ===========================================

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
        upper(regexp_replace(
            btrim(coalesce(v.consultor, '')),
            '[[:space:]]+', ' ', 'g'
        )) AS consultant_id,
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
      ON s.consultant_id = upper(regexp_replace(
             btrim(coalesce(v.consultor, '')),
             '[[:space:]]+', ' ', 'g'
         ))
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

COMMENT ON FUNCTION public.obter_produtividade_individual(integer, integer) IS
    'Calcula as colecoes nominais mensal e semanal do contrato v2. Base '
    'transitoria = dias uteis elegiveis de vinculo; NAO consulta '
    'consultor_afastamento. RPC privada: EXECUTE somente service_role.';

REVOKE ALL ON FUNCTION public.obter_produtividade_individual(integer, integer)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.obter_produtividade_individual(integer, integer)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.obter_produtividade_individual(integer, integer)
    TO service_role;


-- ===========================================
-- 3. Materializacao privada isolada
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_materializar_produtividade_individual(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '180s'
AS $fn$
DECLARE
    v_payload jsonb;
    v_competencia date;
    v_mes_corrente date := date_trunc('month', current_date)::date;
BEGIN
    IF p_mes IS NULL OR p_mes NOT BETWEEN 1 AND 12
       OR p_ano IS NULL OR p_ano NOT BETWEEN 2020 AND 2100 THEN
        RETURN jsonb_build_object(
            'error', format('Competencia invalida: %s/%s', p_mes, p_ano));
    END IF;

    v_competencia := make_date(p_ano, p_mes, 1);
    IF v_competencia >= v_mes_corrente THEN
        RETURN jsonb_build_object(
            'error', format(
                'Competencia %s/%s ainda nao fechou.', p_mes, p_ano));
    END IF;

    SELECT public.obter_produtividade_individual(p_mes, p_ano)
      INTO v_payload;

    IF v_payload IS NULL THEN
        RAISE EXCEPTION
            'Produtividade individual %/% devolveu payload nulo',
            p_mes, p_ano;
    END IF;

    IF coalesce((v_payload #>>
            '{diagnostics,monthlyUnlinkedPaidRows}')::integer, 0) > 0
       OR coalesce((v_payload #>>
            '{diagnostics,weeklyUnlinkedPaidRows}')::integer, 0) > 0
       OR coalesce((v_payload #>>
            '{diagnostics,overlappingEligibleDays}')::integer, 0) > 0 THEN
        RAISE EXCEPTION
            'Produtividade individual %/% bloqueada: diagnostico=%',
            p_mes, p_ano, v_payload->'diagnostics';
    END IF;

    INSERT INTO public.produtividade_individual_snapshot
        (ano, mes, payload, gerado_em)
    VALUES (p_ano, p_mes, v_payload, now())
    ON CONFLICT (ano, mes) DO UPDATE
        SET payload = EXCLUDED.payload,
            gerado_em = EXCLUDED.gerado_em;

    RETURN jsonb_build_object(
        'mes', p_mes,
        'ano', p_ano,
        'monthlyRows', v_payload #>
            '{diagnostics,monthlyRows}',
        'weeklyRows', v_payload #>
            '{diagnostics,weeklyRows}',
        'bytes', pg_column_size(v_payload),
        'gerado_em', now(),
        'error', NULL
    );
END;
$fn$;

COMMENT ON FUNCTION public.fn_materializar_produtividade_individual(
    integer, integer
) IS
    'Materializa somente o snapshot nominal privado. Falha fechado para '
    'producao sem vinculo ou sobreposicao diaria. Preferir '
    'fn_materializar_caderno, que tambem concilia por loja com o agregado.';

REVOKE ALL ON FUNCTION public.fn_materializar_produtividade_individual(
    integer, integer
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_materializar_produtividade_individual(
    integer, integer
) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_materializar_produtividade_individual(
    integer, integer
) TO service_role;


-- ===========================================
-- 4. Leitura privada publicada
-- ===========================================

CREATE OR REPLACE FUNCTION public.obter_produtividade_individual_publicada(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE sql
STABLE
PARALLEL SAFE
SET search_path = ''
AS $fn$
    SELECT s.payload
    FROM public.produtividade_individual_snapshot s
    WHERE s.ano = p_ano AND s.mes = p_mes;
$fn$;

COMMENT ON FUNCTION public.obter_produtividade_individual_publicada(
    integer, integer
) IS
    'Leitura por PK do snapshot nominal v2. NULL = competencia ainda nao '
    'materializada. EXECUTE somente service_role.';

REVOKE ALL ON FUNCTION public.obter_produtividade_individual_publicada(
    integer, integer
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.obter_produtividade_individual_publicada(
    integer, integer
) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.obter_produtividade_individual_publicada(
    integer, integer
) TO service_role;


-- ===========================================
-- 5. Publicacao atomica do agregado + nominal
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_materializar_caderno(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '180s'
AS $fn$
DECLARE
    v_payload jsonb;
    v_individual jsonb;
    v_individual_result jsonb;
    v_competencia date;
    v_mes_corrente date := date_trunc('month', current_date)::date;
    v_divergencias integer;
BEGIN
    IF p_mes IS NULL OR p_mes NOT BETWEEN 1 AND 12
       OR p_ano IS NULL OR p_ano NOT BETWEEN 2020 AND 2100 THEN
        RETURN jsonb_build_object(
            'error', format('Competencia invalida: %s/%s', p_mes, p_ano));
    END IF;

    v_competencia := make_date(p_ano, p_mes, 1);
    IF v_competencia >= v_mes_corrente THEN
        RETURN jsonb_build_object(
            'error', format(
                'Competencia %s/%s ainda nao fechou — o Caderno so '
                'materializa mes fechado.', p_mes, p_ano));
    END IF;

    SELECT public.obter_caderno_fechamento(p_mes, p_ano)
      INTO v_payload;
    IF v_payload IS NULL THEN
        RETURN jsonb_build_object(
            'error', format(
                'Sem periodo cadastrado para %s/%s — nada a materializar.',
                p_mes, p_ano));
    END IF;

    SELECT public.fn_materializar_produtividade_individual(p_mes, p_ano)
      INTO v_individual_result;
    IF v_individual_result->>'error' IS NOT NULL THEN
        RETURN v_individual_result;
    END IF;

    SELECT s.payload
      INTO v_individual
    FROM public.produtividade_individual_snapshot s
    WHERE s.ano = p_ano AND s.mes = p_mes;

    WITH agregado AS (
        SELECT
            x.store,
            coalesce(x."paidByConsultants", x."paidEffective", 0)::numeric
                AS paid
        FROM jsonb_to_recordset(v_payload->'productivity') AS x(
            store text,
            "paidByConsultants" numeric,
            "paidEffective" numeric
        )
    ),
    individual AS (
        SELECT
            item->>'store' AS store,
            sum((item->>'paidEffective')::numeric)::numeric AS paid
        FROM jsonb_array_elements(
            v_individual->'consultantProductivity'
        ) item
        GROUP BY item->>'store'
    ),
    diferencas AS (
        SELECT
            coalesce(a.store, i.store) AS store,
            coalesce(a.paid, 0) AS agregado,
            coalesce(i.paid, 0) AS individual
        FROM agregado a
        FULL JOIN individual i ON i.store = a.store
        WHERE abs(coalesce(a.paid, 0) - coalesce(i.paid, 0)) > 0.01
    )
    SELECT count(*)::integer INTO v_divergencias FROM diferencas;

    IF v_divergencias > 0 THEN
        RAISE EXCEPTION
            'Produtividade individual %/% nao concilia com '
            'paidByConsultants em % loja(s)',
            p_mes, p_ano, v_divergencias;
    END IF;

    INSERT INTO public.caderno_fechamento_snapshot
        (ano, mes, payload, gerado_em)
    VALUES (p_ano, p_mes, v_payload, now())
    ON CONFLICT (ano, mes) DO UPDATE
        SET payload = EXCLUDED.payload,
            gerado_em = EXCLUDED.gerado_em;

    RETURN jsonb_build_object(
        'mes', p_mes,
        'ano', p_ano,
        'bytes', pg_column_size(v_payload),
        'individualBytes', pg_column_size(v_individual),
        'individualMonthlyRows', v_individual #>
            '{diagnostics,monthlyRows}',
        'individualWeeklyRows', v_individual #>
            '{diagnostics,weeklyRows}',
        'gerado_em', now(),
        'error', NULL
    );
END;
$fn$;

COMMENT ON FUNCTION public.fn_materializar_caderno(integer, integer) IS
    'Publica atomicamente o Caderno agregado e a produtividade individual '
    'privada. So competencia fechada; timeout 180s. Bloqueia a transacao '
    'quando a base individual e invalida ou nao concilia por loja com '
    'productivity.paidByConsultants.';

REVOKE ALL ON FUNCTION public.fn_materializar_caderno(integer, integer)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_materializar_caderno(integer, integer)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_materializar_caderno(integer, integer)
    TO service_role;


-- ===========================================
-- 6. Validacao e operacao piloto
-- ===========================================
-- Aplicar a migration sem backfill automatico. Em seguida:
--
-- 1) Piloto atomico de uma competencia fechada:
--
--    SELECT public.fn_materializar_caderno(8, 2026);
--
-- 2) Diagnostico privado (nao executar com role de usuario):
--
--    SELECT
--        ano,
--        mes,
--        gerado_em,
--        payload->'diagnostics' AS diagnostics
--    FROM public.produtividade_individual_snapshot
--    WHERE ano = 2026 AND mes = 8;
--
-- 3) Concilia mensal por loja (esperado: zero linhas):
--
--    WITH agregado AS (
--      SELECT x.store,
--             coalesce(x."paidByConsultants", x."paidEffective", 0) paid
--      FROM public.caderno_fechamento_snapshot s
--      CROSS JOIN LATERAL jsonb_to_recordset(s.payload->'productivity') x(
--        store text, "paidByConsultants" numeric, "paidEffective" numeric)
--      WHERE s.ano = 2026 AND s.mes = 8
--    ), individual AS (
--      SELECT item->>'store' store,
--             sum((item->>'paidEffective')::numeric) paid
--      FROM public.produtividade_individual_snapshot s
--      CROSS JOIN LATERAL jsonb_array_elements(
--        s.payload->'consultantProductivity') item
--      WHERE s.ano = 2026 AND s.mes = 8
--      GROUP BY item->>'store'
--    )
--    SELECT coalesce(a.store, i.store), a.paid, i.paid
--    FROM agregado a FULL JOIN individual i USING (store)
--    WHERE abs(coalesce(a.paid, 0) - coalesce(i.paid, 0)) > 0.01;
--
-- 4) Grants (esperado: service_role apenas nas funcoes privadas):
--
--    SELECT routine_name, grantee
--    FROM information_schema.routine_privileges
--    WHERE routine_name IN (
--      'obter_produtividade_individual',
--      'obter_produtividade_individual_publicada',
--      'fn_materializar_produtividade_individual')
--    ORDER BY routine_name, grantee;
--
-- Rollback operacional: restaurar fn_materializar_caderno a partir da 080
-- e revogar EXECUTE das funcoes privadas. Nao apagar snapshots nominais sem
-- aprovacao: o congelamento publicado e dado auditavel.
