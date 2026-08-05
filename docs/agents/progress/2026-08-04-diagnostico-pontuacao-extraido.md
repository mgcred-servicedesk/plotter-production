# 2026-08-04 — Diagnóstico de pontuação extraído para `pages/dashboard_pontuacao.py` (ST-08)

**Agente:** Claude Code (`ui-dash`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`,
`src/dashboard/pages/dashboard_pontuacao.py`,
`docs/agents/patterns/validar-refactor-de-ui-com-apptest.md`
**Commit(s):** ver `git log` da branch `refactor/app-py-solid-fase1`
(commit desta ST)

## Objetivo

Fase 1 do refactor SOLID/SRP de `app.py`. O bloco
`if diag and _is_admin:` dentro de `main()` renderizava inline o
expander admin-only de diagnóstico do mapeamento de pontuação (métricas,
categorias no contrato × na RPC, mapa de pontos, tipos sem categoria,
categorias sem match). Mover para uma função dedicada, sem redesenho:
extração mecânica.

## O que foi feito

- `render_diagnostico_pontuacao(diag)` em
  `src/dashboard/pages/dashboard_pontuacao.py`.
- `main()` fica com o gate + a chamada:

  ```python
  diag = st.session_state.get("_diag_pontuacao")
  if diag and _is_admin:
      render_diagnostico_pontuacao(diag)
  ```

- `app.py`: 1128 → 1085 linhas. Nenhum import ficou órfão (`pd` segue
  com dezenas de usos); o único import novo entra no bloco que já
  existia para `render_dashboard_pontuacao`.

## Decisões não óbvias

- **Destino: `pages/dashboard_pontuacao.py`, não módulo novo.** O
  critério foi tema (é sobre a mesma pontuação) contra custo (um módulo
  inteiro para ~45 linhas). Alternativas descartadas:
  `pages/diagnostico.py` — módulo novo para uma função só; e
  `ui/diagnostico_pontuacao.py` — semanticamente o lugar mais exato
  (é componente inline, não página), mas paga o mesmo custo e ainda
  adiciona uma linha de import em `app.py`. **Tensão registrada:** o
  docstring de `pages/__init__.py` define o pacote como "páginas
  autônomas", e o diagnóstico não substitui o dashboard — renderiza
  inline, e antes do dispatch de view, então aparece nas duas views
  (vendas e pontuação) para admin. O docstring do módulo diz isso em
  voz alta; se outros diagnósticos surgirem, promover a módulo próprio.
- **O gate ficou em `main()`.** Mesma linha editorial da ST-02/ST-06:
  o módulo renderiza, `app.py` decide *quando*. `diag and _is_admin`
  combina duas coisas que a função não deveria conhecer — a existência
  do side-effect no `session_state` e a regra de perfil.
- **`st.dataframe` não virou `exibir_tabela`.** `ui-components.md`
  permite `st.dataframe` direto fora de renderers de tab, e trocar
  mudaria formatação/estilo — mudança de comportamento fora do escopo
  de uma extração mecânica.
- **A função recebe `diag` por parâmetro, não lê o `session_state`.**
  Mantém o único leitor de `_diag_pontuacao` no codebase em `app.py`
  (o único escritor continua sendo `consolidar_dados`, loaders.py).

## Validação

- `ruff check src/ app.py` limpo; `pytest tests/` **392 passed** (mesmo
  número da ST-01/ST-02/ST-06).
- **Prova de identidade do bloco movido:** o `with st.expander(...)`
  extraído por AST de `git show HEAD:app.py` comparado com o corpo de
  `render_diagnostico_pontuacao` (menos o docstring) — 47 linhas nos
  dois, `textwrap.dedent` **byte a byte igual** (`True`), `ast.dump`
  idêntico, 16 statements no `with`. O `if` continua no **mesmo índice**
  (9 de 62) do corpo do `try` de `main()`.
- **Regressão visual (padrão `AppTest`):** 3 cenários diffados contra
  worktree do commit anterior — **diff vazio nos três** (inclusive nos
  hashes crus de markdown; mover um `with` não altera os literais de
  markdown, que são de linha única):
  - `admin_diag_sintetico` → expander
    `Diagnostico de pontuacao — 8/10 contratos com pontos`, 3 `metric`
    (10 / 2 / 8), 2 `code` (`CARTAO_X, CONSIG_BMG, FGTS` e
    `CONSIG_BMG, FGTS`), 1 `json` (mapa), 2 `warning` (tipos sem
    categoria + `1 categorias sem pontuacao: CARTAO_X`), 1 `dataframe`
    (1×2, `tipo`/`qtd`), 75 blocos de markdown. O dict sintético cobre
    **todos** os ramos do bloco de uma vez.
  - `admin_sem_diag` → 0 metric / code / json / warning / dataframe,
    expander ausente, `_diag_pontuacao` ausente do `session_state`.
  - `nao_admin_com_diag` (`gerente_comercial`) → `_diag_pontuacao`
    **presente** no `session_state` e mesmo assim 0 metric / code /
    json / warning / dataframe: prova que o gate de perfil corta o
    render.
  - Nos três: `at.exception` vazio.

## Pendências / follow-ups

- [ ] Herdada da ST-01/ST-02/ST-06: `main()` monta inline o bloco
      "Período" (expander ano/mês + "Atualizar Dados") e o `st.image` do
      logo — sidebar que não migrou.
- [ ] Herdada da ST-02: `IndexError` latente em
      `(_user.get("nome", "").split()[0]) if _user else ""` quando o
      nome é vazio/só espaços.
- [ ] Herdada da ST-06: o bloco de drill-down (`card_page`) dentro de
      `main()` espelha o padrão da config (botão de voltar + `return`) e
      é candidato natural a uma extração equivalente.
- [ ] Novo: o diagnóstico renderiza **antes** do dispatch de view, então
      aparece nas duas (vendas e pontuação). Comportamento preservado da
      versão anterior — se isso for indesejado, é mudança de
      comportamento e precisa de decisão do usuário, não de refactor.

## Patterns criados ou atualizados

- Atualizado:
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)
  — chave escrita *durante* o run (side-effect de loader) não se injeta
  antes do `at.run()`: patchar a função no módulo, com
  `sys.path.insert(0, dirname(app_alvo))` antes do primeiro
  `import src.…`. E: vários cenários podem dividir um processo (mesma
  versão do app), o que deixa o `cache_data` quente.

## Referências

- Handoff anterior:
  [2026-08-04-pagina-config-extraida-para-pages-config.md](2026-08-04-pagina-config-extraida-para-pages-config.md)
  (ST-06)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/ui-components.md](../ui-components.md),
  [docs/agents/conventions.md](../conventions.md)
