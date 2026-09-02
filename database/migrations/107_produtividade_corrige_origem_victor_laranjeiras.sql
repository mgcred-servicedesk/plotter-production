-- =====================================================
-- Migracao 107: origem do contrato de Victor em Laranjeiras
-- Data: 2026-09-02
-- Depende de: 105 (validacao da origem) e 106 (reatribuicao Patricia)
--
-- Fato confirmado pela operacao:
--   * VICTOR FELIPE TRAJANO COSTA permaneceu em HELP LARANJEIRAS ate
--     03/08/2026;
--   * em 04/08/2026 passou para HELP COPACABANA NOVA;
--   * a ADE 978537400 foi cadastrada em 20/07/2026 e paga em 04/08/2026.
--
-- Logo, trata-se de pagamento posterior a transferencia: o contrato nasceu
-- em Laranjeiras e precisa conservar essa origem, embora o pagamento tenha
-- ocorrido no primeiro dia de Victor em Copacabana Nova.
-- =====================================================

BEGIN;

LOCK TABLE public.contratos IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_laranjeiras_id UUID;
    v_copacabana_nova_id UUID;
    v_victor_laranjeiras_id UUID;
    v_victor_copacabana_nova_id UUID;
    v_quantidade INTEGER;
    v_atualizadas INTEGER;
    v_valor_antes NUMERIC;
    v_valor_depois NUMERIC;
    v_contrato RECORD;
BEGIN
    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_laranjeiras_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP LARANJEIRAS';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 107: HELP LARANJEIRAS ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(l.id))[1]
      INTO v_quantidade, v_copacabana_nova_id
      FROM public.lojas l
     WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
           'HELP COPACABANA NOVA';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 107: HELP COPACABANA NOVA ausente ou ambigua (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(c.id))[1]
      INTO v_quantidade, v_victor_laranjeiras_id
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) =
           'VICTOR FELIPE TRAJANO COSTA'
       AND c.loja_id = v_laranjeiras_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 107: cadastro de Victor em Laranjeiras ausente ou ambiguo (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*), (array_agg(c.id))[1]
      INTO v_quantidade, v_victor_copacabana_nova_id
      FROM public.consultores c
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) =
           'VICTOR FELIPE TRAJANO COSTA'
       AND c.loja_id = v_copacabana_nova_id;

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 107: cadastro de Victor em Copacabana Nova ausente ou ambiguo (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = 'VICTOR FELIPE TRAJANO COSTA'
       AND v.loja_id = v_laranjeiras_id
       AND v.vigencia_inicio <= DATE '2026-07-20'
       AND v.vigencia_fim = DATE '2026-08-04';

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 107: vigencia confirmada de Victor em Laranjeiras nao encontrada (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT count(*)::integer
      INTO v_quantidade
      FROM public.consultor_vigencia v
     WHERE v.nome_normalizado = 'VICTOR FELIPE TRAJANO COSTA'
       AND v.loja_id = v_copacabana_nova_id
       AND v.vigencia_inicio = DATE '2026-08-04'
       AND (v.vigencia_fim IS NULL OR v.vigencia_fim > DATE '2026-08-04');

    IF v_quantidade <> 1 THEN
        RAISE EXCEPTION
            'Migration 107: vigencia de Victor em Copacabana Nova em 04/08 nao encontrada (% correspondencias)',
            v_quantidade;
    END IF;

    SELECT
        c.id,
        c.contrato_id,
        c.num_proposta,
        c.loja_id,
        c.consultor_id,
        c.data_cadastro,
        c.data_status_pagamento,
        c.valor
      INTO v_contrato
      FROM public.contratos c
     WHERE c.contrato_id = 2987344;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Migration 107: contrato 2987344 / ADE 978537400 ausente';
    END IF;

    IF v_contrato.num_proposta IS DISTINCT FROM '978537400'
       OR v_contrato.data_cadastro IS DISTINCT FROM DATE '2026-07-20'
       OR v_contrato.data_status_pagamento IS DISTINCT FROM DATE '2026-08-04'
       OR NOT (
           (v_contrato.loja_id = v_copacabana_nova_id
            AND v_contrato.consultor_id = v_victor_copacabana_nova_id)
           OR
           (v_contrato.loja_id = v_laranjeiras_id
            AND v_contrato.consultor_id = v_victor_laranjeiras_id)
       ) THEN
        RAISE EXCEPTION
            'Migration 107: contrato divergente; nenhuma alteracao aplicada (ade=%, cadastro=%, pagamento=%, loja=%, consultor=%)',
            v_contrato.num_proposta,
            v_contrato.data_cadastro,
            v_contrato.data_status_pagamento,
            v_contrato.loja_id,
            v_contrato.consultor_id;
    END IF;

    v_valor_antes := v_contrato.valor;

    UPDATE public.contratos c
       SET loja_id = v_laranjeiras_id,
           consultor_id = v_victor_laranjeiras_id
     WHERE c.contrato_id = 2987344
       AND c.num_proposta = '978537400'
       AND c.loja_id = v_copacabana_nova_id
       AND c.consultor_id = v_victor_copacabana_nova_id;

    GET DIAGNOSTICS v_atualizadas = ROW_COUNT;

    -- Primeira execucao altera uma linha; repeticao integral e um no-op.
    IF v_atualizadas NOT IN (0, 1) THEN
        RAISE EXCEPTION
            'Migration 107: quantidade inesperada de linhas atualizadas (%)',
            v_atualizadas;
    END IF;

    SELECT c.valor
      INTO v_valor_depois
      FROM public.contratos c
     WHERE c.contrato_id = 2987344
       AND c.num_proposta = '978537400'
       AND c.loja_id = v_laranjeiras_id
       AND c.consultor_id = v_victor_laranjeiras_id
       AND c.data_cadastro = DATE '2026-07-20'
       AND c.data_status_pagamento = DATE '2026-08-04';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Migration 107: pos-condicao falhou para contrato 2987344';
    END IF;

    IF v_valor_depois IS DISTINCT FROM v_valor_antes THEN
        RAISE EXCEPTION
            'Migration 107: valor do contrato mudou de % para %',
            v_valor_antes, v_valor_depois;
    END IF;
END
$$;

COMMIT;

-- Verificacao operacional depois de aplicar 106 e 107:
--
-- SELECT public.fn_contar_pagamentos_sem_vinculo_origem(8, 2026);
-- -- esperado: 0
--
-- SELECT
--     v.contrato_id,
--     v.num_proposta,
--     v.consultor,
--     v.loja,
--     v.data_cadastro,
--     v.data_status_pagamento,
--     v.valor_consolidado
-- FROM public.v_contratos_dashboard v
-- WHERE v.contrato_id = 2987344;
-- -- esperado: 2987344 | 978537400 | VICTOR FELIPE TRAJANO COSTA |
-- --           HELP LARANJEIRAS | 2026-07-20 | 2026-08-04 | 705.98
