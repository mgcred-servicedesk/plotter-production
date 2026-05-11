# 2026-05-11 — Restringir EXECUTE em `fn_web_login`

**Agente:** Windsurf
**Tipo:** bugfix (segurança)
**Arquivos tocados:** `database/migrations/010_revoke_fn_web_login_authenticated.sql` (novo, **rascunho — não aplicado**)
**Commit(s):** —
**Status:** ⚠️ **PENDENTE — validar fluxos do `angry-man` antes de aplicar**

## Objetivo

Resolver 2 dos 4 warnings do Supabase Advisor:

- `fn_web_login` callable por `anon` (warning 3) — **intencional** (login).
- `fn_web_login` callable por `authenticated` (warning 4) — **indevido**.

Os outros 2 warnings (`fn_admin_import` × anon/authenticated) já estão
cobertos pela migration 009 (também rascunho).

## Contexto

- Função `fn_web_login(p_usuario text, p_senha text)` vive no projeto
  `angry-man`. Não há código dela neste repo (`grep` confirmou).
- Este dashboard MGCred **não** usa `fn_web_login` —
  `src/dashboard/auth.py` autentica direto na tabela `usuarios` com
  bcrypt.
- Por ser função de login, `EXECUTE` para `anon` é necessário e
  intencional. Não cabe revogar.

## O que foi feito

- Migration 010 (rascunho):
  - `REVOKE EXECUTE FROM PUBLIC, authenticated`.
  - `GRANT EXECUTE TO anon` (idempotente, garante login funcionando).
  - Mantém `SECURITY DEFINER` (a função lê `senha_hash` bypassando RLS).
- Comentários no SQL listam recomendações fora desta migration:
  mensagem genérica em falha + rate limiting.

## Decisões não óbvias

- **Por que manter `anon`?** — Login por definição é chamado por usuário
  não autenticado. Revogar quebra o `angry-man`.
- **Por que revogar `authenticated`?** — Usuário com JWT válido não
  precisa fazer login de novo. Reduz superfície de ataque (ex.: token
  comprometido sendo usado para descobrir credenciais de outros).
- **`GRANT EXECUTE TO anon` no fim** — Defensivo. Caso o `REVOKE FROM
  PUBLIC` tenha removido o grant herdado por anon em alguma versão do
  Postgres, o `GRANT` explícito garante operação.
- **Marcar warning 3 como "intentional" no Supabase Advisor** — Após
  aplicar a migration, o warning 3 (anon) deve permanecer. Recomenda-se
  dismiss/acknowledge no painel.

## Pendências / follow-ups

- [ ] **Bloqueante**: validar no `angry-man` que nenhum fluxo chama
      `fn_web_login` com JWT autenticado (refresh, troca de conta,
      re-login). Se houver, refatorar antes.
- [ ] Aplicar `010_revoke_fn_web_login_authenticated.sql`.
- [ ] Validar com a query de "Validacao manual" no fim do SQL —
      esperado: apenas `anon` (e owner) com EXECUTE.
- [ ] Marcar warning 3 (`fn_web_login` × anon) como intencional no
      Supabase Advisor.
- [ ] **No projeto `angry-man` (fora deste repo)**:
      - Confirmar que `fn_web_login` retorna mensagem genérica em falha.
      - Implementar rate limiting via Edge Function ou proxy.

## Patterns criados ou atualizados

- Nenhum pattern novo. Padrão emergente (a documentar futuramente):
  funções `SECURITY DEFINER` em `public` devem ter `EXECUTE` concedido
  apenas aos roles estritamente necessários para sua função.

## Referências

- Alertas Supabase: warnings 3 e 4 sobre `public.fn_web_login`.
- Progress relacionado: `2026-05-11-revoke-fn-admin-import.md` (mesmo tema, função `fn_admin_import`).
- Migration relacionada: `database/migrations/009_revoke_fn_admin_import.sql`.
