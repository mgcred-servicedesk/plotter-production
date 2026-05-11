# 2026-05-11 — Restringir EXECUTE em `fn_admin_import`

**Agente:** Windsurf
**Tipo:** bugfix (segurança)
**Arquivos tocados:** `database/migrations/009_revoke_fn_admin_import.sql` (novo, **rascunho — não aplicado**)
**Commit(s):** —
**Status:** ⚠️ **PENDENTE — não aplicar até migrar `angry-man`**

## Risco em aberto (importante)

Enquanto a migration não for aplicada, **a `anon key` do projeto Supabase
funciona como chave de admin disfarçada**: qualquer pessoa que tenha
acesso ao bundle do `angry-man` (front-end) pode chamar
`POST /rest/v1/rpc/fn_admin_import` e:

- inserir/sobrescrever dados em qualquer tabela alvo da função;
- usar `p_delete_where` para apagar registros;
- bypassar RLS (a função roda como `SECURITY DEFINER`).

Decisão consciente do usuário em 2026-05-11: **manter como está** porque
fix imediato quebra o pipeline de importação. Tratar como dívida técnica
de segurança alta prioridade.

## Objetivo

Resolver alerta do Supabase: `fn_admin_import` é `SECURITY DEFINER` e
está chamável via `/rest/v1/rpc/fn_admin_import` pela `anon` role,
permitindo importação/sobrescrita de dados sem autenticação.

## O que foi feito

- Migration 009 revoga `EXECUTE` de `PUBLIC`, `anon` e `authenticated`.
- Concede `EXECUTE` explicitamente a `service_role`.
- Mantém `SECURITY DEFINER` (intencional para bypass controlado de RLS
  na importação em massa).

## Decisões não óbvias

- **Por que não trocar para `SECURITY INVOKER`?** — A função é chamada
  pelo backend de importação com `service_role`, que bypassa RLS de
  qualquer modo; trocar para `INVOKER` não muda nada na prática mas
  perde a semântica explícita "essa função roda elevada".
- **Por que não mover para schema fora do `public`?** — Seria a
  alternativa mais robusta (PostgREST não expõe schemas não listados
  em `db.schemas`), mas exigiria refatorar o projeto de importação que
  vive fora deste repo. Revogar `EXECUTE` resolve o alerta com
  superfície mínima.
- **A função vive em outro projeto** — Não há código dela neste repo
  (`grep` confirmou). Migration documenta a assinatura esperada
  (`text, jsonb, text, jsonb`) com base no alerta do Supabase.

## Pendências / follow-ups

- [ ] **Bloqueante**: migrar `angry-man` para chamar `fn_admin_import`
      a partir de um backend usando `service_role` (hoje usa `anon`
      direto do front-end). Alternativas:
      - Backend dedicado (Node/Python/Edge Function) que valida sessão
        de admin e repassa para a RPC com `service_role`.
      - Edge Function do próprio Supabase com `SUPABASE_SERVICE_ROLE_KEY`.
- [ ] Após migração de `angry-man`, aplicar `009_revoke_fn_admin_import.sql`.
- [ ] Validar com a query do bloco "Validacao manual" no fim do SQL —
      esperado: apenas `service_role` (e owner) com EXECUTE.
- [ ] Testar o pipeline de import após o revoke.
- [ ] Auditar outras funções `SECURITY DEFINER` em `public` com
      EXECUTE para `PUBLIC` — query sugerida:
      ```sql
      SELECT n.nspname, p.proname, p.prosecdef
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public' AND p.prosecdef = true;
      ```

## Patterns criados ou atualizados

- Nenhum pattern novo. Padrão recomendável (a documentar futuramente):
  funções `SECURITY DEFINER` em `public` devem sempre revogar `EXECUTE`
  de `PUBLIC` e conceder explicitamente apenas aos roles que precisam.

## Referências

- Alerta Supabase: "Function public.fn_admin_import ... can be executed by the anon role".
- Migration relacionada: `database/migrations/004_views_security_invoker.sql` (mesmo tema, em views).
