# 2026-05-11 — RLS na tabela `feriados`

**Agente:** Windsurf
**Tipo:** bugfix (segurança)
**Arquivos tocados:** `database/migrations/008_rls_feriados.sql` (novo)
**Commit(s):** —

## Objetivo

Resolver alerta de segurança do Supabase: `Table public.feriados is
public, but RLS has not been enabled`. A tabela foi criada na migration
005 sem `ENABLE ROW LEVEL SECURITY`, ficando exposta via PostgREST.

## O que foi feito

- Criada migration `008_rls_feriados.sql` que:
  - Habilita RLS em `feriados`.
  - Cria `pol_feriados_leitura` (`SELECT USING (true)`) — leitura pública.
  - Cria `pol_feriados_admin` (`FOR ALL`, restrito a `obter_perfil_atual() = 'admin'`) com `WITH CHECK` simétrico.
- Migration é idempotente (`DROP POLICY IF EXISTS` antes de cada `CREATE POLICY`).

## Decisões não óbvias

- **Leitura pública (`USING true`) em vez de restringir por perfil** —
  `_carregar_feriados_cached` em `src/shared/dias_uteis.py` é usado por
  todos os perfis para calcular dias úteis (dashboard + relatórios).
  Restringir leitura quebraria o cálculo para gestor/gerente/supervisor/
  consultor. Espelha o padrão de `regioes`, `lojas`, `produtos`,
  `pontuacao` em `schema.sql:1044-1075`.
- **Escrita só para admin** — A UI `src/dashboard/feriados_mgmt.py` é
  ferramenta de gestão; gestor não foi incluído (escolha do usuário,
  mais restritivo, alinhado a `usuarios`/`usuario_escopos`).
- **Não alterei `005_tabela_feriados.sql`** — migrations são append-only;
  fix vai em nova migration numerada.
- **`WITH CHECK` no policy `FOR ALL`** — evita que admin consiga
  inserir/atualizar linha que ele mesmo não conseguiria ler depois (não
  aplicável aqui porque `USING` é igual, mas é boa prática explícita).

## Pendências / follow-ups

- [ ] Aplicar a migration no Supabase SQL Editor (produção).
- [ ] Confirmar no painel **Authentication → Policies** que `feriados`
      mostra RLS habilitado + 2 policies.
- [ ] Auditar outras tabelas criadas em migrations (não no `schema.sql`)
      para garantir que todas têm RLS — varredura rápida sugerida nas
      migrations 001-007.

## Patterns criados ou atualizados

- Nenhum pattern novo. Reaproveita o padrão "tabela de referência"
  documentado em `schema.sql` (leitura `USING true` + escrita
  restrita por `obter_perfil_atual()`).

## Referências

- Alerta Supabase: e-mail "Action required" sobre `public.feriados` sem RLS.
- Docs consultados: [docs/agents/rls.md](../rls.md), `database/schema.sql:1044-1097`, `database/migrations/006_perfil_consultor.sql`.
