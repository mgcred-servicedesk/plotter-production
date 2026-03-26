-- =====================================================
-- Migracao 004: Corrigir SECURITY DEFINER nas views
--
-- O Supabase cria views como SECURITY DEFINER por padrao,
-- o que faz a view rodar com as permissoes do criador,
-- ignorando RLS do usuario que consulta.
--
-- Corrige para SECURITY INVOKER (respeita RLS do caller).
--
-- Executar no Supabase SQL Editor.
-- =====================================================

ALTER VIEW public.v_contratos_dashboard
    SET (security_invoker = on);

ALTER VIEW public.v_contratos_em_analise
    SET (security_invoker = on);

ALTER VIEW public.v_contratos_cancelados
    SET (security_invoker = on);
