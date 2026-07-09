-- =====================================================
-- Migracao 059: consolidar policies RLS de pagamentos_online
-- (linter 0006 multiple_permissive_policies)
--
-- Contexto: o Performance Advisor acusa 5 warnings (um por role)
-- em pagamentos_online — duas policies permissivas avaliadas em
-- TODA linha de todo SELECT:
--   pol_pagamentos_online_admin  (FOR ALL,    perfil = 'admin')
--   pol_pagamentos_online_gestor (FOR SELECT, perfil = 'gestor')
--
-- A migration 011 ja consolidou as demais tabelas no padrao
-- "uma policy de SELECT com OR + (SELECT obter_perfil_atual())"
-- (initplan: a funcao roda 1x por query, nao 1x por linha por
-- policy). pagamentos_online nasceu depois (014) e ficou fora.
-- Esta migration aplica o mesmo padrao — semantica identica:
--   SELECT: admin OU gestor (fail-closed p/ demais perfis);
--   INSERT/UPDATE/DELETE: apenas admin.
--
-- Obs: o ETL (angry-man) escreve via Edge Functions com
-- service_role, que BYPASSA RLS — estas policies sao a camada
-- defense-in-depth do modelo client-side, como em contratos.
--
-- BEGIN/COMMIT: atomico — entre DROP e CREATE o RLS fica
-- fail-closed (nega, nao vaza), mas a transacao elimina a janela.
--
-- Depende de: 014_pagamentos_online.sql aplicada.
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

DROP POLICY IF EXISTS pol_pagamentos_online_admin
    ON public.pagamentos_online;
DROP POLICY IF EXISTS pol_pagamentos_online_gestor
    ON public.pagamentos_online;

CREATE POLICY pol_pagamentos_online_select
    ON public.pagamentos_online FOR SELECT
    USING ((SELECT obter_perfil_atual()) IN ('admin', 'gestor'));

CREATE POLICY pol_pagamentos_online_admin_insert
    ON public.pagamentos_online FOR INSERT
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_pagamentos_online_admin_update
    ON public.pagamentos_online FOR UPDATE
    USING ((SELECT obter_perfil_atual()) = 'admin')
    WITH CHECK ((SELECT obter_perfil_atual()) = 'admin');

CREATE POLICY pol_pagamentos_online_admin_delete
    ON public.pagamentos_online FOR DELETE
    USING ((SELECT obter_perfil_atual()) = 'admin');

COMMIT;


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- SELECT policyname, cmd, qual
-- FROM pg_policies
-- WHERE schemaname = 'public' AND tablename = 'pagamentos_online'
-- ORDER BY policyname;
-- Esperado: 4 policies (select / admin_insert / admin_update /
-- admin_delete), nenhuma dupla para o mesmo cmd. Re-rodar o
-- Performance Advisor: os 5 warnings 0006 devem sumir.
--
-- Reversao (volta ao estado da 014):
--   DROP POLICY IF EXISTS pol_pagamentos_online_select       ON public.pagamentos_online;
--   DROP POLICY IF EXISTS pol_pagamentos_online_admin_insert ON public.pagamentos_online;
--   DROP POLICY IF EXISTS pol_pagamentos_online_admin_update ON public.pagamentos_online;
--   DROP POLICY IF EXISTS pol_pagamentos_online_admin_delete ON public.pagamentos_online;
--   CREATE POLICY pol_pagamentos_online_admin
--       ON public.pagamentos_online FOR ALL
--       USING (obter_perfil_atual() = 'admin');
--   CREATE POLICY pol_pagamentos_online_gestor
--       ON public.pagamentos_online FOR SELECT
--       USING (obter_perfil_atual() = 'gestor');
-- =====================================================
