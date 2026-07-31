# 2026-07-31 — Responsividade: navegação principal e cards

**Agente:** Claude Code
**Tipo:** bugfix / refactor
**Arquivos tocados:** `app.py`, `assets/dashboard_style.css`,
`src/dashboard/ui/charts.py`, `src/dashboard/ui/prioridades_acao.py`,
`src/dashboard/ui/resumo_executivo.py`,
`src/dashboard/tabs/pagamentos_online.py`
**Commit(s):** (não commitado)

## Objetivo

Auditar a responsividade dos componentes visuais do dashboard. O gatilho
foi a constatação de que abas da navegação principal ficavam ocultas em
telas menores.

## O que foi feito

- **Navegação principal migrada de `sac.tabs` para `st.pills`**
  (`app.py`). Ícones passaram de Bootstrap para Material Symbols
  (`:material/<nome>:`), validados contra
  `streamlit.material_icon_names.ALL_MATERIAL_ICONS`.
- **`.mg-prod-card` e `.mg-kpi-*` viraram containers de consulta**
  (`container-type: inline-size`); tipografia migrada de valor fixo /
  `vw` para `clamp(..., cqi, ...)`.
- **Grids HTML** de `resumo_executivo` e `pagamentos_online` passaram a
  `repeat(auto-fit, minmax(min(Npx, 100%), 1fr))`.
- **Alturas de gráfico** derivadas do conteúdo via
  `_altura_por_conteudo()` em `charts.py`.
- **Bugfix:** ações recomendadas usavam markdown `**negrito**` dentro de
  bloco HTML bruto, renderizando os asteriscos literalmente na tela.

## Decisões não óbvias

- **Por que abandonar `sac.tabs` na nav primária?** O `sac` é um
  componente custom, roda em iframe, e o CSS empacotado na própria lib
  contém `.ant-tabs-nav-more{display:none}` — o botão de overflow do
  antd está escondido. Com 9 abas, as que não cabiam ficavam
  **inacessíveis**, não apenas cortadas. Não há como corrigir do lado do
  app: CSS do documento pai não atravessa o iframe.
- **Por que `st.pills` e não `st.tabs` nativo?** `st.tabs` renderiza o
  conteúdo de **todas** as abas no mesmo rerun (o próprio código já
  registrava isso em `user_mgmt.py:319`). Com 9 renderers e o Supabase
  em plano Nano, seria regressão séria de performance. `st.pills`
  retorna o rótulo selecionado, preservando o render lazy do `sac.tabs`,
  e seu button group nativo já tem `flex-wrap: wrap` — as abas quebram
  em linhas em vez de sumirem.
- **Por que `cqi` em vez de `vw` nos cards?** `st.columns` só empilha
  abaixo de **640px de viewport** (`breakpoints.columns` no bundle do
  Streamlit 1.58) — e é media query de viewport, não de container. Entre
  640px e ~1200px as colunas apenas encolhem. Como `.mg-prod-value`
  tinha `font-size` fixo mais `white-space:nowrap` + `text-overflow:
  ellipsis`, valores longos eram truncados. `cqi` resolve pela largura
  real do card, cobrindo também o carrossel `#mg-mix-scroll`, onde `vw`
  superdimensionava.
- **CSS escopado por `.st-key-nav_principal`** — classe que o Streamlit
  gera para widgets com `key`. Evita que o estilo da nav vaze para
  outros button groups no futuro.
- **O flex das pills não é o `[data-testid="stButtonGroup"]`.** Esse é
  só o wrapper (label + grupo); o flex container é o `> div` filho (Root
  do baseweb), que o Streamlit estiliza com `width:auto` e
  `max-width:fit-content`. Centralizar exige `justify-content:center` +
  `margin-inline:auto` **nesse filho**. E **não** use `width="stretch"`
  no `st.pills` para centralizar: o wrapper de cada botão vira
  `width:100%` e cada pill cai numa linha.
- **Coeficientes `cqi` calibrados por largura de card real, não por
  chute.** A conversão ingênua de `vw` para `cqi` *encolheu* a
  tipografia em telas grandes (ex.: `.mg-kpi-valor` caiu de 52px, o teto
  de `3vw` a 1904px, para ~28px num card de 510px). A régua adotada:
  reproduzir o valor antigo na largura de card de uma tela grande
  (~510px para 3 cards hero, ~395px para 4 cards de contexto, em
  ~1620px de conteúdo) e deixar o teto acima disso, para o texto crescer
  junto com o card em monitores maiores.
- **`.mg-kpi-context` serve três regimes de largura — coeficiente `cqi`
  puro não cobre os três.** Linha `flex:1` (Aceleradores / contexto,
  ~390–530px), carrossel Produtos MIX (travado em 260px) e cards de
  dimensão em `detalhes` (`max-width:300px`). O `7.1cqi` calibrado para
  o primeiro regime jogava os outros dois contra o `min` do `clamp`
  (valor caía de 28px para 18px). Passou a `calc(fixo + Ncqi)`: a
  parcela fixa é o piso legível, o `cqi` é o crescimento. Detalhe que
  invalidava a conta: **`cqi` mede o content box**, não o border box.
- **Media query de viewport anulava a container query.** O
  `@media (max-width:1024px){ .mg-kpi-ctx-sub{font-size:12px} }` era
  inócuo quando a regra base era `vw` (o clamp já batia no piso), mas
  com `cqi` passou a travar o sub em 12px em qualquer card de tablet.
  Reescrito com a mesma fórmula fluida, um degrau abaixo do desktop.
- **Carrossel MIX preso em 260px.** Os cards usavam
  `min-width:clamp(180px,20%,260px); flex-shrink:0` — em 1620px de
  conteúdo sobravam ~240px vazios e a tipografia ficava espremida.
  Trocado por `flex:1 0 clamp(180px,20%,260px); max-width:340px`: grow
  preenche a linha em tela larga, shrink 0 preserva o scroll horizontal
  em tela estreita, `max-width` evita card gigante com poucos produtos.
- **Altura de gráfico é por conteúdo, não por breakpoint de viewport.**
  O Plotly não lê media query: a altura vem do `layout.height` definido
  no servidor, e o servidor não conhece a largura do viewport. A altura
  passou a escalar pelo número de categorias/séries, que é o que de fato
  exige espaço vertical.

## Pendências / follow-ups

- [ ] Validar visualmente pós-login em 768px / 1024px / 1366px — a
      verificação feita foi boot do app (HTTP 200, sem exceção), suíte
      (372 passed) e `ruff check`; a nav só renderiza autenticada.
- [ ] **Código morto a remover (aguarda autorização):** regras
      `.ant-tabs*` em `assets/dashboard_style.css` (seção "Ant Design:
      tabs" e o `:focus-visible` correspondente) nunca se aplicaram — o
      `sac` vive em iframe. Não foram removidas nesta sessão.
- [ ] **Mesmo padrão de linha rígida em outras fileiras de card**
      (`kpi_cards_reforma.py:172` e `:309`, `kpi_cards_pontuacao.py:116`
      e `:204`): `display:flex` sem `flex-wrap` e cards `flex:1`. Abaixo
      de ~1000px os cards espremem em vez de quebrar. Só a fileira de
      Aceleradores foi ajustada nesta sessão (era a pedida). Fix é uma
      linha por fileira: `flex-wrap:wrap` no container e
      `flex:1 1 220px; min-width:0` no card. Aguarda autorização.
- [ ] `sac.tabs` continua em uso em sub-navegações
      (`rankings.py`, `analiticos.py`), com poucos itens. Mesmo risco de
      overflow, menor probabilidade. Avaliar migração se crescerem.
- [ ] Alturas de gráfico realmente por breakpoint de viewport exigiriam
      sondar a largura no cliente (dependência nova) — não instalado.

## Referências

- Docs consultados: [docs/agents/ui-components.md](../ui-components.md),
  [docs/agents/conventions.md](../conventions.md)
