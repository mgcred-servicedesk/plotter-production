-- ============================================================
-- Migracao 023: RPC fn_lojas_sucessao_apply
--
-- Aplica em lote a sucessao de lojas (PDV → HELP herdeira).
-- Para cada par {predecessora_cod_bmg, sucessora_cod_bmg}:
--   - resolve as duas lojas por cod_bmg;
--   - marca predecessora.ativo = false;
--   - seta predecessora.sucessora_id = sucessora.id.
--
-- Idempotente: rodar duas vezes nao cria efeito colateral.
-- Retorna contadores para o angry-man exibir resumo.
--
-- Validacoes:
--   - predecessora deve existir (cod_bmg cadastrado)
--   - sucessora deve existir (cod_bmg cadastrado)
--   - predecessora ≠ sucessora
--
-- Depende de: 021_lojas_sucessao.sql
-- ============================================================

CREATE OR REPLACE FUNCTION fn_lojas_sucessao_apply(
    p_pares JSONB
)
RETURNS TABLE (
    aplicados        INTEGER,
    sem_predecessora INTEGER,
    sem_sucessora    INTEGER,
    invalidos        INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
/*
Schema esperado para cada objeto em p_pares:
{
    "predecessora_cod_bmg": 51463,
    "sucessora_cod_bmg":    56436
}
*/
DECLARE
    v_aplicados        INTEGER := 0;
    v_sem_pred         INTEGER := 0;
    v_sem_suc          INTEGER := 0;
    v_invalidos        INTEGER := 0;
    v_row              JSONB;
    v_pred_cod_bmg     INTEGER;
    v_suc_cod_bmg      INTEGER;
    v_pred_id          UUID;
    v_suc_id           UUID;
BEGIN
    FOR v_row IN SELECT * FROM jsonb_array_elements(p_pares)
    LOOP
        v_pred_cod_bmg := (v_row->>'predecessora_cod_bmg')::INTEGER;
        v_suc_cod_bmg  := (v_row->>'sucessora_cod_bmg')::INTEGER;

        IF v_pred_cod_bmg IS NULL OR v_suc_cod_bmg IS NULL
           OR v_pred_cod_bmg = v_suc_cod_bmg THEN
            v_invalidos := v_invalidos + 1;
            CONTINUE;
        END IF;

        SELECT id INTO v_pred_id
        FROM public.lojas
        WHERE cod_bmg = v_pred_cod_bmg
        LIMIT 1;

        IF v_pred_id IS NULL THEN
            v_sem_pred := v_sem_pred + 1;
            CONTINUE;
        END IF;

        SELECT id INTO v_suc_id
        FROM public.lojas
        WHERE cod_bmg = v_suc_cod_bmg
        LIMIT 1;

        IF v_suc_id IS NULL THEN
            v_sem_suc := v_sem_suc + 1;
            CONTINUE;
        END IF;

        UPDATE public.lojas
        SET ativo        = false,
            sucessora_id = v_suc_id,
            updated_at   = now()
        WHERE id = v_pred_id;

        v_aplicados := v_aplicados + 1;
    END LOOP;

    RETURN QUERY SELECT v_aplicados, v_sem_pred, v_sem_suc, v_invalidos;
END;
$$;

COMMENT ON FUNCTION fn_lojas_sucessao_apply IS
    'Aplica sucessao de lojas em lote. Para cada par '
    '{predecessora_cod_bmg, sucessora_cod_bmg}: marca a '
    'predecessora como inativa e seta a sucessora. Idempotente. '
    'Chamada pelo angry-man (import "Sucessao de Lojas").';

REVOKE ALL ON FUNCTION fn_lojas_sucessao_apply FROM PUBLIC;
