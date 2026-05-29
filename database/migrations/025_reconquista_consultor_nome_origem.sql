-- ============================================================
-- Migracao 025: Persistir primeiro nome do consultor no
-- snapshot do Reconquista
--
-- Contexto: o arquivo xlsx traz `CONSULTOR` truncado em ~14
-- chars (ex: "CHALLANA DE"). O lookup por prefixo + loja
-- (fn_importar_reconquista_snapshot) frequentemente nao
-- encontra o consultor cadastrado e ate hoje o nome do
-- arquivo era descartado — perdiamos a rastreabilidade da
-- linha quando consultor_id ficava NULL.
--
-- Esta migracao adiciona uma coluna textual que persiste
-- SEMPRE o primeiro nome (split_part(consultor_prefix, ' ', 1)),
-- independente do FK ter sido resolvido. A loja ja e
-- associada via cod_bmg (com sucessora), entao snapshots
-- "sem consultor" mantem ao menos loja + nome bruto do
-- consultor para auditoria/futura conciliacao.
--
-- Backfill: a coluna fica NULL para snapshots ja importados.
-- O reprocessamento da base via angry-man preenche o campo
-- (decisao do projeto: reprocessar em vez de backfill SQL).
--
-- Depende de: 018_reconquista_tables.sql, 022_reconquista_resolve_sucessora.sql.
-- Executar no Supabase SQL Editor.
-- ============================================================


-- 1. Coluna nova ----------------------------------------------

ALTER TABLE reconquista_snapshot
    ADD COLUMN IF NOT EXISTS consultor_nome_origem TEXT;

COMMENT ON COLUMN reconquista_snapshot.consultor_nome_origem IS
    'Primeiro nome do consultor extraido do arquivo xlsx '
    '(split_part(CONSULTOR, '' '', 1)). Persistido sempre, '
    'mesmo quando consultor_id resolve via lookup, para '
    'rastrear o valor bruto do arquivo. NULL apenas para '
    'snapshots importados antes desta migracao (025).';


-- 2. fn_importar_reconquista_snapshot --------------------------
--
-- Mantem assinatura, sucessora e contadores das migracoes
-- 020/022. Acrescenta a persistencia de consultor_nome_origem
-- no INSERT e no UPDATE (ON CONFLICT).

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
DECLARE
    v_inseridos       INTEGER := 0;
    v_atualizados     INTEGER := 0;
    v_sem_loja        INTEGER := 0;
    v_sem_consultor   INTEGER := 0;
    v_row             JSONB;
    v_loja_id         UUID;
    v_consultor_id    UUID;
    v_prefix          TEXT;
    v_nome_origem     TEXT;
    v_was_insert      BOOLEAN;
BEGIN
    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows)
    LOOP
        -- Lookup loja por cod_bmg; resolve sucessora 1 nivel.
        SELECT COALESCE(sucessora_id, id) INTO v_loja_id
        FROM public.lojas
        WHERE cod_bmg = (v_row->>'cod_bmg_loja')::INTEGER
        LIMIT 1;

        IF v_loja_id IS NULL THEN
            v_sem_loja := v_sem_loja + 1;
        END IF;

        -- Primeiro nome do consultor a partir do prefixo do xlsx.
        -- Persistido sempre (mesmo quando o FK resolve).
        v_prefix := v_row->>'consultor_prefix';
        v_nome_origem := NULLIF(
            TRIM(split_part(COALESCE(v_prefix, ''), ' ', 1)),
            ''
        );

        -- Lookup consultor por prefixo + loja.
        v_consultor_id := NULL;
        SELECT id INTO v_consultor_id
        FROM public.consultores
        WHERE nome ILIKE COALESCE(v_prefix, '') || '%'
          AND (loja_id = v_loja_id OR loja_id IS NULL)
        ORDER BY
            CASE WHEN loja_id = v_loja_id THEN 0 ELSE 1 END,
            nome
        LIMIT 1;

        IF v_consultor_id IS NULL THEN
            v_sem_consultor := v_sem_consultor + 1;
        END IF;

        INSERT INTO public.reconquista_snapshot (
            macica_id, dat_envio, cod_ade,
            loja_id, consultor_id, consultor_nome_origem,
            subproduto,
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
            v_nome_origem,
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
            SET loja_id               = EXCLUDED.loja_id,
                consultor_id          = EXCLUDED.consultor_id,
                consultor_nome_origem = EXCLUDED.consultor_nome_origem,
                subproduto            = EXCLUDED.subproduto,
                saldo_contabil        = EXCLUDED.saldo_contabil,
                dias_atraso           = EXCLUDED.dias_atraso,
                faixa_atraso          = EXCLUDED.faixa_atraso,
                mot_ipd_operar        = EXCLUDED.mot_ipd_operar,
                flag_cnc              = EXCLUDED.flag_cnc,
                flag_consignado       = EXCLUDED.flag_consignado,
                flag_cartao           = EXCLUDED.flag_cartao,
                flag_dna              = EXCLUDED.flag_dna,
                flag_reconquista      = EXCLUDED.flag_reconquista,
                flag_rl               = EXCLUDED.flag_rl,
                tipo_pgto             = EXCLUDED.tipo_pgto,
                tipo_conta            = EXCLUDED.tipo_conta,
                regra_pgto            = EXCLUDED.regra_pgto,
                dat_fim_relac         = EXCLUDED.dat_fim_relac,
                banco_origem          = EXCLUDED.banco_origem,
                banco_destino         = EXCLUDED.banco_destino,
                qtd_fdr               = EXCLUDED.qtd_fdr,
                link                  = EXCLUDED.link
        RETURNING (xmax = 0) INTO v_was_insert;

        IF v_was_insert THEN
            v_inseridos := v_inseridos + 1;
        ELSE
            v_atualizados := v_atualizados + 1;
        END IF;
    END LOOP;

    UPDATE public.macicas
    SET dat_ultimo_envio = GREATEST(dat_ultimo_envio, p_dat_envio),
        updated_at       = now()
    WHERE id = p_macica_id;

    RETURN QUERY SELECT v_inseridos, v_atualizados, v_sem_loja, v_sem_consultor;
END;
$$;

REVOKE ALL ON FUNCTION fn_importar_reconquista_snapshot FROM PUBLIC;

COMMENT ON FUNCTION fn_importar_reconquista_snapshot IS
    'Importa em lote os snapshots de um arquivo xlsx. '
    'Resolve loja_id (com sucessora) e consultor_id (FK) '
    'internamente. Persiste sempre consultor_nome_origem '
    '(primeiro nome do arquivo). Upsert por '
    '(macica_id, dat_envio, cod_ade). Retorna contadores '
    'para logging.';
