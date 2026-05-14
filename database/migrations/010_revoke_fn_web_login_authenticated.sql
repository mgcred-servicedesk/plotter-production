-- =====================================================
-- Migracao 010: Restringir EXECUTE em fn_web_login
--
-- !!! RASCUNHO — VALIDAR ANTES DE APLICAR !!!
-- Status: PENDENTE (2026-05-11)
-- Pre-requisito: confirmar no app "angry-man" que NENHUM
-- fluxo chama fn_web_login com JWT ja autenticado
-- (ex.: troca de conta, refresh, re-login). Se houver,
-- esses fluxos quebrarao apos aplicar.
-- Ver docs/agents/progress/2026-05-11-revoke-fn-web-login.md.
--
-- Objetivo: corrigir alertas do Supabase
--   - "fn_web_login can be executed by the authenticated
--      role as a SECURITY DEFINER function"
--   - (warning para anon e' intencional — login precisa
--      ser chamavel por usuario nao autenticado;
--      mantemos EXECUTE para anon)
--
-- Estrategia:
--   - REVOKE EXECUTE FROM authenticated (e PUBLIC por
--     seguranca, caso default tenha sido herdado).
--   - MANTER EXECUTE para anon (necessario para login).
--   - Mantemos SECURITY DEFINER (a funcao precisa ler
--     senha_hash da tabela usuarios bypassando RLS).
--
-- Idempotente. Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Revogar de PUBLIC e authenticated
-- ===========================================

REVOKE EXECUTE ON FUNCTION public.fn_web_login(
    p_usuario  text,
    p_senha    text
) FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.fn_web_login(
    p_usuario  text,
    p_senha    text
) FROM authenticated;


-- ===========================================
-- 2. Confirmar EXECUTE para anon e service_role (idempotente)
-- ===========================================
-- anon: necessario para o endpoint de login nao autenticado.
-- service_role: necessario para a Edge Function auth-login,
--   que usa SUPABASE_SERVICE_ROLE_KEY para chamar fn_web_login.
--   REVOKE FROM PUBLIC removeu o grant herdado — precisa ser
--   concedido explicitamente.

GRANT EXECUTE ON FUNCTION public.fn_web_login(
    p_usuario  text,
    p_senha    text
) TO anon;

GRANT EXECUTE ON FUNCTION public.fn_web_login(
    p_usuario  text,
    p_senha    text
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
--   AND routine_name   = 'fn_web_login';
--
-- Esperado: 'anon' e 'service_role' (e o owner) com EXECUTE.
-- 'authenticated' e 'PUBLIC' nao devem aparecer.
--
-- Recomendacoes adicionais (fora desta migration,
-- a serem feitas no projeto que define a funcao):
--   1. Garantir que a funcao retorna mensagem generica
--      em falha (nao distinguir "usuario nao existe" de
--      "senha incorreta") para evitar enumeracao.
--   2. Implementar rate limiting (Edge Function ou proxy)
--      para mitigar ataques de forca bruta — fn_web_login
--      por design e' chamavel pela anon key.
