-- ============================================================
-- Migracao 029: Reconquista v2 — RPC de importacao
--
-- fn_importar_reconquista(p_rows JSONB):
--   1. TRUNCATE reconquista (foto unica — substitui a base).
--   2. Para cada linha: resolve loja_id (cod_bmg + sucessora) e
--      consultor_id (nome completo + loja) e insere.
--   3. Retorna contadores (inseridos, sem_loja, sem_consultor).
--
-- TRUNCATE + INSERT rodam na MESMA transacao (uma chamada RPC =
-- uma transacao). Se a carga falhar, a base anterior e
-- preservada (rollback).
--
-- Dedup defensivo: ON CONFLICT (co_adesao) DO NOTHING — mantem
-- a primeira ocorrencia caso o arquivo traga co_adesao repetido.
--
-- Schema esperado de cada objeto em p_rows:
--   {
--     "co_adesao": 9601063,                 -- BIGINT, obrigatorio
--     "status": "EFETIVADA",                -- TEXT, obrigatorio
--     "dt_fim_relacionamento": "2026-04-13",
--     "dt_macica": "2026-05-18",
--     "dt_dna": "2026-04-24",
--     "dt_producao": "2026-01-08",
--     "subproduto": "REFIN",
--     "no_franquia": "49925 - HELP! - RJ - ...",
--     "cod_bmg": 49925,                     -- prefixo de no_franquia
--     "consultor_nome": "ADERIVANIA SILVA ...",
--     "gerente_regional": "ANA PAULA RODRIGUES",
--     "gerente_loja": "JAQUELINE WENCESLAU",
--     "coordenador_loja": "SANDRA RAPOSO ...",
--     "banco_origem": "BANCO BMG S.A.",
--     "banco_destino": "104 - CAIXA ECONOMICA FEDERAL",
--     "saldo_contabil": 35718.00,
--     "dias_atraso": 45,
--     "faixa_atraso": "2. 1 A 90 DIAS",
--     "tipo_pagamento": "TED",
--     "qt_fim_relacionamento": 30,
--     "link_aceite": "https://dnabmg.help.com.br/..."
--   }
--
-- Depende de: 028_reconquista_v2_tabela.sql, 021_lojas_sucessao.sql.
-- Chamada por: scripts/importar_reconquista.py (role service_role).
-- Executar no Supabase SQL Editor.
-- ============================================================

CREATE OR REPLACE FUNCTION fn_importar_reconquista(
    p_rows JSONB
)
RETURNS TABLE (
    inseridos     INTEGER,
    sem_loja      INTEGER,
    sem_consultor INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_inseridos     INTEGER := 0;
    v_sem_loja      INTEGER := 0;
    v_sem_consultor INTEGER := 0;
    v_row           JSONB;
    v_loja_id       UUID;
    v_consultor_id  UUID;
    v_consultor_nm  TEXT;
    v_affected      INTEGER;
BEGIN
    TRUNCATE TABLE public.reconquista;

    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows)
    LOOP
        -- Loja: resolve pelo cod_bmg ja com sucessora aplicada
        v_loja_id := NULL;
        IF (v_row->>'cod_bmg') IS NOT NULL THEN
            SELECT COALESCE(l.sucessora_id, l.id) INTO v_loja_id
            FROM public.lojas l
            WHERE l.cod_bmg = (v_row->>'cod_bmg')::INTEGER
            LIMIT 1;
        END IF;

        IF v_loja_id IS NULL THEN
            v_sem_loja := v_sem_loja + 1;
        END IF;

        -- Consultor: nome completo (novo layout) + loja
        v_consultor_id := NULL;
        v_consultor_nm := NULLIF(TRIM(v_row->>'consultor_nome'), '');
        IF v_consultor_nm IS NOT NULL THEN
            SELECT c.id INTO v_consultor_id
            FROM public.consultores c
            WHERE c.nome ILIKE v_consultor_nm
              AND (c.loja_id = v_loja_id OR c.loja_id IS NULL)
            ORDER BY CASE WHEN c.loja_id = v_loja_id THEN 0 ELSE 1 END, c.nome
            LIMIT 1;
        END IF;

        IF v_consultor_id IS NULL THEN
            v_sem_consultor := v_sem_consultor + 1;
        END IF;

        INSERT INTO public.reconquista (
            co_adesao, status,
            dt_fim_relacionamento, dt_macica, dt_dna, dt_producao,
            subproduto,
            no_franquia, cod_bmg, loja_id,
            consultor_nome, consultor_id,
            gerente_regional, gerente_loja, coordenador_loja,
            banco_origem, banco_destino, saldo_contabil,
            dias_atraso, faixa_atraso, tipo_pagamento,
            qt_fim_relacionamento, link_aceite
        )
        VALUES (
            (v_row->>'co_adesao')::BIGINT,
            v_row->>'status',
            (v_row->>'dt_fim_relacionamento')::DATE,
            (v_row->>'dt_macica')::DATE,
            (v_row->>'dt_dna')::DATE,
            (v_row->>'dt_producao')::DATE,
            v_row->>'subproduto',
            v_row->>'no_franquia',
            (v_row->>'cod_bmg')::INTEGER,
            v_loja_id,
            v_consultor_nm,
            v_consultor_id,
            v_row->>'gerente_regional',
            v_row->>'gerente_loja',
            v_row->>'coordenador_loja',
            v_row->>'banco_origem',
            v_row->>'banco_destino',
            (v_row->>'saldo_contabil')::NUMERIC,
            (v_row->>'dias_atraso')::INTEGER,
            v_row->>'faixa_atraso',
            v_row->>'tipo_pagamento',
            (v_row->>'qt_fim_relacionamento')::INTEGER,
            v_row->>'link_aceite'
        )
        ON CONFLICT (co_adesao) DO NOTHING;

        GET DIAGNOSTICS v_affected = ROW_COUNT;
        v_inseridos := v_inseridos + v_affected;
    END LOOP;

    RETURN QUERY SELECT v_inseridos, v_sem_loja, v_sem_consultor;
END;
$$;

COMMENT ON FUNCTION fn_importar_reconquista(JSONB) IS
    'Reconquista v2: TRUNCATE + carga em lote da tabela reconquista. '
    'Resolve loja_id (cod_bmg + sucessora) e consultor_id (nome '
    'completo + loja). Atomica (truncate+insert na mesma transacao). '
    'Retorna (inseridos, sem_loja, sem_consultor) para logging.';

-- Apenas service_role/admin importam
REVOKE ALL ON FUNCTION fn_importar_reconquista(JSONB) FROM PUBLIC;
