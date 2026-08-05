# 2026-08-04 — CSS/HTML inline de `main()` extraído para `ui/theme.py` (ST-02)

**Agente:** Claude Code (`ui-dash`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/ui/theme.py`,
`docs/agents/ui-components.md`
**Commit(s):** ver `git log` da branch `refactor/app-py-solid-fase1`
(commit desta ST)

## Objetivo

Fase 1 do refactor SOLID/SRP de `app.py`. O início de `main()` injetava
dois blocos de CSS/HTML via `st.markdown(..., unsafe_allow_html=True)`
(~68 linhas de markup dentro da função de orquestração). Mover para
`ui/theme.py`, sem redesenho: extração mecânica.

## O que foi feito

- `ocultar_widgets_nativos()` — CSS que esconde `stMainMenu`,
  `stAppDeployButton` e `stStatusWidget`.
- `render_overlay_fresh_login(nome)` — overlay de transição pós-login.
- `app.py` cai de 1227 para 1166 linhas; `theme.py` sobe de 432 para 526.
- `import html` saiu de `app.py` (ficou órfão — só o overlay usava) e
  entrou em `theme.py`.

## Decisões não óbvias

- **A decisão ficou no chamador; só o markup migrou.** `main()` mantém
  `if _perfil_logado != "admin":` e o `st.session_state.pop("_fresh_login")`.
  Alternativa descartada: `ocultar_widgets_nativos(perfil)` com
  early-return e overlay lendo `usuario_logado()` por dentro — faria
  `theme.py` (hoje importa **só** `streamlit` + `html`) depender de
  `src.dashboard.auth` e passar a conhecer regra de perfil. Um módulo de
  estilo não deve saber quem é admin.
- **`render_*` e não `aplicar_*` para o overlay.** `theme.py` usa verbo
  em português (`aplicar_tema`, `carregar_estilos_customizados`), e
  `ocultar_widgets_nativos` segue essa linha. Para o overlay valeu o
  prefixo `render_*` do resto de `ui/` (`render_header`,
  `render_theme_toggle`): é um componente visível, não configuração de
  tema, e o nome mantém a amarração com a chave `_fresh_login`.
- **A indentação do CSS mudou (12 → 8 espaços) e isso é visível no
  markdown do hide-widgets.** É artefato de nesting (saiu de dentro de
  `if` dentro de `main()`). Manter 12 espaços preservaria o hash bruto,
  mas destoaria de `aplicar_tema()` no mesmo arquivo. O overlay **não**
  muda de hash: sua string começa com `\n`, então todas as linhas têm
  prefixo comum e o dedent do `st.markdown` remove a indentação inteira;
  a do hide-widgets começa com `<style>` na linha 1 (prefixo comum zero),
  então o dedent é no-op e a diferença sobrevive. Diferença provada
  whitespace-only (abaixo).
- **Nada mais dentro de `main()` mudou.** Comentários que explicavam o
  *markup* foram para os docstrings; os que explicam a *decisão*
  (gate por perfil, consumo da flag) ficaram no call site.

## Validação

- `ruff check src/ app.py` limpo; `pytest tests/` **392 passed**
  (mesmo número da ST-01).
- **Prova de identidade do CSS movido:** literal extraído por AST de
  `git show HEAD:app.py` comparado com o que a função nova emite —
  `antigo.replace(' '*12, ' '*8) == novo` → `True`, e idêntico removendo
  todo whitespace. `unsafe_allow_html=True` preservado.
- **Regressão visual (padrão `AppTest`):** dois cenários, cada um
  cobrindo duas das quatro condições da ST, diffados contra worktree do
  commit anterior:
  - `nao_admin_fresh` (gerente_comercial + `_fresh_login=True`) →
    hide-widgets **presente** (1 bloco), overlay **presente** (1 bloco),
    texto `Bem-vindo, Fulano!` (primeiro nome, escapado). 39 blocos de
    markdown. Diff bruto: **1 linha** — o hash cru do bloco de
    hide-widgets; hash normalizado por whitespace **idêntico**
    (`e0821178da37`, len 140).
  - `admin_semfresh` (admin, sem flag) → hide-widgets **ausente** (0),
    overlay **ausente** (0). 79 blocos de markdown (render completo do
    dashboard). Diff **vazio**.
  - `at.exception` vazio nos quatro runs. Login injetado em
    `st.session_state["usuario_logado"]` (sem credencial no banco).

## Pendências / follow-ups

- [ ] **Bug latente pré-existente, preservado de propósito:** em
      `main()`, `(_user.get("nome", "").split()[0]) if _user else ""`
      levanta `IndexError` se o usuário existir com `nome` vazio ou só
      espaços (`"".split()` → `[]`). Não estava no escopo da ST-02
      (extração mecânica), então o comportamento foi mantido byte a
      byte. Correção sugerida: `(_user.get("nome") or "").split()` com
      guarda de lista vazia. Decidir com o dono do fluxo de auth.
- [ ] O `sha1` bruto do markdown como critério de diff tem falso
      positivo garantido quando a extração muda o nível de aninhamento
      **e** a string não começa com `\n`. O pattern
      `validar-refactor-de-ui-com-apptest.md` foi atualizado com a
      contramedida (emitir hash bruto + normalizado).
- [ ] Herdada da ST-01, ainda aberta: `main()` monta inline o bloco
      "Período" (expander ano/mês + "Atualizar Dados") e o `st.image` do
      logo — sidebar que não migrou.

## Patterns criados ou atualizados

- Atualizado:
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)
  — seção sobre hash bruto vs. normalizado e o dedent do `st.markdown`.

## Referências

- Handoff anterior:
  [2026-08-04-sidebar-extraida-para-ui-sidebar.md](2026-08-04-sidebar-extraida-para-ui-sidebar.md)
  (ST-01)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/ui-components.md](../ui-components.md)

> Nota de divergência: a entrada da ST-01 cita o commit `f5c5e38`, mas o
> commit correspondente na branch é `c7230c9` (provável rebase/amend
> posterior). Registrado aqui por ser append-only — a entrada anterior
> não foi editada.
