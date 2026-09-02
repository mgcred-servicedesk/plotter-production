-- =====================================================
-- Migracao 105: produtividade — origem do contrato x data do pagamento
-- Data: 2026-09-02
-- Depende de: 101 (snapshot individual privado)
--
-- Pagamento pode ocorrer depois de uma transferencia. Nesse caso, a linha
-- semanal conserva a loja do contrato e pode ter zero dias nessa loja, mas o
-- consultor tem dias elegiveis em outra loja na mesma semana. Isso nao e furo
-- de ledger.
--
-- O bloqueio correto valida se o contrato foi cadastrado durante uma vigencia
-- da pessoa na loja do contrato. A metrica continua no eixo de PAGAMENTO; a
-- data de cadastro serve somente para auditar a atribuicao de origem.
-- =====================================================


-- ===========================================
-- 1. Diagnostico de atribuicao na origem
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_contar_pagamentos_sem_vinculo_origem(
    p_mes integer,
    p_ano integer
)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
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
        upper(regexp_replace(
            btrim(coalesce(v.consultor, '')),
            '[[:space:]]+', ' ', 'g'
        )) AS consultant_id,
        c.loja_id,
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
              WHERE cv.nome_normalizado = e.consultant_id
                AND cv.loja_id = e.loja_id
                AND e.data_origem >= cv.vigencia_inicio
                AND (cv.vigencia_fim IS NULL
                     OR e.data_origem < cv.vigencia_fim)
          )
      )
)
SELECT count(*)::integer FROM sem_vinculo;
$fn$;

COMMENT ON FUNCTION public.fn_contar_pagamentos_sem_vinculo_origem(
    integer, integer
) IS
    'Conta eventos pagos usados pelo snapshot cuja data de cadastro nao cai '
    'numa vigencia da pessoa na loja do contrato. Pagamento posterior a uma '
    'transferencia e valido quando a origem do contrato estava vinculada.';

REVOKE ALL ON FUNCTION public.fn_contar_pagamentos_sem_vinculo_origem(
    integer, integer
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_contar_pagamentos_sem_vinculo_origem(
    integer, integer
) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_contar_pagamentos_sem_vinculo_origem(
    integer, integer
) TO service_role;


-- ===========================================
-- 2. Materializacao: bloqueio pela origem
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
    v_sem_vinculo_origem integer;
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

    SELECT public.fn_contar_pagamentos_sem_vinculo_origem(p_mes, p_ano)
      INTO v_sem_vinculo_origem;

    v_payload := jsonb_set(
        v_payload,
        '{diagnostics,unlinkedPaidOriginEvents}',
        to_jsonb(coalesce(v_sem_vinculo_origem, 0)),
        true
    );

    -- monthly/weeklyUnlinkedPaidRows continuam no diagnostico: medem
    -- segmentos pagos sem dias NA MESMA LOJA do pagamento. Isso e esperado
    -- depois de transferencia. O bloqueio usa a vigencia na origem do contrato.
    IF coalesce(v_sem_vinculo_origem, 0) > 0
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
        'unlinkedPaidOriginEvents', coalesce(v_sem_vinculo_origem, 0),
        'bytes', pg_column_size(v_payload),
        'gerado_em', now(),
        'error', NULL
    );
END;
$fn$;

COMMENT ON FUNCTION public.fn_materializar_produtividade_individual(
    integer, integer
) IS
    'Materializa o snapshot nominal privado. Bloqueia atribuicao cuja data '
    'de cadastro nao encontra vigencia da pessoa na loja de origem e '
    'sobreposicao diaria. Segmento sem dias na loja da semana e permitido '
    'quando decorre de pagamento posterior a transferencia.';

REVOKE ALL ON FUNCTION public.fn_materializar_produtividade_individual(
    integer, integer
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_materializar_produtividade_individual(
    integer, integer
) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_materializar_produtividade_individual(
    integer, integer
) TO service_role;


-- Depois de aplicar, o caso conhecido de 08/2026 deve continuar bloqueado
-- enquanto os 17 contratos de 18/08 estiverem apontando para Iluara:
--
-- SELECT public.fn_contar_pagamentos_sem_vinculo_origem(8, 2026);
-- -- esperado antes da correcao dos contratos: 17
-- -- esperado depois da reimportacao/correcao: 0
--
-- Os quatro pagamentos tardios de contratos validos (Ana Leticia, Renan,
-- Mizael e Victor) nao entram nessa contagem.
