# 2026-05-11 — Warnings de Performance e Info do Supabase

**Agente:** Windsurf
**Tipo:** refactor (segurança/performance)
**Arquivos tocados:**
- `database/migrations/011_consolidar_rls_policies.sql` (novo)
- `database/migrations/012_indexes_foreign_keys.sql` (novo)

**Commit(s):** —
**Status:** ⚠️ **PRONTOS PARA APLICAR — testar perfis após 011**

## Objetivo

Resolver 29 alertas do Supabase Linter (24 WARN + 5 INFO):

- **24 `multiple_permissive_policies`** em `contratos`, `metas`,
  `feriados`, `usuarios`, `usuario_escopos`.
- **5 `unindexed_foreign_keys`** em `consultores`, `lojas`, `metas`,
  `supervisores` (2 FKs).
- **6 `unused_index`** (Grupo C) — apenas documentado, sem ação.

Sem impacto na funcionalidade primordial do `angry-man` de subir dados
(usa `service_role`, que tem `BYPASSRLS` e não passa por policies).

## O que foi feito

### Migration 011 — consolidação de RLS

Para cada tabela com `pol_X_admin FOR ALL` + outras policies SELECT:

1. Substituir `FOR ALL` por 3 policies separadas: `INSERT`, `UPDATE`,
   `DELETE` (admin only) com `WITH CHECK` quando aplicável.
2. Consolidar todas as condições de SELECT em uma **única** policy com
   OR (admin OR gestor OR gerente AND escopo OR ...).
3. Trocar `obter_perfil_atual()` por `(SELECT obter_perfil_atual())`
   para forçar avaliação via initplan (1× por query, não por linha).

Tabelas cobertas: `contratos`, `metas`, `feriados`, `usuarios`,
`usuario_escopos`.

Resultado por tabela: **1 policy SELECT + 3 policies de escrita** em
vez de N policies sobrepostas.

### Migration 012 — covering indexes

Adiciona 5 índices `IF NOT EXISTS` para cobrir FKs sem índice:

- `consultores.loja_id`
- `lojas.regiao_id`
- `metas.loja_id`
- `supervisores.loja_id`
- `supervisores.regiao_id`

## Decisões não óbvias

- **Por que não dropar índices unused (Grupo C)?** — Métricas do
  Supabase só capturam desde a última instalação/restart. Vários dos
  índices flagados são recentes (006, 005). Reavaliar em 1-2 meses.
- **Por que `(SELECT obter_perfil_atual())` em vez de chamada direta?**
  — Postgres trata subquery escalar como initplan: avalia 1× e
  reutiliza. Chamada direta é avaliada por linha, mesmo com função
  STABLE. Padrão recomendado pelo Supabase (lint `auth_rls_initplan`).
- **Por que separar admin em 3 policies (INSERT/UPDATE/DELETE)?** — Se
  mantivéssemos `FOR ALL`, o overlap com a policy SELECT consolidada
  reapareceria em SELECTs. Separar elimina sobreposição e mantém o
  controle granular.
- **`feriados` e `usuarios`/`usuario_escopos`** — São casos mais
  simples (só admin + leitura/proprio). Mesmo padrão aplicado por
  consistência.
- **Comportamento RLS preservado** — Mudança é refactor de **forma**.
  Mesma lógica, só consolidada. Mas é sensível: testar cada perfil
  pós-aplicação é obrigatório.

## Pendências / follow-ups

- [ ] Aplicar `011_consolidar_rls_policies.sql` no Supabase SQL Editor.
- [ ] Aplicar `012_indexes_foreign_keys.sql` no Supabase SQL Editor.
- [ ] **Teste funcional crítico após 011**: logar com cada perfil
      (admin, gestor, gerente_comercial, supervisor, consultor) e
      validar que cada um vê apenas os dados esperados em `contratos`
      e `metas`. Sem isso, pode haver vazamento ou bloqueio indevido.
- [ ] Validar com queries do bloco "Validacao manual" no fim de cada SQL.
- [ ] Rodar o linter do Supabase de novo para confirmar que os 29
      alertas (5 + 24) sumiram.
- [ ] **Reavaliar Grupo C em ~1-2 meses**: se índices listados abaixo
      continuarem sem uso, considerar drop.
      - `idx_feriados_ano_mes`
      - `idx_usuario_escopos_consultor_id`
      - `idx_usuario_escopos_regiao_id`
      - `idx_usuario_escopos_loja_id`
      - `idx_produtos_categoria_id`
      - `idx_usuarios_perfil`

## Patterns criados ou atualizados

Padrão emergente (a documentar futuramente em `docs/agents/patterns/`):
**RLS performante no Supabase**:

1. Uma policy por `cmd` por tabela (consolidar via OR).
2. Sempre envolver chamadas de função em `(SELECT fn())` para initplan.
3. `FOR ALL` só em tabelas com policy única; tabelas com policies
   adicionais por perfil devem usar policies por `cmd`.

## Referências

- `docs/supabase-performance-adivsor.md` — fonte dos 24 warnings.
- `docs/supabase-info.md` — fonte dos 11 INFOs (5 FKs + 6 unused).
- Supabase docs: <https://supabase.com/docs/guides/database/database-linter>
- Schema atual: `database/schema.sql:976-1096`.
- Policies de consultor: `database/migrations/006_perfil_consultor.sql:96-129`.
