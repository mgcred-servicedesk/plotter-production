-- =====================================================
-- Migracao 058: revogar EXECUTE de anon/authenticated nas
-- funcoes SECURITY DEFINER de escrita/login (linter 0028/0029)
--
-- Contexto: o Security Advisor acusa 9 warnings — cinco funcoes
-- SECURITY DEFINER executaveis por anon e/ou authenticated:
--   fn_importar_reconquista, fn_importar_reconquista_snapshot,
--   fn_lojas_sucessao_apply, fn_upsert_macica, fn_web_login.
--
-- Por que os REVOKEs anteriores nao resolveram: as migrations
-- 020/023/029/053 fizeram apenas `REVOKE ... FROM PUBLIC`. No
-- Supabase, anon/authenticated/service_role recebem EXECUTE em
-- toda funcao nova de public via ALTER DEFAULT PRIVILEGES — e um
-- REVOKE FROM PUBLIC nao remove esses grants DIRETOS. E preciso
-- revogar explicitamente de anon e authenticated (mesmo padrao
-- que a 010 aplicou em fn_web_login para authenticated).
--
-- Quem consome cada funcao (verificado em 2026-07-09):
--   * fn_importar_reconquista / fn_lojas_sucessao_apply:
--     angry-man SEMPRE via service_role — web: Edge Function
--     reconquista-rpc (whitelist + JWT); Electron: IPC com
--     service_role. Script local (scripts/importar_reconquista.py)
--     usa a SUPABASE_KEY service_role do .env.
--   * fn_web_login: web via Edge Function auth-login
--     (service_role); Electron via IPC service_role. NENHUM
--     caminho chama com anon key desde a Edge auth-login — o
--     grant a anon mantido pela 010 ficou obsoleto. O dashboard
--     Streamlit nao usa fn_web_login (auth.py le `usuarios` +
--     bcrypt no Python).
--   * fn_upsert_macica / fn_importar_reconquista_snapshot:
--     zumbis da Reconquista v1 — a 031 (que as dropa) NAO foi
--     aplicada em producao. Nada mais as consome.
--
-- Ordem com a 031: esta migration tolera ambas — as duas funcoes
-- v1 sao revogadas somente se ainda existirem (to_regprocedure).
-- Rodar a 031 depois (destrutiva; apaga historico v1) elimina os
-- objetos de vez; ate la, o REVOKE fecha o buraco.
--
-- Idempotente. Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Funcoes v2 vivas: revogar anon/authenticated,
--    garantir service_role (unico consumidor real)
-- ===========================================

REVOKE EXECUTE ON FUNCTION public.fn_importar_reconquista(JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_importar_reconquista(JSONB)
    TO service_role;

REVOKE EXECUTE ON FUNCTION public.fn_lojas_sucessao_apply(JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_lojas_sucessao_apply(JSONB)
    TO service_role;


-- ===========================================
-- 2. fn_web_login: fechar o grant a anon (obsoleto)
--
-- A 010 manteve anon para o "endpoint de login nao autenticado";
-- esse caminho nao existe mais — todo login passa pela Edge
-- Function auth-login com service_role. Revogar anon zera o
-- warning 0028 sem quebrar login algum.
-- ===========================================

REVOKE EXECUTE ON FUNCTION public.fn_web_login(TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_web_login(TEXT, TEXT)
    TO service_role;


-- ===========================================
-- 3. Zumbis da v1 (se a 031 ainda nao rodou)
-- ===========================================

DO $$
BEGIN
    IF to_regprocedure(
        'public.fn_upsert_macica(text, text, date, date, numeric)'
    ) IS NOT NULL THEN
        REVOKE EXECUTE ON FUNCTION
            public.fn_upsert_macica(TEXT, TEXT, DATE, DATE, NUMERIC)
            FROM PUBLIC, anon, authenticated;
    END IF;

    IF to_regprocedure(
        'public.fn_importar_reconquista_snapshot(uuid, date, jsonb)'
    ) IS NOT NULL THEN
        REVOKE EXECUTE ON FUNCTION
            public.fn_importar_reconquista_snapshot(UUID, DATE, JSONB)
            FROM PUBLIC, anon, authenticated;
    END IF;
END $$;


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- SELECT routine_name, grantee, privilege_type
-- FROM information_schema.role_routine_grants
-- WHERE routine_schema = 'public'
--   AND routine_name IN (
--       'fn_importar_reconquista', 'fn_lojas_sucessao_apply',
--       'fn_web_login', 'fn_upsert_macica',
--       'fn_importar_reconquista_snapshot')
-- ORDER BY routine_name, grantee;
-- Esperado: apenas service_role (e o owner postgres) com EXECUTE;
-- anon/authenticated/PUBLIC ausentes. Depois, re-rodar o Security
-- Advisor: os 9 warnings 0028/0029 devem sumir.
--
-- Smoke test (fluxos que DEVEM continuar funcionando):
--   * login no angry-man (web e Electron);
--   * import de reconquista e sucessao de lojas no angry-man;
--   * scripts/importar_reconquista.py local.
--
-- Reversao (improvavel — so se algum fluxo esquecido usar anon):
--   GRANT EXECUTE ON FUNCTION public.fn_web_login(TEXT, TEXT) TO anon;
--   GRANT EXECUTE ON FUNCTION public.fn_importar_reconquista(JSONB)
--       TO anon, authenticated;
--   GRANT EXECUTE ON FUNCTION public.fn_lojas_sucessao_apply(JSONB)
--       TO anon, authenticated;
-- =====================================================
