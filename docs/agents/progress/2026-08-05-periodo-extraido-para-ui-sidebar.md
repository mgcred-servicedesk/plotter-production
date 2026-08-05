# 2026-08-05 — Bloco "Período" extraído de `main()` para `ui/sidebar.py` (ST-11)

**Agente:** Claude Code (`ui-dash`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/ui/sidebar.py`,
`src/dashboard/ui/header.py`, `src/config/settings.py`,
`src/dashboard/kpis/gerais.py`, `src/dashboard/tabs/produtos.py`,
`tests/test_kpis_gerais.py`
**Commit(s):** ver `git log` da branch `refactor/app-py-solid-fase1`
(commit desta ST)

## Objetivo

ST de acabamento da Fase 1, antes da Fase 2 (OCP). Era o follow-up
aberto na ST-01: `main()` ainda montava inline, dentro do
`with st.sidebar:`, o expander "Período" (default de período +
selectbox de Ano/Mês + botão "Atualizar Dados"). Além da extração, a ST
pedia duas correções de raiz que o bloco carregava:

1. o dicionário de nomes de mês era a **terceira** cópia no codebase e
   divergia das outras duas na grafia ("Marco" sem cedilha);
2. o botão "Atualizar Dados" dava `pop` em seis chaves de
   `session_state` **de outros módulos** pelo nome literal.

## O que foi feito

- Novo `render_periodo(*, on_refresh) -> tuple[int, int]` em
  `src/dashboard/ui/sidebar.py`, com o bloco inteiro. Única função de
  render do módulo que devolve valor — `ano`/`mes` governam o resto de
  `main()` (carga dos frames, header, chaves de cache), então voltam
  pelo `return` e não por `session_state`.
- `main()` fica com uma linha:
  `ano, mes = render_periodo(on_refresh=_limpar_caches_periodo)`.
- `MESES_PT_TITULO` em `src/config/settings.py`, **derivado** de
  `MESES_PT` (`{n: nome.capitalize()}`). `header.py` passou a consumi-lo
  no lugar do `_MESES_PT` local e o dict inline de `app.py` morreu.
- `limpar_cache_kpis(session_state)` em `kpis/gerais.py` (2 pops) e
  `limpar_cache_comparativos()` em `tabs/produtos.py` (4 pops, derivados
  de `_PREFIXOS_COMPARATIVO`).
- `_limpar_caches_periodo()` em `app.py` compõe as duas + o
  `st.cache_data.clear()` + o pop de `_periodo_carregado`.
- `app.py`: 824 → 783 linhas. `carregar_ultimo_periodo` saiu dos imports
  (migrou para a sidebar); entraram `render_periodo`,
  `limpar_cache_kpis` e `limpar_cache_comparativos`.

## Decisões não óbvias

- **O callback `on_refresh` existe por causa de um ciclo de import.** A
  correção "óbvia" — a sidebar importar as duas funções de limpeza — é
  impossível: `tabs/produtos.py` já importa
  `ui/sidebar.py::aplicar_filtros_ui`, então `ui/sidebar` →
  `tabs/produtos` fecharia o ciclo (e `app.py` importa `tabs.produtos`
  **antes** de `ui.sidebar`, então quebraria no boot, não num caso de
  borda). Descartei o import tardio dentro do handler do botão: esconde
  a dependência e mantém a sidebar sabendo *quais* módulos têm cache.
  Com o callback, quem compõe a limpeza é `main()` — que já é o único
  lugar que conhece os três donos — e a sidebar só sabe que houve um
  **pedido** de refresh. Segue o precedente do `on_progress` de
  `carregar_periodo_dashboard`, que é a mesma inversão.
- **`_periodo_carregado` continua removido pelo nome, em `app.py`.** É
  estado do próprio `main()` (trava do skeleton da primeira carga), não
  de um módulo dono — não ganhou função dedicada, conforme o enunciado.
- **As funções de limpeza foram criadas (não simplifiquei para um
  pop-list migrado).** O enunciado dava liberdade para simplificar, mas
  a ST-09 já pagou um bugfix por isso: `_df_ano_ant_*` nasceu no
  lazy-load e só entrou no botão depois, por correção manual
  (`40a0999`). Movido para a sidebar, o pop-list ficaria **mais** longe
  de quem cria as chaves, não menos. Custo real: 2 funções de 3 linhas.
- **`_PREFIXOS_COMPARATIVO` alimenta carga E limpeza.** Os dois call
  sites de `_carregar_mes_comparativo` passaram a usar
  `_PREFIXO_MES_ANT` / `_PREFIXO_ANO_ANT` em vez de literais. É o que
  torna estrutural a correção acima: um terceiro comparativo passa a ser
  limpo de graça, sem ninguém lembrar do botão.
- **`limpar_cache_kpis` recebe `session_state`**, como
  `obter_kpis_periodo`: nenhum módulo de `kpis/` importa Streamlit no
  topo, e assim a função é testável com um `dict` comum.
- **`MESES_PT_TITULO` derivado, não escrito à mão.** Escrever a segunda
  lista capitalizada em `settings.py` recriaria o problema num arquivo
  novo. Derivar de `MESES_PT` torna a divergência de grafia
  impossível. Fecha o follow-up de
  [2026-07-30-gestao-intervalo-de-datas.md](2026-07-30-gestao-intervalo-de-datas.md)
  ("migrar `_MESES_PT` de header.py e o dict inline de app.py — 3 cópias
  hoje"), que pedia a migração quando alguma cópia fosse tocada.
- **⚠️ Mudança visível de comportamento (única):** o mês 3 no selectbox
  agora aparece como **"Março"**, não "Marco". Era a divergência entre
  as cópias; o breadcrumb do header já escrevia "Março" no mesmo rerun,
  e o próprio rótulo do expander já é "Período". Não há como deduplicar
  mantendo as duas grafias.
- **`from datetime import datetime` subiu para o topo de `sidebar.py`.**
  O `from datetime import datetime as _dt` local só existia porque
  `app.py` já tinha `datetime` no escopo do módulo; no módulo novo não
  há colisão.
- **Nada além do bloco mudou em `main()`.** A ST não autorizava
  reorganizar a lógica em volta da chamada.

## Validação

- `.venv/bin/ruff check src/ app.py tests/` limpo.
- `.venv/bin/python -m pytest tests/` → **405 passed** (era 403; +2
  testes de `limpar_cache_kpis`: força recálculo e é idempotente com o
  cache ausente).
- **Prova de identidade do código movido:** script comparou o bloco de
  `git show HEAD:app.py` com o corpo de `render_periodo`; após aplicar
  os **três** deltas intencionais (import de `datetime`, dict inline →
  `MESES_PT_TITULO`, 7 pops → `on_refresh()`), o texto é **idêntico**
  módulo dedent.
- **Regressão visual (padrão `AppTest`):** 4 cenários por versão, um
  processo por versão, `PYTHONHASHSEED=0`, inventário recursivo de
  `at.sidebar` + `at.main` (486 linhas) — `admin`, `gerente_comercial`
  (escopo `GLENDA`), `supervisor` (escopo `HELP BANGU`) e um cenário de
  clique em "Atualizar Dados". `at.exception` vazio nos 4, nas 2
  versões. **O diff acusa só as 4 linhas do rótulo "Marco" → "Março"**
  (uma por cenário) — o expander sai na mesma posição
  (`sb/sidebar[6]`), com os mesmos widgets, `options` de Ano
  (`2024/2025/2026`), valores (`ano=2026`, `mes=8`) e a mesma
  `key`/`help` do botão.
- **Cenário de clique — caches envenenados.** Depois do primeiro run,
  os *valores* de `_kpis_cache`, `_df_ant_cache` e `_df_ano_ant_cache`
  foram trocados por sentinelas **mantendo as chaves reais**
  (`_kpis_chave` etc.): se o botão não evictasse, a chave bateria e a
  sentinela sobreviveria ao rerun. Nas duas versões, após o clique:
  `SENTINELA_KPIS_SOBREVIVEU = False` e os dois comparativos voltaram
  com 30 colunas reais (não a coluna `SENTINELA`). Cobre os 6 nomes —
  inclusive o par YoY do bugfix `40a0999`, que **não** regrediu.

### Ruído mapeado (não é regressão)

O elemento `st.json(diag['mapa_pontos'])` do diagnóstico de pontuação
(admin) sai com **hash diferente e `len` idêntico (208)** entre
processos. Provado como não-determinismo do dado, não do código:
rodando o inventário **duas vezes no mesmo baseline**, a linha diverge
igual (`b1 admin=75924e0047` × `b2 admin=e1312b5264`), e um script
isolado extraiu o payload das duas versões byte a byte igual. É a ordem
das chaves do mapa vinda da RPC, que não tem `ORDER BY`. Antídoto para
a próxima ST: quando um único elemento divergir, **rode o baseline duas
vezes antes de investigar o próprio diff**.

## Pendências / follow-ups

- [ ] O `st.image` do logo continua inline no `with st.sidebar:` — era o
      outro item da pendência da ST-01. Sozinho é uma linha; vale mover
      só se `render_periodo`/`render_sidebar_usuario` ganharem um
      `render_sidebar()` guarda-chuva (decisão de Fase 2).
- [ ] `_diag_pontuacao` é sobrescrito pelo `consolidar_dados` do mês
      anterior (chamado dentro da aba Produtos): o dict que fica no
      `session_state` ao fim do rerun **não** é o que foi renderizado.
      Não afeta a tela (o expander renderiza antes), mas confunde quem
      inspeciona o estado. Fora do escopo desta ST.
- [ ] Herdada da ST-01: `ui/sidebar.py` continua sem teste dedicado.
      `render_periodo` é o candidato mais fácil (default de período +
      `on_refresh` chamado uma vez), se houver Supabase de teste.

## Patterns criados ou atualizados

- Atualizado:
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)
  — seção nova sobre envenenar o cache mantendo a chave (discrimina
  eviction de recarga) e sobre rodar o baseline duas vezes para separar
  ruído de dado do diff de código.

## Referências

- Handoff anterior:
  [2026-08-05-drilldown-de-cards-extraido-para-pages-detalhes-cards.md](2026-08-05-drilldown-de-cards-extraido-para-pages-detalhes-cards.md)
  (ST-10)
- Follow-up fechado:
  [2026-07-30-gestao-intervalo-de-datas.md](2026-07-30-gestao-intervalo-de-datas.md)
  (as 3 cópias de `MESES_PT`)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/ui-components.md](../ui-components.md),
  [docs/agents/conventions.md](../conventions.md)
