-- =====================================================
-- Migracao 103: cobertura temporaria de Mizael em Rio Comprido
-- Data: 2026-09-01
-- Depende de: 087 (consultor_vigencia diaria)
--
-- Fato confirmado pela operacao:
--   * loja de origem: HELP LARANJEIRAS;
--   * cobertura na HELP RIO COMPRIDO: 11/08/2026 a 24/08/2026;
--   * retorno a HELP LARANJEIRAS: 25/08/2026.
--
-- As janelas usam o intervalo semiaberto [inicio, fim). Portanto, o fim
-- 25/08 na linha de Rio Comprido significa que 24/08 foi o ultimo dia la.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_nn CONSTANT TEXT := 'MIZAEL BARBOSA NETO';
    v_inicio_rio CONSTANT DATE := DATE '2026-08-11';
    v_retorno_laranjeiras CONSTANT DATE := DATE '2026-08-25';
    v_laranjeiras_id UUID;
    v_rio_id UUID;
    v_quantidade INTEGER;
    v_linha_anterior_id UUID;
    v_linha_rio_id UUID;
    v_linha_retorno_id UUID;
    v_conflitos TEXT;
    v_incorretas TEXT;
BEGIN
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_laranjeiras_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP LARANJEIRAS';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 103: HELP LARANJEIRAS ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_rio_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP RIO COMPRIDO';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 103: HELP RIO COMPRIDO ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    -- A janela de origem que alcançava 11/08 precisa ser unica. Na
    -- reaplicacao, ela ja termina exatamente em 11/08 e continua valida.
    SELECT count(*), (array_agg(v.id ORDER BY v.vigencia_inicio))[1]
      INTO v_quantidade, v_linha_anterior_id
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nn
       AND v.loja_id = v_laranjeiras_id
       AND v.vigencia_inicio < v_inicio_rio
       AND coalesce(v.vigencia_fim, DATE '9999-12-31') >= v_inicio_rio;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 103: esperado um unico vinculo anterior de Mizael em Laranjeiras; encontrados %',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(v.id ORDER BY v.vigencia_inicio))[1]
      INTO v_quantidade, v_linha_rio_id
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nn
       AND v.loja_id = v_rio_id
       AND v.vigencia_inicio >= v_inicio_rio;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 103: mais de uma janela de Mizael em Rio Comprido apos 11/08 (%)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(v.id ORDER BY v.vigencia_inicio))[1]
      INTO v_quantidade, v_linha_retorno_id
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nn
       AND v.loja_id = v_laranjeiras_id
       AND v.vigencia_inicio >= v_retorno_laranjeiras;

    IF v_quantidade > 1 THEN
        RAISE EXCEPTION
            'Migration 103: mais de uma janela de retorno de Mizael a Laranjeiras (%)',
            v_quantidade;
    END IF;

    -- Depois de 11/08, so podem existir as linhas que serao transformadas na
    -- cobertura temporaria e no retorno. Outro historico exige revisao humana.
    SELECT string_agg(
               format('%s [%s, %s)',
                      coalesce(l.nome, '<sem loja>'),
                      v.vigencia_inicio,
                      coalesce(v.vigencia_fim::text, 'aberta')),
               '; ' ORDER BY v.vigencia_inicio
           )
      INTO v_conflitos
      FROM public.consultor_vigencia v
      LEFT JOIN public.lojas l ON l.id = v.loja_id
     WHERE v.nome_normalizado = v_nn
       AND coalesce(v.vigencia_fim, DATE '9999-12-31') > v_inicio_rio
       AND v.id <> v_linha_anterior_id
       AND (v_linha_rio_id IS NULL OR v.id <> v_linha_rio_id)
       AND (v_linha_retorno_id IS NULL OR v.id <> v_linha_retorno_id);

    IF v_conflitos IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 103: vigencia conflitante de Mizael; revisar antes de aplicar: %',
            v_conflitos;
    END IF;

    UPDATE public.consultor_vigencia
       SET vigencia_fim = v_inicio_rio,
           origem = 'MANUAL'
     WHERE id = v_linha_anterior_id;

    IF v_linha_rio_id IS NULL THEN
        INSERT INTO public.consultor_vigencia (
            nome, loja_id, vigencia_inicio, vigencia_fim, origem
        ) VALUES (
            'MIZAEL BARBOSA NETO', v_rio_id,
            v_inicio_rio, v_retorno_laranjeiras, 'MANUAL'
        )
        RETURNING id INTO v_linha_rio_id;
    ELSE
        UPDATE public.consultor_vigencia
           SET nome = 'MIZAEL BARBOSA NETO',
               vigencia_inicio = v_inicio_rio,
               vigencia_fim = v_retorno_laranjeiras,
               origem = 'MANUAL'
         WHERE id = v_linha_rio_id;
    END IF;

    IF v_linha_retorno_id IS NULL THEN
        INSERT INTO public.consultor_vigencia (
            nome, loja_id, vigencia_inicio, vigencia_fim, origem
        ) VALUES (
            'MIZAEL BARBOSA NETO', v_laranjeiras_id,
            v_retorno_laranjeiras, NULL, 'MANUAL'
        )
        RETURNING id INTO v_linha_retorno_id;
    ELSE
        UPDATE public.consultor_vigencia
           SET nome = 'MIZAEL BARBOSA NETO',
               vigencia_inicio = v_retorno_laranjeiras,
               vigencia_fim = NULL,
               origem = 'MANUAL'
         WHERE id = v_linha_retorno_id;
    END IF;

    WITH esperado(loja_id, inicio, fim) AS (
        VALUES
            (v_rio_id, v_inicio_rio, v_retorno_laranjeiras),
            (v_laranjeiras_id, v_retorno_laranjeiras, NULL::date)
    ),
    contagem AS (
        SELECT
            e.loja_id,
            e.inicio,
            e.fim,
            count(v.id) AS quantidade
        FROM esperado e
        LEFT JOIN public.consultor_vigencia v
          ON v.nome_normalizado = v_nn
         AND v.loja_id = e.loja_id
         AND v.vigencia_inicio = e.inicio
         AND v.vigencia_fim IS NOT DISTINCT FROM e.fim
         AND v.origem = 'MANUAL'
        GROUP BY e.loja_id, e.inicio, e.fim
    )
    SELECT string_agg(
               format('%s [%s, %s): %s linha(s)',
                      l.nome, c.inicio,
                      coalesce(c.fim::text, 'aberta'), c.quantidade),
               '; '
           )
      INTO v_incorretas
      FROM contagem c
      JOIN public.lojas l ON l.id = c.loja_id
     WHERE c.quantidade <> 1;

    IF v_incorretas IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 103: pos-condicao da cobertura falhou: %', v_incorretas;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.consultor_vigencia v
        WHERE v.id = v_linha_anterior_id
          AND (v.vigencia_fim <> v_inicio_rio OR v.origem <> 'MANUAL')
    ) THEN
        RAISE EXCEPTION
            'Migration 103: vinculo anterior de Laranjeiras nao terminou em 11/08';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.consultor_vigencia a
        JOIN public.consultor_vigencia b
          ON a.nome_normalizado = b.nome_normalizado
         AND a.id < b.id
         AND a.vigencia_inicio < coalesce(b.vigencia_fim, DATE '9999-12-31')
         AND coalesce(a.vigencia_fim, DATE '9999-12-31') > b.vigencia_inicio
        WHERE a.nome_normalizado = v_nn
    ) THEN
        RAISE EXCEPTION
            'Migration 103: sobreposicao de vigencias de Mizael apos a correcao';
    END IF;
END
$$;

COMMIT;

-- Verificacao operacional:
-- SELECT v.nome, l.nome AS loja, v.vigencia_inicio, v.vigencia_fim, v.origem
-- FROM public.consultor_vigencia v
-- LEFT JOIN public.lojas l ON l.id = v.loja_id
-- WHERE v.nome_normalizado = 'MIZAEL BARBOSA NETO'
-- ORDER BY v.vigencia_inicio;
