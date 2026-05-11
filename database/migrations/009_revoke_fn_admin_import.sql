-- =====================================================
-- Migracao 009: Restringir EXECUTE em fn_admin_import
--
-- !!! RASCUNHO — NAO APLICAR AINDA !!!
-- Status: PENDENTE (2026-05-11)
-- Motivo: o app "angry-man" chama esta RPC usando a
-- anon key. Aplicar agora quebra o pipeline de import.
-- Pre-requisito: migrar angry-man para usar
-- service_role (via backend) antes de rodar este SQL.
-- Ver docs/agents/progress/2026-05-11-revoke-fn-admin-import.md.
--
-- Objetivo: corrigir alerta de seguranca do Supabase
-- ("Function public.fn_admin_import ... can be executed
--  by the anon role as a SECURITY DEFINER function via
--  /rest/v1/rpc/fn_admin_import").
--
-- Contexto:
--   - A funcao roda como SECURITY DEFINER (privilegios
--     do criador) e por padrao Postgres concede EXECUTE
--     a PUBLIC, expondo-a via PostgREST com a anon key.
--   - O uso real e via backend de importacao usando a
--     service_role key (bypass de RLS), portanto anon
--     e authenticated NAO devem chamar esta RPC.
--
-- Estrategia: revogar EXECUTE de PUBLIC/anon/authenticated
-- e conceder explicitamente apenas a service_role.
-- Mantemos SECURITY DEFINER (intencional: importacao em
-- massa que precisa contornar RLS de forma controlada).
--
-- Idempotente. Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Revogar acesso publico
-- ===========================================

REVOKE EXECUTE ON FUNCTION public.fn_admin_import(
    p_table         text,
    p_data          jsonb,
    p_on_conflict   text,
    p_delete_where  jsonb
) FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.fn_admin_import(
    p_table         text,
    p_data          jsonb,
    p_on_conflict   text,
    p_delete_where  jsonb
) FROM anon;

REVOKE EXECUTE ON FUNCTION public.fn_admin_import(
    p_table         text,
    p_data          jsonb,
    p_on_conflict   text,
    p_delete_where  jsonb
) FROM authenticated;


-- ===========================================
-- 2. Conceder EXECUTE somente a service_role
-- ===========================================

GRANT EXECUTE ON FUNCTION public.fn_admin_import(
    p_table         text,
    p_data          jsonb,
    p_on_conflict   text,
    p_delete_where  jsonb
) TO service_role;


-- ===========================================
-- 3. Validacao manual (apos executar)
-- ===========================================
-- Confira os grants atuais com:
--
-- SELECT
--     grantee,
--     privilege_type
-- FROM information_schema.role_routine_grants
-- WHERE routine_schema = 'public'
--   AND routine_name   = 'fn_admin_import';
--
-- Esperado: apenas 'service_role' (e o owner) com EXECUTE.
