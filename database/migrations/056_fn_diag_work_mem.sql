-- =====================================================
-- Migracao 056: fn_diag_work_mem — diagnostico do work_mem na API
--
-- Contexto (continuacao do Disk IO Budget; ver 054 e
-- docs/agents/progress/2026-07-08-disk-io-*.md):
--
-- A 054 setou work_mem=12MB no role `authenticator`, mas GUC de role
-- aplica no LOGIN — as conexoes ja abertas do pool do PostgREST nao
-- pegam o valor novo ate o pool reciclar (ou restart do projeto).
-- `SHOW work_mem` no SQL Editor roda como `postgres` e NAO prova nada
-- sobre as conexoes da API. Esta funcao e a unica forma de enxergar o
-- GUC vigente DENTRO de uma conexao do pool: chamada via REST, devolve
-- o work_mem/role da propria conexao que atendeu o request.
--
-- Inocua: so expoe um GUC de tuning e o role corrente (informacao que
-- o proprio erro do PostgREST ja revela). Droppavel em migration
-- futura quando a medicao pos-054 fechar.
--
-- Executar no Supabase SQL Editor. Requer 054 aplicada.
-- =====================================================

CREATE OR REPLACE FUNCTION fn_diag_work_mem()
RETURNS JSON
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT json_build_object(
        'role',     current_user,
        'work_mem', current_setting('work_mem')
    );
$$;

GRANT EXECUTE ON FUNCTION fn_diag_work_mem() TO anon, authenticated;


-- ===========================================
-- Verificacao (fora do SQL Editor — precisa passar pela API):
--
--   curl -s -X POST "$SUPABASE_URL/rest/v1/rpc/fn_diag_work_mem" \
--     -H "apikey: $ANON_KEY" -H "Authorization: Bearer $ANON_KEY" \
--     -H "Content-Type: application/json" -d '{}'
--
--   Esperado: {"role":"anon","work_mem":"12MB"}
--   Se vier "4MB": o pool ainda tem conexoes antigas — repetir o
--   restart do projeto (Settings -> Infrastructure -> Restart project)
--   antes de medir temp_files.
--
-- Reversao:
--   DROP FUNCTION IF EXISTS fn_diag_work_mem();
-- ===========================================
