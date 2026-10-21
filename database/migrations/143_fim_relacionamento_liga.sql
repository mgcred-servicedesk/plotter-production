-- =====================================================
-- Migracao 143: Fim de relacionamento — Liga
-- Foto mensal do banco: nao refiltra 90 dias pelo relogio local e nao
-- divide a carga pelo mes de data_fim_relacionamento. O periodo e a
-- visao do arquivo (primeira carga: 10/2026, 231 ADEs / 229 qtde = 1).
-- Independente da Reconquista contabilizada e dos seus KPIs.
-- =====================================================

CREATE TABLE IF NOT EXISTS public.fim_relacionamento_liga (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id UUID NOT NULL REFERENCES public.periodos (id)
        ON DELETE CASCADE,
    co_adesao BIGINT NOT NULL CHECK (co_adesao > 0),
    qtde INTEGER NOT NULL CHECK (qtde IN (0, 1)),
    data_contrato DATE NOT NULL,
    data_fim_relacionamento DATE NOT NULL,
    franqueado TEXT,
    no_franquia TEXT,
    cod_bmg INTEGER CHECK (cod_bmg > 0),
    loja_id UUID REFERENCES public.lojas (id) ON DELETE SET NULL,
    consultor_nome TEXT,
    consultor_id UUID REFERENCES public.consultores (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_fim_relacionamento_liga_periodo_adesao
        UNIQUE (periodo_id, co_adesao)
);

COMMENT ON TABLE public.fim_relacionamento_liga IS
    'Foto de Fim de relacionamento da Liga por competencia escolhida. '
    'Uma ADE por periodo, incluindo qtde 0. Reimportacao atomica substitui '
    'somente a competencia; preserva as duas datas e o recorte do banco.';
COMMENT ON COLUMN public.fim_relacionamento_liga.qtde IS
    'Qt Fim Relacionamento: 1 = contabilizada pelo banco; 0 = apenas listada.';

ALTER TABLE public.fim_relacionamento_liga ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pol_fim_relacionamento_liga_deny
    ON public.fim_relacionamento_liga;
CREATE POLICY pol_fim_relacionamento_liga_deny
    ON public.fim_relacionamento_liga FOR ALL
    TO anon, authenticated USING (false) WITH CHECK (false);
REVOKE ALL ON public.fim_relacionamento_liga
    FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.fim_relacionamento_liga TO service_role;

CREATE OR REPLACE VIEW public.v_fim_relacionamento_liga
    WITH (security_invoker = on)
AS
SELECT
    f.id,
    f.periodo_id,
    f.co_adesao,
    p.ano,
    p.mes,
    f.qtde,
    f.data_contrato,
    f.data_fim_relacionamento,
    COALESCE(l.nome, f.no_franquia, '(Nao Identificado)') AS loja,
    reg.nome AS regiao,
    COALESCE(con.nome, f.consultor_nome, '(Sem Consultor)') AS consultor,
    f.franqueado,
    f.no_franquia,
    f.cod_bmg,
    f.consultor_nome
FROM public.fim_relacionamento_liga f
JOIN public.periodos p ON p.id = f.periodo_id
LEFT JOIN public.lojas l ON l.id = f.loja_id
LEFT JOIN public.regioes reg ON reg.id = l.regiao_id
LEFT JOIN public.consultores con ON con.id = f.consultor_id;

COMMENT ON VIEW public.v_fim_relacionamento_liga IS
    'Analitico da foto mensal FDR Liga. Nomes de escopo compativeis com '
    '_filtro_rls_reconquista; consumidor aplica RLS antes de totais e filtros.';
REVOKE ALL ON public.v_fim_relacionamento_liga
    FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_fim_relacionamento_liga TO service_role;

CREATE OR REPLACE FUNCTION public.fn_importar_fim_relacionamento_liga(
    p_periodo_id UUID,
    p_rows JSONB
)
RETURNS TABLE (
    removidos INTEGER,
    inseridos INTEGER,
    contabilizadas INTEGER,
    sem_loja INTEGER,
    sem_consultor INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_row JSONB;
    v_loja_id UUID;
    v_consultor_id UUID;
    v_consultor_nome TEXT;
    v_removidos INTEGER := 0;
    v_inseridos INTEGER := 0;
    v_contabilizadas INTEGER := 0;
    v_sem_loja INTEGER := 0;
    v_sem_consultor INTEGER := 0;
BEGIN
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'p_rows deve ser uma lista JSON.';
    END IF;
    IF jsonb_array_length(p_rows) = 0 THEN
        RAISE EXCEPTION 'Nenhuma linha valida de Fim de relacionamento. Carga abortada.';
    END IF;

    -- Mesmo periodo nao pode ser substituido por duas cargas concorrentes.
    -- A trava vale ate o commit/rollback e tambem protege a existencia do FK.
    PERFORM 1 FROM public.periodos p WHERE p.id = p_periodo_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Periodo % inexistente.', p_periodo_id;
    END IF;

    -- Valida TODO o lote antes de qualquer DELETE. Casts tambem rejeitam
    -- overflow de identificador/codigo e datas impossiveis (31/02, etc.).
    FOR v_row IN SELECT e.value FROM jsonb_array_elements(p_rows) AS e
    LOOP
        IF jsonb_typeof(v_row) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'Cada linha de p_rows deve ser um objeto JSON.';
        END IF;
        IF COALESCE(v_row->>'co_adesao', '') !~ '^[0-9]+$'
            OR COALESCE(v_row->>'qtde', '') NOT IN ('0', '1')
        THEN
            RAISE EXCEPTION 'Adesao invalida ou qtde diferente de 0/1.';
        END IF;
        IF (v_row->>'co_adesao')::BIGINT <= 0 THEN
            RAISE EXCEPTION 'Adesao deve ser um inteiro positivo.';
        END IF;
        IF COALESCE(v_row->>'data_contrato', '') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            OR COALESCE(v_row->>'data_fim_relacionamento', '') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        THEN
            RAISE EXCEPTION 'Data Contrato e Data Fim Relacionamento devem ser datas ISO validas.';
        END IF;
        PERFORM (v_row->>'data_contrato')::DATE,
                (v_row->>'data_fim_relacionamento')::DATE;
        IF v_row->>'cod_bmg' IS NOT NULL THEN
            IF (v_row->>'cod_bmg') !~ '^[0-9]+$' THEN
                RAISE EXCEPTION 'cod_bmg deve ser um inteiro positivo ou null.';
            END IF;
            IF (v_row->>'cod_bmg')::INTEGER <= 0 THEN
                RAISE EXCEPTION 'cod_bmg deve ser um inteiro positivo ou null.';
            END IF;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS e
        GROUP BY (e.value->>'co_adesao')::BIGINT HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Adesao duplicada em Fim de relacionamento. Carga abortada.';
    END IF;

    DELETE FROM public.fim_relacionamento_liga f
    WHERE f.periodo_id = p_periodo_id;
    GET DIAGNOSTICS v_removidos = ROW_COUNT;

    FOR v_row IN SELECT e.value FROM jsonb_array_elements(p_rows) AS e
    LOOP
        v_loja_id := NULL;
        SELECT COALESCE(l.sucessora_id, l.id) INTO v_loja_id
        FROM public.lojas l
        WHERE l.cod_bmg = (v_row->>'cod_bmg')::INTEGER
        ORDER BY l.id LIMIT 1;

        v_consultor_id := NULL;
        v_consultor_nome := NULLIF(btrim(v_row->>'consultor_nome'), '');
        IF v_consultor_nome IS NOT NULL THEN
            SELECT c.id INTO v_consultor_id FROM public.consultores c
            WHERE lower(c.nome) = lower(v_consultor_nome)
              AND (c.loja_id = v_loja_id OR c.loja_id IS NULL)
            ORDER BY CASE WHEN c.loja_id = v_loja_id THEN 0 ELSE 1 END,
                     c.nome, c.id
            LIMIT 1;
        END IF;

        INSERT INTO public.fim_relacionamento_liga (
            periodo_id, co_adesao, qtde, data_contrato,
            data_fim_relacionamento, franqueado, no_franquia,
            cod_bmg, loja_id, consultor_nome, consultor_id
        ) VALUES (
            p_periodo_id, (v_row->>'co_adesao')::BIGINT,
            (v_row->>'qtde')::INTEGER, (v_row->>'data_contrato')::DATE,
            (v_row->>'data_fim_relacionamento')::DATE,
            NULLIF(btrim(v_row->>'franqueado'), ''),
            NULLIF(btrim(v_row->>'no_franquia'), ''),
            (v_row->>'cod_bmg')::INTEGER, v_loja_id,
            v_consultor_nome, v_consultor_id
        );
        v_inseridos := v_inseridos + 1;
        v_contabilizadas := v_contabilizadas + (v_row->>'qtde')::INTEGER;
        IF v_loja_id IS NULL THEN v_sem_loja := v_sem_loja + 1; END IF;
        IF v_consultor_id IS NULL THEN
            v_sem_consultor := v_sem_consultor + 1;
        END IF;
    END LOOP;

    RETURN QUERY SELECT v_removidos, v_inseridos, v_contabilizadas,
                        v_sem_loja, v_sem_consultor;
END;
$$;

COMMENT ON FUNCTION public.fn_importar_fim_relacionamento_liga(UUID, JSONB) IS
    'Valida lote completo, serializa pela competencia e substitui somente '
    'o periodo em uma transacao. Resolve loja por cod_bmg/sucessora e '
    'consultor por nome exato sem diferenca de caixa + loja; preserva origem.';
REVOKE EXECUTE ON FUNCTION public.fn_importar_fim_relacionamento_liga(UUID, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_importar_fim_relacionamento_liga(UUID, JSONB)
    TO service_role;

-- VALIDACAO POS-MIGRATION (executar separadamente; sempre ROLLBACK).
-- O bloco abaixo usa um periodo existente, substitui SO dentro da
-- transacao de teste e restaura tudo ao final. Nao compoe o deploy.
/* FDR_VALIDATION_BEGIN
BEGIN;
DO $test$
DECLARE
    v_periodo UUID;
    v_rows JSONB := '[
      {"co_adesao": 900000001, "qtde": 1,
       "data_contrato": "2026-07-01", "data_fim_relacionamento": "2026-08-16"},
      {"co_adesao": 900000002, "qtde": 0,
       "data_contrato": "2026-09-01", "data_fim_relacionamento": "2026-10-18"}
    ]'::JSONB;
    v_bad JSONB;
    v_result RECORD;
    v_outros BIGINT;
    v_falhou BOOLEAN;
BEGIN
    SELECT p.id INTO STRICT v_periodo FROM public.periodos p
    ORDER BY p.ano DESC, p.mes DESC LIMIT 1;
    SELECT count(*) INTO v_outros FROM public.fim_relacionamento_liga f
    WHERE f.periodo_id <> v_periodo;

    SELECT * INTO v_result
    FROM public.fn_importar_fim_relacionamento_liga(v_periodo, v_rows);
    IF v_result.inseridos <> 2 OR v_result.contabilizadas <> 1 THEN
        RAISE EXCEPTION 'Carga inicial nao preservou quantidade 0/1.';
    END IF;
    SELECT * INTO v_result
    FROM public.fn_importar_fim_relacionamento_liga(v_periodo, v_rows);
    IF v_result.removidos <> 2 OR v_result.inseridos <> 2 THEN
        RAISE EXCEPTION 'Reimportacao nao foi idempotente por periodo.';
    END IF;
    IF (SELECT count(*) FROM public.fim_relacionamento_liga f
        WHERE f.periodo_id <> v_periodo) <> v_outros THEN
        RAISE EXCEPTION 'Outra competencia foi alterada.';
    END IF;

    -- Cada erro esperado roda numa subtransacao; captura apenas a RPC,
    -- nunca o proprio assert, e verifica que a foto anterior ficou intacta.
    FOR v_bad IN SELECT x FROM (VALUES
        ('[]'::JSONB),
        ('null'::JSONB),
        ('[null]'::JSONB),
        (v_rows || jsonb_build_array(v_rows->0)),
        (jsonb_set(v_rows, '{0,qtde}', '2'::JSONB)),
        (jsonb_set(v_rows, '{0,co_adesao}', '0'::JSONB)),
        (jsonb_set(v_rows, '{0,data_contrato}', '"2026-02-31"'::JSONB)),
        (jsonb_set(v_rows, '{0,cod_bmg}', '"abc"'::JSONB))
    ) AS invalidos(x)
    LOOP
        v_falhou := false;
        BEGIN
            PERFORM public.fn_importar_fim_relacionamento_liga(v_periodo, v_bad);
        EXCEPTION WHEN OTHERS THEN
            v_falhou := true;
        END;
        IF NOT v_falhou THEN RAISE EXCEPTION 'Lote invalido aceito: %', v_bad; END IF;
        IF (SELECT count(*) FROM public.fim_relacionamento_liga f
            WHERE f.periodo_id = v_periodo) <> 2 THEN
            RAISE EXCEPTION 'Falha alterou a foto anterior.';
        END IF;
    END LOOP;

    IF has_table_privilege('anon', 'public.fim_relacionamento_liga', 'SELECT')
       OR has_table_privilege('authenticated', 'public.v_fim_relacionamento_liga', 'SELECT')
       OR has_function_privilege('anon',
          'public.fn_importar_fim_relacionamento_liga(uuid,jsonb)', 'EXECUTE')
       OR has_function_privilege('authenticated',
          'public.fn_importar_fim_relacionamento_liga(uuid,jsonb)', 'EXECUTE')
       OR NOT has_function_privilege('service_role',
          'public.fn_importar_fim_relacionamento_liga(uuid,jsonb)', 'EXECUTE')
    THEN RAISE EXCEPTION 'Permissoes de FDR Liga incorretas.'; END IF;
    IF NOT (SELECT c.relrowsecurity FROM pg_class c
            WHERE c.oid = 'public.fim_relacionamento_liga'::regclass) THEN
        RAISE EXCEPTION 'RLS nao habilitada.';
    END IF;
END;
$test$;
ROLLBACK;
FDR_VALIDATION_END */
