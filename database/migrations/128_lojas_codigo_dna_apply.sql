-- =====================================================
-- Migracao 128: fn_lojas_codigo_dna_apply — import de Codigos de
--               Loja (DNA) sem UPDATE direto do cliente
--
-- CONTEXTO (2026-10-02)
-- O card "Codigos de Loja Help" do angry-man gravava `lojas.codigo_dna`
-- com UPDATE direto na tabela:
--   * no desktop, pelo processo principal do Electron com a chave
--     service_role — que estava EMBUTIDA no instalador e esta sendo
--     removida do app;
--   * na web, com a chave anon. `lojas` so tem policy de SELECT
--     (pol_lojas_leitura), entao o UPDATE afetava ZERO linhas sem
--     devolver erro, e o import contava cada loja como "atualizada".
--     Bug silencioso: na web o import nunca gravou nada.
--
-- Esta RPC e o caminho unico das duas versoes: angry-man -> Edge
-- Function `reconquista-rpc` (whitelist + JWT do app, admin/gestor) ->
-- RPC com service_role. Mesmo desenho de fn_lojas_sucessao_apply.
--
-- UNICIDADE (uq_lojas_codigo_dna)
-- Duas lojas do arquivo podem TROCAR de codigo entre si. Gravar linha a
-- linha bateria na constraint no meio da troca. Por isso: (1) limpa o
-- codigo das lojas do arquivo, (2) grava os novos — tudo na mesma
-- transacao. Codigo que ja pertence a uma loja FORA do arquivo continua
-- violando a constraint e aborta o import inteiro (nada e gravado): e
-- conflito real de cadastro, a decidir por quem importa.
--
-- Payload: lista de {loja_id, codigo_dna}. O match nome -> id continua
-- no importador (lookup de lojas), como antes.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE OR REPLACE FUNCTION public.fn_lojas_codigo_dna_apply(
    p_rows JSONB
)
RETURNS TABLE (
    atualizadas    INTEGER,
    nao_encontradas INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_atualizadas     INTEGER := 0;
    v_total           INTEGER := 0;
BEGIN
    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RAISE EXCEPTION 'p_rows deve ser um array JSON.';
    END IF;

    CREATE TEMP TABLE _codigos ON COMMIT DROP AS
    SELECT DISTINCT ON ((r->>'loja_id')::UUID)
        (r->>'loja_id')::UUID          AS loja_id,
        NULLIF(TRIM(r->>'codigo_dna'), '') AS codigo_dna
    FROM jsonb_array_elements(p_rows) AS r
    WHERE (r->>'loja_id') IS NOT NULL;

    SELECT count(*) INTO v_total FROM _codigos;

    IF EXISTS (SELECT 1 FROM _codigos WHERE codigo_dna IS NULL) THEN
        RAISE EXCEPTION 'Codigo DNA vazio no payload.';
    END IF;

    -- (1) libera os codigos das lojas do arquivo (permite troca entre elas)
    UPDATE public.lojas l
       SET codigo_dna = NULL
      FROM _codigos c
     WHERE l.id = c.loja_id;

    -- (2) grava os codigos novos
    UPDATE public.lojas l
       SET codigo_dna = c.codigo_dna,
           updated_at = now()
      FROM _codigos c
     WHERE l.id = c.loja_id;
    GET DIAGNOSTICS v_atualizadas = ROW_COUNT;

    RETURN QUERY SELECT v_atualizadas, v_total - v_atualizadas;
END;
$$;

COMMENT ON FUNCTION public.fn_lojas_codigo_dna_apply(JSONB) IS
    'Grava lojas.codigo_dna em lote (payload {loja_id, codigo_dna}). '
    'Limpa e regrava na mesma transacao para permitir troca de codigo '
    'entre lojas do arquivo. Retorna (atualizadas, nao_encontradas = '
    'loja_id inexistente). Chamada pelo angry-man via Edge Function '
    'reconquista-rpc.';

REVOKE EXECUTE ON FUNCTION public.fn_lojas_codigo_dna_apply(JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_lojas_codigo_dna_apply(JSONB)
    TO service_role;


-- =====================================================
-- VALIDACAO — rodar apos aplicar
--
-- 1) So service_role executa (esperado: anon=false, authenticated=false):
--
--    SELECT has_function_privilege('anon',
--             'public.fn_lojas_codigo_dna_apply(jsonb)', 'EXECUTE') AS anon,
--           has_function_privilege('authenticated',
--             'public.fn_lojas_codigo_dna_apply(jsonb)', 'EXECUTE') AS auth;
--
-- 2) Apos importar "Codigo Lojas Help.xlsx" no angry-man, conferir:
--
--    SELECT count(*) FILTER (WHERE codigo_dna IS NOT NULL) AS com_codigo,
--           count(*) AS lojas
--    FROM public.lojas WHERE ativo;
-- =====================================================
