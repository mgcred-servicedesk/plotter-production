-- =====================================================
-- Migracao 106: reatribuicao da producao indicada para Iluara
-- Data: 2026-09-02
-- Depende de: 104 (admissao de Iluara) e 105 (validacao da origem)
--
-- Fato confirmado pela operacao:
--   * as 17 propostas foram digitadas por PATRICIA PEREIRA LOPES;
--   * posteriormente a producao foi indicada para ILUARA BORGES CABRAL;
--   * Iluara so foi admitida em 25/08/2026, depois dessas propostas;
--   * para preservar a historia, as propostas voltam para Patricia;
--   * a loja continua HELP CASCADURA.
--
-- Patricia era supervisora na competencia. Pelas regras do Caderno, sua
-- producao permanece no total da loja (`paidEffective`), mas nao entra no
-- numerador nem nos rankings de consultores (`paidByConsultants`).
-- =====================================================

BEGIN;

LOCK TABLE public.contratos IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_loja_id UUID;
    v_patricia_id UUID;
    v_iluara_id UUID;
    v_quantidade INTEGER;
    v_atualizadas INTEGER;
    v_total_antes NUMERIC;
    v_total_depois NUMERIC;
    v_incorretas TEXT;
BEGIN
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_loja_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP CASCADURA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 106: HELP CASCADURA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(c.id))[1]
      INTO v_quantidade, v_patricia_id
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) =
           'PATRICIA PEREIRA LOPES'
       AND c.loja_id = v_loja_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 106: cadastro de Patricia em Cascadura ausente ou ambiguo (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(c.id))[1]
      INTO v_quantidade, v_iluara_id
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) =
           'ILUARA BORGES CABRAL'
       AND c.loja_id = v_loja_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 106: cadastro de Iluara em Cascadura ausente ou ambiguo (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.supervisor_vigencia s
     WHERE s.nome_normalizado = 'PATRICIA PEREIRA LOPES'
       AND s.vigencia_inicio <= DATE '2026-08-31'
       AND (s.vigencia_fim IS NULL OR s.vigencia_fim > DATE '2026-08-31');

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 106: Patricia nao possui uma unica vigencia de supervisao em 31/08/2026 (% correspondencias)',
            v_quantidade;
    END IF;

    WITH esperadas(contrato_id, ade) AS (
        VALUES
            (2995893, '10346657'),
            (2995895, '10347633'),
            (2995896, '10347640'),
            (2995897, '10347663'),
            (2995898, '10348604'),
            (2995900, '10348890'),
            (2995901, '10349131'),
            (2995902, '10351292'),
            (2995904, '10352601'),
            (2995905, '10353343'),
            (2995908, '10359687'),
            (2995909, '10359727'),
            (2995913, '10361322'),
            (2996591, '10351824'),
            (2996592, '10353445'),
            (2996593, '10353882'),
            (2996595, '10362208')
    )
    SELECT string_agg(
               format(
                   'contrato=%s ade_esperada=%s ade_atual=%s loja=%s consultor=%s data=%s',
                   e.contrato_id,
                   e.ade,
                   coalesce(c.num_proposta, '<ausente>'),
                   coalesce(c.loja_id::text, '<ausente>'),
                   coalesce(c.consultor_id::text, '<ausente>'),
                   coalesce(c.data_cadastro::text, '<ausente>')
               ),
               '; ' ORDER BY e.contrato_id
           )
      INTO v_incorretas
      FROM esperadas e
      LEFT JOIN public.contratos c ON c.contrato_id = e.contrato_id
     WHERE c.id IS NULL
        OR c.num_proposta IS DISTINCT FROM e.ade
        OR c.loja_id IS DISTINCT FROM v_loja_id
        OR c.data_cadastro IS DISTINCT FROM DATE '2026-08-18'
        OR c.consultor_id NOT IN (v_iluara_id, v_patricia_id);

    IF v_incorretas IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 106: propostas ausentes ou divergentes; nenhuma alteracao aplicada: %',
            v_incorretas;
    END IF;

    SELECT coalesce(sum(c.valor), 0)
      INTO v_total_antes
      FROM public.contratos c
     WHERE c.contrato_id = ANY (ARRAY[
         2995893, 2995895, 2995896, 2995897, 2995898, 2995900,
         2995901, 2995902, 2995904, 2995905, 2995908, 2995909,
         2995913, 2996591, 2996592, 2996593, 2996595
     ]::BIGINT[]);

    UPDATE public.contratos c
       SET consultor_id = v_patricia_id
     WHERE c.contrato_id = ANY (ARRAY[
         2995893, 2995895, 2995896, 2995897, 2995898, 2995900,
         2995901, 2995902, 2995904, 2995905, 2995908, 2995909,
         2995913, 2996591, 2996592, 2996593, 2996595
     ]::BIGINT[])
       AND c.loja_id = v_loja_id
       AND c.consultor_id = v_iluara_id;

    GET DIAGNOSTICS v_atualizadas = ROW_COUNT;

    -- Primeira execucao altera 17 linhas; repeticao integral e um no-op.
    IF v_atualizadas NOT IN (0, 17) THEN
        RAISE EXCEPTION
            'Migration 106: estado parcial inesperado (% de 17 linhas atualizadas)',
            v_atualizadas;
    END IF;

    SELECT count(*)::integer, coalesce(sum(c.valor), 0)
      INTO v_quantidade, v_total_depois
      FROM public.contratos c
     WHERE c.contrato_id = ANY (ARRAY[
         2995893, 2995895, 2995896, 2995897, 2995898, 2995900,
         2995901, 2995902, 2995904, 2995905, 2995908, 2995909,
         2995913, 2996591, 2996592, 2996593, 2996595
     ]::BIGINT[])
       AND c.loja_id = v_loja_id
       AND c.consultor_id = v_patricia_id;

    IF v_quantidade <> 17 THEN
        RAISE EXCEPTION
            'Migration 106: pos-condicao falhou (% de 17 propostas em Patricia/Cascadura)',
            v_quantidade;
    END IF;

    IF v_total_depois IS DISTINCT FROM v_total_antes THEN
        RAISE EXCEPTION
            'Migration 106: total das propostas mudou de % para %',
            v_total_antes, v_total_depois;
    END IF;
END
$$;

COMMIT;

-- Verificacao operacional depois da aplicacao:
--
-- SELECT public.fn_contar_pagamentos_sem_vinculo_origem(8, 2026);
-- -- esperado: 1, enquanto o contrato 2987344 de Victor/Copacabana Nova
-- -- ainda estiver com a loja posterior a sua data de cadastro.
--
-- SELECT
--     v.consultor,
--     v.loja,
--     count(*) AS contratos,
--     sum(v.valor_consolidado) AS pago
-- FROM public.v_contratos_dashboard v
-- WHERE v.contrato_id = ANY (ARRAY[
--     2995893, 2995895, 2995896, 2995897, 2995898, 2995900,
--     2995901, 2995902, 2995904, 2995905, 2995908, 2995909,
--     2995913, 2996591, 2996592, 2996593, 2996595
-- ]::BIGINT[])
-- GROUP BY v.consultor, v.loja;
-- -- esperado: PATRICIA PEREIRA LOPES | HELP CASCADURA | 17 | 14221.48
