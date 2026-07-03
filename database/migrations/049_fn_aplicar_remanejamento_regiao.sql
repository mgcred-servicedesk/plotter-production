-- =====================================================
-- Migracao 049: fn_aplicar_remanejamento_regiao
--               (aplica troca de regiao de uma loja, versionada)
--
-- Estagio 3. Operacao ATOMICA que remaneja UMA loja para uma nova
-- regiao a partir de uma data efetiva, mantendo a invariante do
-- ledger loja_regiao_vigencia (043):
--   1. fecha a linha de vigencia ABERTA (vigencia_fim := data_efetiva);
--   2. abre uma nova linha aberta (vigencia_inicio := data_efetiva)
--      com a regiao nova;
--   3. atualiza lojas.regiao_id (ponteiro do organograma atual).
--
-- Tudo dentro da funcao plpgsql => 1 transacao (ou aplica os 3 passos
-- ou nenhum). Idempotente: se a loja ja esta na regiao nova, e no-op.
--
-- Uso previsto:
--   * o script de remanejamento H2/2026 (migration 050) chama esta
--     funcao 1x por loja alterada;
--   * futuramente o angry-man chama esta funcao ao detectar troca de
--     regiao no import de loja_regiao, em vez de sobrescrever
--     lojas.regiao_id direto (senao a linha aberta desincroniza do
--     ponteiro atual e o point-in-time corrompe silenciosamente).
--
-- Seguranca: funcao de ESCRITA. EXECUTE revogado de PUBLIC/anon/
-- authenticated — so roda via service_role (angry-man) ou owner
-- (SQL Editor). Mesmo racional das migrations 009/010.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE OR REPLACE FUNCTION fn_aplicar_remanejamento_regiao(
    p_loja_nome    TEXT,
    p_regiao_nova  TEXT,
    p_data_efetiva DATE
)
RETURNS TEXT
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v_loja_id         UUID;
    v_regiao_nova_id  UUID;
    v_aberta_id       UUID;
    v_aberta_reg_id   UUID;
    v_aberta_inicio   DATE;
    v_reg_antiga      TEXT;
BEGIN
    -- Resolve loja (nome exato — uq_lojas_nome).
    SELECT id INTO v_loja_id
    FROM public.lojas WHERE nome = p_loja_nome;
    IF v_loja_id IS NULL THEN
        RAISE EXCEPTION 'Loja nao encontrada: %', p_loja_nome;
    END IF;

    -- Resolve regiao nova (nome exato — uq_regioes_nome).
    SELECT id INTO v_regiao_nova_id
    FROM public.regioes WHERE nome = p_regiao_nova;
    IF v_regiao_nova_id IS NULL THEN
        RAISE EXCEPTION 'Regiao nao encontrada: %', p_regiao_nova;
    END IF;

    -- Linha de vigencia aberta atual (0 ou 1 — uq_lrv_loja_aberta).
    SELECT id, regiao_id, vigencia_inicio
      INTO v_aberta_id, v_aberta_reg_id, v_aberta_inicio
    FROM public.loja_regiao_vigencia
    WHERE loja_id = v_loja_id AND vigencia_fim IS NULL;

    -- Idempotencia: ja esta na regiao nova => no-op (garante ponteiro).
    IF v_aberta_reg_id = v_regiao_nova_id THEN
        UPDATE public.lojas
           SET regiao_id = v_regiao_nova_id
         WHERE id = v_loja_id AND regiao_id IS DISTINCT FROM v_regiao_nova_id;
        RETURN format('no-op: %s ja esta em %s',
                      p_loja_nome, p_regiao_nova);
    END IF;

    -- Sem linha aberta (loja sem vigencia, ex.: regiao_id era NULL):
    -- apenas abre a nova.
    IF v_aberta_id IS NULL THEN
        INSERT INTO public.loja_regiao_vigencia
            (loja_id, regiao_id, vigencia_inicio)
        VALUES (v_loja_id, v_regiao_nova_id, p_data_efetiva);
        UPDATE public.lojas
           SET regiao_id = v_regiao_nova_id WHERE id = v_loja_id;
        RETURN format('nova vigencia p/ %s em %s (sem linha anterior)',
                      p_loja_nome, p_regiao_nova);
    END IF;

    -- Guarda temporal: a data efetiva tem de ser POSTERIOR ao inicio
    -- da linha aberta (senao criaria janela invalida / sobreposta).
    IF p_data_efetiva <= v_aberta_inicio THEN
        RAISE EXCEPTION
            'data_efetiva % <= inicio da vigencia aberta (%) da loja %',
            p_data_efetiva, v_aberta_inicio, p_loja_nome;
    END IF;

    v_reg_antiga := (SELECT nome FROM public.regioes
                     WHERE id = v_aberta_reg_id);

    -- 1) fecha a linha aberta
    UPDATE public.loja_regiao_vigencia
       SET vigencia_fim = p_data_efetiva
     WHERE id = v_aberta_id;

    -- 2) abre a nova linha
    INSERT INTO public.loja_regiao_vigencia
        (loja_id, regiao_id, vigencia_inicio)
    VALUES (v_loja_id, v_regiao_nova_id, p_data_efetiva);

    -- 3) atualiza o ponteiro do organograma atual
    UPDATE public.lojas
       SET regiao_id = v_regiao_nova_id WHERE id = v_loja_id;

    RETURN format('remanejada %s: %s -> %s em %s',
                  p_loja_nome, v_reg_antiga, p_regiao_nova, p_data_efetiva);
END;
$$;

COMMENT ON FUNCTION fn_aplicar_remanejamento_regiao(TEXT, TEXT, DATE) IS
    'Remaneja UMA loja para nova regiao a partir de data_efetiva, '
    'atomico: fecha vigencia aberta, abre nova e atualiza '
    'lojas.regiao_id. Idempotente. Escrita — so service_role/owner.';

-- Escrita: nao expor aos papeis publicos do app.
REVOKE ALL ON FUNCTION fn_aplicar_remanejamento_regiao(TEXT, TEXT, DATE)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION fn_aplicar_remanejamento_regiao(TEXT, TEXT, DATE)
    FROM anon, authenticated;
