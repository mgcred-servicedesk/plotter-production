# 2026-08-04 — Sidebar extraída de `app.py` para `ui/sidebar.py` (ST-01)

**Agente:** Claude Code (`ui-dash`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/ui/sidebar.py` (novo)
**Commit(s):** `f5c5e38` — branch `refactor/app-py-solid-fase1`

## Objetivo

Fase 1 do refactor SOLID/SRP de `app.py`. O topo do arquivo mantinha 8
funções de sidebar (~368 linhas) misturadas com os helpers de `main()`.
Mover para módulo próprio, sem redesenho: extração mecânica.

## O que foi feito

- Novo `src/dashboard/ui/sidebar.py` com as 8 funções. `app.py` cai de
  1591 para 1227 linhas.
- Superfície pública (importada por `app.py`): `render_theme_toggle`,
  `render_sidebar_usuario`, `render_sidebar_visualizar_como`,
  `render_sidebar_filtros_perfil`, `aplicar_filtros_ui`,
  `filtrar_metas_ui`.
- Quatro imports de `app.py` ficaram órfãos e saíram (seriam `F401`):
  `fazer_logout`, `carregar_lojas_ativas`, `get_theme_mode`,
  `set_theme_mode`. `usuario_logado`, `aplicar_rls`, `html`, `pd` e
  `sac` **permanecem** — ainda têm uso fora da sidebar.

## Decisões não óbvias

- **Duas funções continuaram privadas.** A subtarefa pedia tornar as 8
  públicas; `_limpar_filtros_ui` e `_render_consultor_subselect` não têm
  call site fora do módulo, e `ui/` já tem precedente de helper privado
  (`_sparkline_svg` em `kpi_cards.py`, `_MESES_PT` em `header.py`).
  Mantê-las com `_` faz o `import` de `app.py` descrever a API real da
  sidebar em vez de listar detalhe interno. Promover depois é trivial;
  despromover, não.
- **`aplicar_filtros_ui`/`filtrar_metas_ui` moram na sidebar mesmo não
  renderizando nada.** Elas são o *lado leitor* das chaves que a sidebar
  escreve (`ui_filtro_lojas`, `ui_filtro_consultor`). Separá-las em outro
  módulo espalharia o contrato de `session_state` por dois arquivos. O
  contrato completo está documentado no docstring do módulo.
- **Sem ciclo de import.** `ui/sidebar.py` importa `auth`, `loaders`,
  `rls` e `ui/theme`; nenhum deles importa `ui/*`. `loaders` importa
  `rls` e `kpis/*`, o que mantém a direção sidebar → dados.
- **`render_sidebar_visualizar_como` continua sem `st.rerun()`.** O
  comentário que explica isso (a sidebar roda antes do `aplicar_rls`, o
  rerun do widget basta) foi junto — é a razão de a ordem das duas fases
  de sidebar em `main()` ser load-bearing. Não reordenar.
- **Nada dentro de `main()` mudou além dos nomes chamados.** A ST não
  autorizava reorganizar a lógica em volta das chamadas.

## Validação

- `ruff check src/ app.py` limpo; `pytest tests/` 392 passed
  (`test_app_helpers.py` importa `app`, então também prova que a cadeia
  de imports nova resolve).
- **Prova de identidade do código movido:** script comparou o bloco de
  `git show HEAD:app.py` com o módulo novo aplicando só os renomes —
  byte-idêntico.
- **Regressão visual:** inventário headless via
  `streamlit.testing.v1.AppTest` nos cenários `admin`, `gerente_comercial`
  e `supervisor`, diffado contra a worktree do commit anterior —
  idêntico nos três, `at.exception` vazio. Cobre logo, toggle de tema,
  card de usuário, Período, "Atualizar Dados", "Visualizar Como",
  multiselect de Loja e selectbox de Consultor. Estado sujo injetado no
  cenário admin confirmou `_limpar_filtros_ui` rodando.
  Sem credencial de teste no banco: o login foi injetado direto em
  `st.session_state["usuario_logado"]`.

## Pendências / follow-ups

- [ ] `src/dashboard/ui/sidebar.py` não tem teste dedicado. O padrão de
      `AppTest` usado na validação é executável em CI se houver um
      Supabase de teste — hoje ele bate na instância real. Decidir com o
      `test-automation` se vale um smoke test por perfil.
- [ ] `main()` ainda monta inline o bloco "Período" (expander com
      ano/mês + botão "Atualizar Dados"), que é sidebar mas não estava
      no escopo da ST-01. Candidato natural a uma ST futura, junto do
      `st.image` do logo.

## Patterns criados ou atualizados

- Criado:
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)

## Referências

- Handoff anterior:
  [2026-08-04-carregar-periodo-dashboard.md](2026-08-04-carregar-periodo-dashboard.md)
  (ST-05)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/ui-components.md](../ui-components.md)
