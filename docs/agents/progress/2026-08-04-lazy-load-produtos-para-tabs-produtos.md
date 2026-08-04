# 2026-08-04 — Lazy-load dos meses de comparação movido para `tabs/produtos.py` (ST-09)

**Agente:** Claude Code (`ui-dash`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/tabs/produtos.py`,
`docs/agents/ui-components.md`
**Commit(s):** ver `git log` da branch `refactor/app-py-solid-fase1`
(commit desta ST)

## Objetivo

Fase 1 do refactor SOLID/SRP de `app.py`. O bloco `if tab == "Produtos":`
dentro de `main()` tinha ~95 linhas de lazy-load antes da chamada de
render: dois carregamentos quase idênticos (mês anterior e mesmo mês do
ano anterior), cada um com chave de cache em tupla, `consolidar_dados` +
`aplicar_nomes_display_produto` + `aplicar_rls` + `aplicar_filtros_ui`,
`try/except` com `st.warning`, e memoização em `st.session_state`.
`main()` computava três valores (`df_ant`, `du_dec_ant`, `df_ano_ant`)
que **só** a aba Produtos consome, e os passava prontos.

## O que foi feito

- `_carregar_mes_comparativo(mes, ano, *, prefixo, rotulo)` e
  `_chave_mes_comparativo(mes, ano)` em `src/dashboard/tabs/produtos.py`.
  Os dois blocos viraram duas chamadas:

  ```python
  df_ant = _carregar_mes_comparativo(
      mes_ant, ano_ant, prefixo="_df_ant", rotulo="mês anterior")
  du_dec_ant = calcular_dias_uteis(ano_ant, mes_ant, 1)[0]
  df_ano_ant = _carregar_mes_comparativo(
      mes, ano - 1, prefixo="_df_ano_ant", rotulo="comparativo YoY")
  ```

- **Assinatura de `render_tab_produtos` mudou**: saíram `df_ant`,
  `du_dec_ant` e `df_ano_ant` (3 parâmetros a menos). Ela já recebia
  `mes`/`ano` e já computava `mes_ant`/`ano_ant` para `carregar_feriados`
  — agora computa uma vez só, no topo.
- `app.py`: o branch `if tab == "Produtos":` ficou com um comentário de
  3 linhas + a chamada; sumiram a inicialização morta
  (`df_ant_full = pd.DataFrame()` / `du_dec_ant = 0`) e dois imports que
  ficaram órfãos (`consolidar_dados`, `aplicar_nomes_display_produto`).
  947 → 859 linhas; `tabs/produtos.py` 670 → 785.

## Decisões não óbvias

- **Os dois blocos foram deduplicados numa função só.** Eram idênticos
  exceto por (mes, ano), pelo par de chaves de `session_state` e pelo
  texto da mensagem. Dois parâmetros resolvem: `prefixo` (raiz das duas
  chaves) e `rotulo`. Só **dois** call sites — mas a duplicação aqui é a
  cadeia RLS+filtros, e chave de cache duplicada é justamente o tipo de
  código onde as duas cópias divergem em silêncio e um perfil passa a
  ver dado de outro. Deduplicar reduz essa superfície, não só linhas.
- **`prefixo`, não dois nomes de chave.** As chaves continuam
  `_df_ant_cache` / `_df_ant_chave` / `_df_ano_ant_cache` /
  `_df_ano_ant_chave`, byte a byte — o botão "Atualizar Dados" em
  `app.py` faz `pop` de `_df_ant_cache`/`_df_ant_chave` pelo nome
  literal, e mudar a nomenclatura quebraria isso silenciosamente.
- **A mensagem de log foi harmonizada; a de tela, não.** Os dois
  `st.warning` saem com o texto exato de antes ("…o mês anterior
  (07/2026): …" / "…o comparativo YoY (08/2025): …"), porque é o que o
  usuário lê. O `logger.exception` do YoY passou de "mesmo mês / ano
  anterior" para "comparativo YoY" — mesma informação, um parâmetro a
  menos na assinatura.
- **A chamada fica no topo de `render_tab_produtos`, antes do primeiro
  `sac.divider`.** Preserva a posição do `st.warning` de falha de carga:
  no bloco antigo ele era emitido antes de qualquer render da aba.
- **`_chave_mes_comparativo` chama `_obter_perfil_efetivo()` em vez de
  receber `role`/`perfil_efetivo`.** O módulo já fazia isso duas vezes
  (`render_tab_produtos` e `_render_produto_regional`); manter o mesmo
  idioma evita adicionar dois parâmetros à assinatura pública só para
  reconstruir uma tupla que a função consegue montar sozinha. A tupla
  resultante é idêntica à que `app.py` montava.
- **`logger` de módulo em `tabs/`, primeiro caso.** Nenhum arquivo de
  `tabs/` ou `pages/` tinha logger; o `logger.exception` veio junto com
  o código movido e não podia ser descartado (erro não se engole). É o
  idioma já usado em `app.py` e `loaders.py`.
- **Contrato de tab renderer atualizado em `ui-components.md`.** O doc
  dizia que renderer "não executa queries nem aplica RLS"; esta ST cria
  a primeira exceção deliberada, então o doc ganhou a regra da exceção
  (dado consumido por uma aba só carrega dentro dela, e a chave de cache
  precisa carregar os seis componentes de `_chave_kpis`).

## Validação

- `ruff check src/ app.py` limpo; `pytest tests/` **403 passed** (mesmo
  número de antes da ST).
- **Regressão visual (padrão `AppTest`):** 3 cenários diffados contra
  worktree do commit anterior, `PYTHONHASHSEED=0` nos dois lados.
  **333 linhas de inventário, diff vazio exceto o `sha` cru dos
  `plotly_chart`** — cujo `norm` (mesmo hash sem o campo `id`) é
  idêntico nos 5 gráficos. Ver "Armadilha" abaixo.
  - `admin` → 2 plotly (heatmap + acumulado), 75 markdown, 4 sub-tabs
    (`Emissão`/`Super Conta`/`BMG Med`/`Vida Familiar`), 1 warning e
    1 info pré-existentes (idênticos aos do baseline).
  - `gerente_comercial` (escopo `GLENDA`) → 2 plotly, 101 markdown
    (visão por loja, mais tabelas), mesmas 4 sub-tabs.
  - `consultor` (escopo por nome) → 1 plotly (sem heatmap), 43
    markdown, 0 sub-tabs — a seção regional é pulada para consultor.
  - Nos três: `at.exception` vazio.
- **Prova de que o RLS continua dentro do bloco movido:** as chaves de
  cache no `session_state` saem com o mesmo valor nas duas versões e o
  recorte é visivelmente por perfil —
  `_df_ant_cache` com **6470** linhas (admin), **1288** (gerente
  GLENDA), **143** (consultor); `_df_ant_chave` =
  `(7, 2026, 'consultor', ('ROSIANE …',), (), '')`, isto é, os seis
  componentes na ordem de `_chave_kpis`.

## Armadilha nova: o `id` do proto embute o caminho do `app.py`

`str(node.proto)` de um `plotly_chart` inclui
`id: "$$ID-<hash>-None"`, derivado do `active_script_hash` — que depende
do **caminho** do arquivo. A worktree do baseline e a raiz têm caminhos
diferentes, então esse campo diverge sempre, com o `proto_len`
**idêntico** (é o mesmo número de bytes). Normalizar
(`re.sub(r'id: "\$\$ID-[^"]*"', 'id: "$$ID"', raw)`) antes de hashear.
Mesmo espírito da armadilha do dedent do markdown já documentada.

Duas fontes de ruído a mais, mapeadas no mesmo run:

- `PYTHONHASHSEED` — um `st.json` de dict montado a partir de `set`
  saía com o mesmo `len` e hash diferente **por processo**. Exportar
  `PYTHONHASHSEED=0` nos dois lados elimina.
- `.value` de `UnknownElement` (ex.: `plotly_chart`) levanta `KeyError`
  ao procurar o id no `session_state` — acessar dentro de `try` e cair
  para o `proto`.

## Pendências / follow-ups

- [ ] **Novo (bug pré-existente, não tocado):** o botão "Atualizar
      Dados" em `app.py` faz `pop` de `_df_ant_cache`/`_df_ant_chave`
      mas **não** de `_df_ano_ant_cache`/`_df_ano_ant_chave`. Como a
      chave YoY não muda, o comparativo do ano anterior sobrevive ao
      "Atualizar Dados" e pode ficar velho. Fora do escopo desta ST
      (é correção de comportamento, não refactor) — decisão do usuário.
- [ ] Herdada da ST-01/ST-02/ST-06/ST-08: `main()` monta inline o bloco
      "Período" (expander ano/mês + "Atualizar Dados") e o `st.image` do
      logo — sidebar que não migrou.
- [ ] Herdada da ST-06/ST-08: o bloco de drill-down (`card_page`) dentro
      de `main()` continua candidato natural a extração equivalente.
- [ ] Herdada da ST-02: `IndexError` latente em
      `(_user.get("nome", "").split()[0]) if _user else ""` quando o
      nome é vazio/só espaços.

## Patterns criados ou atualizados

- Atualizado:
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)
  — as três fontes de ruído da seção "Armadilha nova" acima (`id` do
  proto com o caminho do app, `PYTHONHASHSEED`, `.value` de
  `UnknownElement`) viraram itens de "Fazer".

## Referências

- Handoff anterior:
  [2026-08-04-obter-kpis-periodo-extraida.md](2026-08-04-obter-kpis-periodo-extraida.md)
  (ST-07)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/ui-components.md](../ui-components.md),
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)
