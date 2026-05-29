-- ============================================================
-- Migracao 020: RPCs de importacao do Reconquista
--
-- Depende de: 018_reconquista_tables.sql
-- Chamadas por: angry-man (role: service_role).
--
-- Adiciona:
--   - fn_upsert_macica
--   - fn_importar_reconquista_snapshot
--
-- Detalhe do contador: usamos (xmax = 0) no RETURNING para
-- distinguir INSERT real de UPDATE no ON CONFLICT.
--
-- Executar no Supabase SQL Editor.
-- ============================================================


-- ============================================================
-- fn_upsert_macica
--
-- Cria ou atualiza uma maciça. Retorna o UUID.
-- Idempotente por `codigo`. Atualiza dat_ultimo_envio mantendo
-- o maior valor (GREATEST com NULL safe).
-- ============================================================

CREATE OR REPLACE FUNCTION fn_upsert_macica(
    p_codigo             TEXT,
    p_descricao          TEXT,
    p_dat_primeiro_envio DATE,
    p_dat_ultimo_envio   DATE    DEFAULT NULL,
    p_meta_retencao      NUMERIC DEFAULT 30.0
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO public.macicas (
        codigo, descricao, dat_primeiro_envio,
        dat_ultimo_envio, meta_retencao
    )
    VALUES (
        p_codigo, p_descricao, p_dat_primeiro_envio,
        p_dat_ultimo_envio, p_meta_retencao
    )
    ON CONFLICT (codigo) DO UPDATE
        SET descricao        = EXCLUDED.descricao,
            dat_ultimo_envio = GREATEST(
                                   public.macicas.dat_ultimo_envio,
                                   EXCLUDED.dat_ultimo_envio
                               ),
            updated_at       = now()
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION fn_upsert_macica IS
    'Cria ou atualiza uma maciça. Retorna o UUID. '
    'Idempotente por codigo.';


-- ============================================================
-- fn_importar_reconquista_snapshot
--
-- Importa em lote linhas de um arquivo xlsx. Recebe JSONB
-- com array de objetos. Resolve loja_id (via lojas.cod_bmg)
-- e consultor_id (nome ILIKE prefixo + loja) internamente.
--
-- Retorno: contadores de insercoes, atualizacoes e falhas de
-- lookup (sem_loja, sem_consultor). A distincao insert/update
-- vem de (xmax = 0) no RETURNING.
-- ============================================================

CREATE OR REPLACE FUNCTION fn_importar_reconquista_snapshot(
    p_macica_id UUID,
    p_dat_envio DATE,
    p_rows      JSONB
)
RETURNS TABLE (
    inseridos     INTEGER,
    atualizados   INTEGER,
    sem_loja      INTEGER,
    sem_consultor INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
/*
Schema esperado para cada objeto em p_rows:
{
    "cod_ade":         9601063,
    "cod_bmg_loja":    53418,
    "consultor_prefix":"CHALLANA DE",
    "subproduto":      "SUPER CONTA",
    "saldo_contabil":  1500.00,
    "dias_atraso":     45,
    "faixa_atraso":    "31-60",
    "mot_ipd_operar":  null,
    "flag_cnc":        0,
    "flag_consignado": 0,
    "flag_cartao":     0,
    "flag_dna":        0,
    "flag_reconquista":0,
    "flag_rl":         0,
    "tipo_pgto":       null,
    "tipo_conta":      null,
    "regra_pgto":      null,
    "dat_fim_relac":   null,
    "banco_origem":    null,
    "banco_destino":   null,
    "qtd_fdr":         0,
    "link":            null
}
*/
DECLARE
    v_inseridos     INTEGER := 0;
    v_atualizados   INTEGER := 0;
    v_sem_loja      INTEGER := 0;
    v_sem_consultor INTEGER := 0;
    v_row           JSONB;
    v_loja_id       UUID;
    v_consultor_id  UUID;
    v_was_insert    BOOLEAN;
BEGIN
    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows)
    LOOP
        -- Lookup loja por cod_bmg
        v_loja_id := NULL;
        SELECT id INTO v_loja_id
        FROM public.lojas
        WHERE cod_bmg = (v_row->>'cod_bmg_loja')::INTEGER
        LIMIT 1;

        IF v_loja_id IS NULL THEN
            v_sem_loja := v_sem_loja + 1;
        END IF;

        -- Lookup consultor por prefixo de nome (preferindo a loja)
        v_consultor_id := NULL;
        SELECT id INTO v_consultor_id
        FROM public.consultores
        WHERE nome ILIKE (v_row->>'consultor_prefix') || '%'
          AND (loja_id = v_loja_id OR loja_id IS NULL)
        ORDER BY
            CASE WHEN loja_id = v_loja_id THEN 0 ELSE 1 END,
            nome
        LIMIT 1;

        IF v_consultor_id IS NULL THEN
            v_sem_consultor := v_sem_consultor + 1;
        END IF;

        -- Upsert do snapshot. (xmax = 0) no RETURNING distingue
        -- INSERT (xmax zerado) de UPDATE (xmax > 0).
        INSERT INTO public.reconquista_snapshot (
            macica_id, dat_envio, cod_ade,
            loja_id, consultor_id, subproduto,
            saldo_contabil, dias_atraso, faixa_atraso, mot_ipd_operar,
            flag_cnc, flag_consignado, flag_cartao,
            flag_dna, flag_reconquista, flag_rl,
            tipo_pgto, tipo_conta, regra_pgto,
            dat_fim_relac, banco_origem, banco_destino,
            qtd_fdr, link
        )
        VALUES (
            p_macica_id,
            p_dat_envio,
            (v_row->>'cod_ade')::BIGINT,
            v_loja_id,
            v_consultor_id,
            v_row->>'subproduto',
            (v_row->>'saldo_contabil')::NUMERIC,
            (v_row->>'dias_atraso')::INTEGER,
            v_row->>'faixa_atraso',
            v_row->>'mot_ipd_operar',
            COALESCE((v_row->>'flag_cnc')::SMALLINT, 0),
            COALESCE((v_row->>'flag_consignado')::SMALLINT, 0),
            COALESCE((v_row->>'flag_cartao')::SMALLINT, 0),
            COALESCE((v_row->>'flag_dna')::SMALLINT, 0),
            COALESCE((v_row->>'flag_reconquista')::SMALLINT, 0),
            COALESCE((v_row->>'flag_rl')::SMALLINT, 0),
            v_row->>'tipo_pgto',
            v_row->>'tipo_conta',
            v_row->>'regra_pgto',
            (v_row->>'dat_fim_relac')::DATE,
            v_row->>'banco_origem',
            v_row->>'banco_destino',
            (v_row->>'qtd_fdr')::INTEGER,
            v_row->>'link'
        )
        ON CONFLICT (macica_id, dat_envio, cod_ade) DO UPDATE
            SET loja_id          = EXCLUDED.loja_id,
                consultor_id     = EXCLUDED.consultor_id,
                subproduto       = EXCLUDED.subproduto,
                saldo_contabil   = EXCLUDED.saldo_contabil,
                dias_atraso      = EXCLUDED.dias_atraso,
                faixa_atraso     = EXCLUDED.faixa_atraso,
                mot_ipd_operar   = EXCLUDED.mot_ipd_operar,
                flag_cnc         = EXCLUDED.flag_cnc,
                flag_consignado  = EXCLUDED.flag_consignado,
                flag_cartao      = EXCLUDED.flag_cartao,
                flag_dna         = EXCLUDED.flag_dna,
                flag_reconquista = EXCLUDED.flag_reconquista,
                flag_rl          = EXCLUDED.flag_rl,
                tipo_pgto        = EXCLUDED.tipo_pgto,
                tipo_conta       = EXCLUDED.tipo_conta,
                regra_pgto       = EXCLUDED.regra_pgto,
                dat_fim_relac    = EXCLUDED.dat_fim_relac,
                banco_origem     = EXCLUDED.banco_origem,
                banco_destino    = EXCLUDED.banco_destino,
                qtd_fdr          = EXCLUDED.qtd_fdr,
                link             = EXCLUDED.link
        RETURNING (xmax = 0) INTO v_was_insert;

        IF v_was_insert THEN
            v_inseridos := v_inseridos + 1;
        ELSE
            v_atualizados := v_atualizados + 1;
        END IF;
    END LOOP;

    -- Atualizar dat_ultimo_envio da maciça
    UPDATE public.macicas
    SET dat_ultimo_envio = GREATEST(dat_ultimo_envio, p_dat_envio),
        updated_at       = now()
    WHERE id = p_macica_id;

    RETURN QUERY SELECT v_inseridos, v_atualizados, v_sem_loja, v_sem_consultor;
END;
$$;

COMMENT ON FUNCTION fn_importar_reconquista_snapshot IS
    'Importa em lote os snapshots de um arquivo xlsx. '
    'Resolve loja_id e consultor_id internamente. '
    'Upsert por (macica_id, dat_envio, cod_ade). '
    'Retorna contadores (inseridos, atualizados, sem_loja, sem_consultor) '
    'para logging no angry-man. Recomendado: lotes de 500 linhas.';


-- ============================================================
-- Permissoes: apenas service_role/admin podem chamar.
-- ============================================================

REVOKE ALL ON FUNCTION fn_upsert_macica                  FROM PUBLIC;
REVOKE ALL ON FUNCTION fn_importar_reconquista_snapshot  FROM PUBLIC;
