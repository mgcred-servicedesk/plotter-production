-- =====================================================
-- Migracao 104: admissao confirmada de Iluara
-- Data: 2026-09-02
-- Depende de: 087 (consultor_vigencia diaria)
--
-- Fato confirmado pela operacao:
--   * ILUARA BORGES CABRAL;
--   * HELP CASCADURA;
--   * admissao em 25/08/2026.
--
-- Esta migracao nao corrige contratos. Os contratos pagos de 18/08 que hoje
-- apontam para o cadastro de Iluara precisam voltar aos donos verdadeiros;
-- ampliar a vigencia para 18/08 esconderia a divergencia.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_nome CONSTANT TEXT := 'ILUARA BORGES CABRAL';
    v_nn CONSTANT TEXT := 'ILUARA BORGES CABRAL';
    v_admissao CONSTANT DATE := DATE '2026-08-25';
    v_loja_id UUID;
    v_quantidade INTEGER;
    v_conflitos TEXT;
BEGIN
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_loja_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP CASCADURA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 104: HELP CASCADURA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

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
       AND coalesce(v.vigencia_fim, DATE '9999-12-31') > v_admissao
       AND NOT (
           v.loja_id = v_loja_id
           AND v.vigencia_fim IS NULL
           AND v.vigencia_inicio >= v_admissao
       );

    IF v_conflitos IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 104: vigencia conflitante de Iluara; revisar antes de aplicar: %',
            v_conflitos;
    END IF;

    UPDATE public.consultor_vigencia v
       SET nome = v_nome,
           vigencia_inicio = v_admissao,
           origem = 'MANUAL'
     WHERE v.nome_normalizado = v_nn
       AND v.loja_id = v_loja_id
       AND v.vigencia_fim IS NULL
       AND v.vigencia_inicio >= v_admissao;

    IF NOT FOUND THEN
        INSERT INTO public.consultor_vigencia (
            nome, loja_id, vigencia_inicio, vigencia_fim, origem
        ) VALUES (
            v_nome, v_loja_id, v_admissao, NULL, 'MANUAL'
        );
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = v_nn
       AND v.loja_id = v_loja_id
       AND v.vigencia_inicio = v_admissao
       AND v.vigencia_fim IS NULL
       AND v.origem = 'MANUAL';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 104: pos-condicao de Iluara falhou (% linhas corretas)',
            v_quantidade;
    END IF;
END
$$;

COMMIT;

-- Verificacao operacional:
-- SELECT v.nome, l.nome AS loja, v.vigencia_inicio, v.vigencia_fim, v.origem
-- FROM public.consultor_vigencia v
-- LEFT JOIN public.lojas l ON l.id = v.loja_id
-- WHERE v.nome_normalizado = 'ILUARA BORGES CABRAL';
