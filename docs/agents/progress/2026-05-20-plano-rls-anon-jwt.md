# 2026-05-20 — Plano: migrar app de `service_role` para `anon` + JWT/GUC

**Agente:** Claude Code
**Tipo:** research / plano
**Arquivos tocados (deste registro):** apenas este doc.
**Commit(s):** —

## Objetivo

Sair do modelo atual (cliente Supabase singleton com `service_role` bypassando RLS, autorização aplicada apenas em pandas via `src/dashboard/rls.py`) para um modelo onde:

1. O app usa apenas a chave `anon`.
2. Cada requisição carrega contexto do usuário logado, lido pelas policies RLS já existentes em `database/schema.sql`.
3. Operações que precisam de `service_role` ficam isoladas em scripts offline.

## Estado atual (mapeamento)

- **Cliente:** `src/config/supabase_client.py` é singleton module-level; lê `SUPABASE_KEY` de `st.secrets["database"]` ou `.env`. Hoje o valor é `service_role` por convenção (documentado em `database/INTEGRACAO.md:35`).
- **Consumidores do cliente:** `src/dashboard/loaders.py`, `auth.py`, `feriados_mgmt.py`, `user_mgmt.py`, `src/shared/dias_uteis.py`, `dashboard_supabase.py`, `scripts/seed_admin.py`, `scripts/fix_supervisores_usuario_nome.py`, `scripts/diagnostico/*`, `gerar_relatorio*.py`, `corrigir_produto_id.py`, `debug_data.py`, `diagnostico_pontos.py`.
- **Banco — bom estado:** funções `obter_usuario_atual_id()` e `obter_perfil_atual()` (`database/schema.sql:955-994`) leem GUC via `current_setting('app.current_user_id', true)` / `current_setting('app.current_user_perfil', true)`. Policies já existem em `contratos`, `metas`, `feriados`, `usuarios`, `usuario_escopos` (migration `011`). Views `v_contratos_dashboard` e `contratos_pagos` usam `security_invoker=on` (migration `004`).
- **Banco — o que falta:** ninguém seta os GUCs. Hoje o `service_role` bypassa tudo e as policies só são exercitadas em fluxos pontuais (e.g. `fn_web_login`).
- **Tabelas de dimensão** (`regioes`, `lojas`, `consultores`, `supervisores`, `periodos`, `categorias_produto`, `produtos`, `pontuacao`): RLS habilitado com policy `USING (true)` — leitura aberta para qualquer um autenticado.
- **Autorização em Python:** `src/dashboard/rls.py` filtra DataFrames via `.isin()` por `REGIAO`/`LOJA`/`CONSULTOR` após o fetch. Suporta "visualizar como".
- **Cache:** `@st.cache_data` em `loaders.py` chaveia por `(mes, ano)`. **Não diferencia usuário** — risco crítico se trocarmos para RLS sem ajustar.

## Abordagem recomendada — JWT próprio + `db-pre-request` (variante de "b" + "c")

Trade-offs avaliados:

| Opção | Prós | Contras |
|---|---|---|
| (a) Migrar para Supabase Auth | JWT real, refresh nativo | Reescrever login (bcrypt → email/senha do Auth); migrar `usuarios.id` para `auth.users`; usuários atuais não têm email. Maior superfície de mudança. |
| (b) Emitir JWT próprio com claim `role=authenticated` + `sub=user_id` | Idiomático Supabase; PostgREST aceita `Authorization: Bearer <jwt>`; preserva login bcrypt | Requer `SUPABASE_JWT_SECRET` no app; precisa rotação manual; policies hoje leem GUC e não `auth.jwt()`. |
| (c) RPC `set_app_context()` por request com GUC | Aproveita 100% das policies e funções existentes; sem JWT | Streamlit roda script inteiro a cada interação — precisa rodar antes de toda chamada. PostgREST não mantém estado entre requests. |

**Decisão recomendada:** combinar (b) e (c).
1. Emitir JWT próprio mínimo no `autenticar()` do app — assinado com `SUPABASE_JWT_SECRET`, claims `role=authenticated, sub=<usuario.id>, user_perfil=<perfil>`, TTL ~12h.
2. Configurar `db-pre-request` no Supabase (Settings → API) chamando uma função `app.set_context_from_jwt()` que lê `request.jwt.claims->>'sub'` e faz `set_config('app.current_user_id', ..., true)`.

Resultado: policies existentes funcionam sem mudança; refresh é simples (re-emitir no login); só introduzimos `SUPABASE_JWT_SECRET` como nova variável de ambiente (segredo do projeto Supabase, já existe).

Fallback se `db-pre-request` não estiver disponível no plano: chamar RPC `set_app_context()` manualmente como primeira chamada de cada loader.

## Policies — inventário

| Tabela / view | RLS | SELECT | Escrita | Ação |
|---|---|---|---|---|
| `contratos` | sim | OK (m011) | admin-only | nada |
| `metas` | sim | OK (m011) | admin-only | nada |
| `feriados` | sim | leitura pública | admin-only | nada |
| `usuarios`, `usuario_escopos` | sim | self + admin | admin-only | nada |
| `regioes`, `lojas`, `consultores`, `supervisores`, `periodos`, `categorias_produto`, `produtos`, `pontuacao` | sim | `USING (true)` | sem policy de escrita | **decidir:** restringir escrita explicitamente ou aceitar bloqueio implícito (RLS habilitado sem policy = nega). |
| `v_contratos_dashboard`, `contratos_pagos`, `v_pontuacao_efetiva` | invoker | herda | n/a | nada |
| RPCs `obter_pontuacao_periodo`, `obter_contratos_em_analise`, `obter_contratos_cancelados` | ? | precisa auditar `SECURITY DEFINER` vs `INVOKER` | n/a | **auditar na Fase 0** |

## Fases de migração

### Fase 0 — Auditoria SQL (1 dia, sem mudança em prod)
- Listar declaração `SECURITY` de cada RPC consumida pelo app.
- Listar todas as policies via `pg_policies`.
- Confirmar como `fn_web_login` é invocada hoje (edge function? RPC direto?).
- Confirmar disponibilidade de `db-pre-request` no projeto.

### Fase 1 — Infraestrutura de contexto (banco + emissor JWT, sem cutover)
- Migration: função `app.set_context_from_jwt()` + configuração de `db-pre-request` (ou variante manual).
- Migration: ajustar RPCs problemáticas para `SECURITY INVOKER` (ou aplicar `obter_usuario_atual_id()` internamente).
- App: instalar `PyJWT`; emitir JWT em `autenticar()`; guardar em `st.session_state["jwt"]`.

### Fase 2 — Cliente per-request (atrás de feature flag)
- Refatorar `get_supabase_client()` para aceitar `jwt: str | None`. Quando presente, cliente novo com header `Authorization: Bearer <jwt>` e `apikey: <anon>`.
- Flag `USE_RLS_DB` em `settings.py` para rollback rápido.
- Testar em staging com `SUPABASE_KEY=anon` e flag ligada. Validar cada perfil (admin, gestor, gerente_comercial, supervisor, consultor) e "visualizar como".

### Fase 3 — Cache key por usuário
- Mudar assinatura das funções `@st.cache_data` em `loaders.py` para incluir `usuario_id`, `perfil`, `escopo_hash`.
- Wrapper público lê `usuario_logado()` e passa as chaves.
- Considerar reduzir TTL (cache cresce N× usuários).
- `st.cache_data.clear()` no logout e ao alternar "visualizar como".
- **Pré-requisito** absoluto para a Fase 4 — sem isso, sessões podem ver cache de outras.

### Fase 4 — Cutover em produção
- Trocar `SUPABASE_KEY` em `st.secrets` para a chave `anon`.
- Manter `src/dashboard/rls.py` ativo como defense-in-depth (~1 mês).
- Atualizar `database/INTEGRACAO.md` para nova arquitetura.

### Fase 5 — Isolar scripts admin
- Criar `src/config/supabase_admin_client.py` lendo `SUPABASE_SERVICE_KEY` (variável separada).
- Migrar `scripts/seed_admin.py`, `scripts/fix_*`, `scripts/diagnostico/*`, `gerar_relatorio*.py`, `corrigir_produto_id.py`, `debug_data.py`, `diagnostico_pontos.py`.
- Documentar: o app NUNCA importa o admin client.

## Arquivos previstos para tocar

**Banco**
- `database/migrations/014_app_set_context.sql` (nova)
- `database/migrations/015_rpcs_security_invoker.sql` (nova — só se Fase 0 confirmar necessidade)
- `database/INTEGRACAO.md` (atualizar)

**App**
- `src/config/supabase_client.py` (refatorar para per-JWT)
- `src/config/supabase_admin_client.py` (novo, para scripts)
- `src/config/settings.py` (flag `USE_RLS_DB`, `SUPABASE_JWT_SECRET`)
- `src/dashboard/auth.py` (emitir/invalidar JWT)
- `src/dashboard/loaders.py` (cache key por usuário; cliente per-request)
- `src/dashboard/feriados_mgmt.py`, `user_mgmt.py`, `src/shared/dias_uteis.py`
- `src/dashboard/rls.py` (mantido; opcional log/alerta se filtro remover linhas — sintoma de cache vazado)
- Scripts em `scripts/`, `gerar_relatorio*.py`, `corrigir_produto_id.py`, `debug_data.py`, `diagnostico_pontos.py`, `dashboard_supabase.py` (apontar para admin client)
- `requirements.txt` (adicionar `PyJWT`)
- `docs/agents/rls.md` (atualizar)

**Testes**
- `tests/` — novos testes de integração com JWT mock por perfil.

## Riscos & mitigações

1. **`db-pre-request` indisponível** → fallback RPC `set_app_context()` manual.
2. **Cache vazado entre usuários** → Fase 3 obrigatória antes da Fase 4. Bloquear cutover até 100% das `@st.cache_data` chavearem por usuário.
3. **JWT expirado em sessão longa** → re-emitir silenciosamente se faltar <30min, ou TTL ~12h e forçar re-login.
4. **Performance de policies em `contratos`** → migration 011 já usou `(SELECT obter_perfil_atual())` pattern para initplan. Validar com `EXPLAIN ANALYZE` em staging para gerente_comercial com várias regiões.
5. **"Visualizar Como"** (admin/gestor simulam outro perfil) → emitir JWT temporário com claim adicional `impersonated_by` para auditoria. Necessário decidir formato.
6. **Scripts batch quebrando** se trocarmos key antes da Fase 5 → migrar scripts para admin client primeiro.
7. **`PyJWT` no Streamlit Cloud** → validar redeploy e versão.
8. **Login antes do JWT existir** → `fn_web_login` precisa ser callable por anon. Confirmar fluxo atual.

## Pendências / follow-ups

- [ ] Fase 0 — auditoria SQL (descritivo acima).
- [ ] Responder perguntas em aberto (próxima seção) com o usuário antes de codar.
- [ ] Estimar duração de cada fase com o time.
- [ ] Definir ambiente de staging (atualmente parece não existir um isolado — todas as keys hoje apontam para o mesmo projeto Supabase).

## Perguntas em aberto

1. `db-pre-request` está disponível neste projeto Supabase (Settings → API)?
2. `fn_web_login` é chamada via Edge Function (service_role) ou direto do app (anon)? Confirmar.
3. Aceitamos leitura aberta de `consultores`/`lojas`/`supervisores`/`regioes` para qualquer autenticado, ou restringimos por escopo do usuário?
4. TTL do JWT: 8h, 12h, ou refresh silencioso?
5. "Visualizar Como" — registrar auditoria em tabela?
6. Como distribuir `SUPABASE_JWT_SECRET` no Streamlit Cloud (`st.secrets`)?
7. Por quanto tempo manter `src/dashboard/rls.py` ativo como defense-in-depth depois do cutover?
8. Há outros consumidores do banco (BI externo, integrações) que dependem de `service_role`?

## Referências

- Achados da auditoria de segurança realizada na mesma sessão (2026-05-20):
  - XSS em `app.py:170-181` (corrigido com `html.escape()`)
  - `st.exception` em `app.py:1352-1354` (corrigido — log interno)
  - `.env.example*` e `README_STREAMLIT_CLOUD.md` recomendavam `service_role` (corrigido — passam a recomendar `anon`)
- Docs consultados: `database/schema.sql:955-994`, `database/migrations/011`, `database/migrations/004`, `database/INTEGRACAO.md:35`, `docs/agents/rls.md`.
