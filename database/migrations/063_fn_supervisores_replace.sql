-- =====================================================
-- Migracao 063: fn_supervisores_replace(p_rows jsonb)
--
-- Contexto (ver progress doc 2026-07-09-supervisor-como-
-- consultor-exclusao-global.md e migration 062): o import de
-- supervisores do angry-man (configuracao/Supervisores.xlsx)
-- fazia upsert com onConflict (nome, loja_id) e NUNCA removia
-- o par antigo quando um supervisor trocava de loja. Cada
-- rodizio deixava lixo para tras (duplicata da MONICA; CRISTINA
-- aparecendo como consultora em HELP BANGU). A 062 corrigiu o
-- estado; esta migration corrige o MECANISMO: a planilha passa
-- a ser a foto unica de quem supervisiona qual loja, no mesmo
-- padrao ja usado por fn_pagamentos_online_replace (015) e
-- fn_importar_reconquista.
--
-- Bonus corrigido de tabela: o upsert antigo tambem duplicava
-- linhas com loja_id NULL a cada import (UNIQUE com NULLS
-- DISTINCT nao dispara o onConflict) — o DISTINCT ON abaixo
-- deduplica inclusive pares com loja nula.
--
-- regiao_id: derivado da regiao ATUAL da loja (lojas.regiao_id),
-- fonte unica de verdade — mesma regra da 062. O valor vindo da
-- planilha e usado apenas como fallback quando a loja nao
-- resolve (loja_id NULL).
--
-- Garantias (padrao 015):
--   (a) Minimo de linhas (30) — evita wipe silencioso por
--       planilha corrompida/aba errada (tabela tem ~52 linhas).
--   (b) Advisory lock (id 20260709) — uploads concorrentes
--       serializam.
--   (c) DELETE + INSERT na mesma transacao implicita — se o
--       INSERT falhar, o DELETE e revertido (base preservada).
--
-- Consumidor: angry-man importSupervisores (Electron via IPC
-- service_role; web via Edge Function reconquista-rpc, que
-- valida JWT admin/gestor). Nenhuma FK/view referencia
-- supervisores.id — regenerar ids a cada import e seguro.
--
-- Retorno:
--   { count: N, count_before: M, sem_loja: K, error: NULL }
--   { count: 0, error: 'mensagem' }                       falha
-- =====================================================

CREATE OR REPLACE FUNCTION public.fn_supervisores_replace(p_rows jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_min_linhas   integer := 30;
    v_payload_len  integer;
    v_count_before integer := 0;
    v_count_after  integer := 0;
    v_sem_loja     integer := 0;
BEGIN
    -- 1. Validar payload nao-nulo e do tipo array
    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Payload ausente ou nao e um array JSON.'
        );
    END IF;

    v_payload_len := jsonb_array_length(p_rows);

    -- 2. Minimo de linhas (evita wipe silencioso)
    IF v_payload_len < v_min_linhas THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format(
                'Planilha com %s linhas — abaixo do minimo esperado (%s). '
                'Substituicao abortada (base preservada).',
                v_payload_len, v_min_linhas
            )
        );
    END IF;

    -- 3. Advisory lock — serializa uploads concorrentes
    PERFORM pg_advisory_xact_lock(20260709);

    SELECT count(*) INTO v_count_before FROM supervisores;

    -- 4. Substituicao atomica
    -- `WHERE true` requerido pela extensao safeupdate do Supabase.
    DELETE FROM supervisores WHERE true;

    INSERT INTO supervisores (nome, loja_id, regiao_id)
    SELECT DISTINCT ON (r.nome, r.loja_id)
        r.nome,
        r.loja_id,
        COALESCE(l.regiao_id, r.regiao_id)
    FROM jsonb_to_recordset(p_rows)
         AS r(nome text, loja_id uuid, regiao_id uuid)
    LEFT JOIN lojas l ON l.id = r.loja_id
    WHERE r.nome IS NOT NULL AND btrim(r.nome) <> '';

    GET DIAGNOSTICS v_count_after = ROW_COUNT;

    -- 5. Diagnostico: linhas que ficaram sem loja resolvida
    SELECT count(*) INTO v_sem_loja
    FROM supervisores
    WHERE loja_id IS NULL;

    RETURN jsonb_build_object(
        'count',        v_count_after,
        'count_before', v_count_before,
        'sem_loja',     v_sem_loja,
        'error',        NULL
    );

EXCEPTION WHEN OTHERS THEN
    -- A transacao implicita ja foi revertida — o DELETE nao persistiu.
    RETURN jsonb_build_object(
        'count', 0,
        'error', SQLERRM
    );
END;
$$;

COMMENT ON FUNCTION public.fn_supervisores_replace(jsonb) IS
    'Substitui atomicamente o conteudo de supervisores a partir '
    'da planilha Supervisores.xlsx (angry-man). Foto unica: pares '
    '(nome, loja) ausentes da planilha deixam de existir — rodizio '
    'de supervisores nao acumula lixo. regiao_id segue a regiao '
    'atual da loja. Minimo de 30 linhas, advisory lock 20260709, '
    'DELETE+INSERT na mesma transacao. SECURITY DEFINER; EXECUTE '
    'so para service_role.';


-- ===========================================
-- Permissoes
--
-- Padrao 015/058: revogar explicitamente de anon/authenticated
-- (ALTER DEFAULT PRIVILEGES do Supabase concede EXECUTE direto
-- a eles em toda funcao nova — REVOKE FROM PUBLIC nao basta).
-- ===========================================

REVOKE ALL ON FUNCTION public.fn_supervisores_replace(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_supervisores_replace(jsonb) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_supervisores_replace(jsonb) TO service_role;


-- ===========================================
-- Validacao pos-migracao
-- ===========================================
-- Smoke test (payload abaixo do minimo — deve recusar SEM tocar a base):
--
--   SELECT public.fn_supervisores_replace(
--       jsonb_build_array(jsonb_build_object('nome', 'X'))
--   );
--   -- { "count": 0, "error": "Planilha com 1 linhas ..." }
--
--   SELECT count(*) FROM supervisores;  -- inalterado
--
-- Confirmar permissoes (apenas service_role com EXECUTE):
--   SELECT grantee, privilege_type
--   FROM information_schema.routine_privileges
--   WHERE routine_name = 'fn_supervisores_replace';
