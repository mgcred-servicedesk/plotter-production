# 2026-08-18 — Responsividade: sub-navegações migradas de `sac.tabs` para `st.pills`

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/tabs/analiticos.py`,
`src/dashboard/tabs/rankings.py`, `assets/dashboard_style.css`,
`src/dashboard/ui/theme.py`, `docs/agents/ui-components.md`
**Commit(s):** (não commitado)

## Objetivo

Usuário reportou que, depois que a sub-aba **Cobrança Consignável** entrou
em Analíticos, a sub-aba **Distribuição de Produtos** ficou escondida em
telas de resolução menor. Pediu avaliação de responsividade.

## O que foi feito

- **Três sub-navegações migradas de `sac.tabs` para `st.pills`**, com o
  padrão já documentado da nav principal:
  - `analiticos.py` — sub-nav de Analíticos (7 itens, o bug reportado),
    `key="nav_analiticos"`;
  - `rankings.py` — sub-nav de Rankings (até 5 itens, mesmo bug latente),
    `key="nav_rankings"`;
  - `analiticos.py` — sub-tabs internas de Reconquista (2 itens, migrada
    por uniformidade), `key="nav_reconquista"`.
- **Ícones Bootstrap → Material Symbols**, validados contra
  `streamlit.material_icon_names.ALL_MATERIAL_ICONS`. Mapas em constantes
  de módulo (`_ICONES_ANALITICOS`, `_ICONES_RECONQUISTA`,
  `_ICONES_RANKINGS`).
- **Bloco de CSS único para sub-navs** em `dashboard_style.css`, cobrindo
  as três chaves `.st-key-nav_*`.
- **`docs/agents/ui-components.md`**: a seção "Tabs" documentava
  `sac.tabs` como o padrão de sub-navegação — passou a marcar o
  componente como não usado em lugar nenhum, e ganhou a subseção de
  sub-navegação.
- **Código morto removido** (autorizado pelo usuário na mesma sessão,
  em duas rodadas — ver "Remoção de código morto" abaixo): ~85 linhas de
  regras `.ant-*` em `dashboard_style.css` e 6 regras `.ant-tabs-*` na
  injeção de tema em `theme.py`.

## Decisões não óbvias

- **Não é problema de largura/CSS — não existe correção de CSS.** O `sac`
  roda em iframe e a própria lib empacota
  `.ant-tabs-nav-more{display:none}` (verificado no pacote instalado:
  `streamlit_antd_components/frontend/build/static/css/main.d8bbe754.chunk.css`).
  É o botão de overflow do antd. Escondido, o que não cabe fica
  **inacessível**, não apenas cortado — e CSS do documento pai não
  atravessa o iframe.
- **Isto era um follow-up previsto**, em
  [2026-07-31-responsividade-nav-e-cards.md](2026-07-31-responsividade-nav-e-cards.md):
  *"`sac.tabs` continua em uso em sub-navegações (`rankings.py`,
  `analiticos.py`) … Avaliar migração se crescerem."* Cresceram.
- **O critério "poucos itens, estáveis" foi abandonado, não reajustado.**
  Era o critério que autorizava `sac.tabs` em sub-navs. Analíticos tinha
  6 itens "estáveis" até Cobrança Consignável entrar. Item novo é
  exatamente o que ninguém prevê, e o modo de falha é **silencioso** —
  não quebra, não loga, a aba só deixa de existir para quem tem tela
  pequena. Um critério que depende de prever o crescimento não é
  critério. Zero call sites de `sac.tabs` restam.
- **Por que `st.pills` e não `st.tabs`?** Mesma razão de 2026-07-31:
  `st.tabs` renderiza o conteúdo de **todas** as abas no mesmo rerun. Com
  o Supabase em Nano, seria regressão séria — a sub-nav de Analíticos tem
  7 renderers. O `st.pills` devolve o rótulo, então o `if/elif` de
  despacho **não mudou** e o render segue lazy.
- **Sub-nav é o mesmo componente, um degrau menor.** Alinhada à esquerda
  (o `sac.tabs` daqui usava `align="start"`) e tipografia menor, para
  preservar a hierarquia contra a nav primária, que é centralizada. Por
  isso o bloco de sub-nav **não** repete `justify-content:center` +
  `margin-inline:auto`.
- **Um bloco de CSS listando as três chaves, não três blocos.** O estilo
  de sub-nav é um só; duplicar por chave garantiria divergência. Custo: o
  seletor é explícito (`.st-key-nav_*` não existe em CSS), então sub-nav
  nova exige acrescentar a chave no bloco — registrado em
  `ui-components.md`.
- **`rocket_launch` em Aceleradores, não `bolt`.** `bolt` é a tradução
  literal do antigo `lightning-charge`, mas já é o ícone da aba principal
  Pagamentos Online. Escolha do usuário entre as opções apresentadas.
- **Chave da sub-tab de Reconquista mudou** (`acel_reconquista_tabs` →
  `nav_reconquista`), para entrar no seletor compartilhado. Descarta o
  estado de navegação em sessões abertas no deploy — cai no `default`
  ("Por Loja"), sem erro.

## Remoção de código morto

Feita **depois** da migração, com autorização explícita do usuário. O
escopo cresceu durante a investigação, e isso é o mais importante aqui.

- **`assets/dashboard_style.css`: todas as regras `.ant-*` removidas**
  (~85 linhas — tabs, divider e segmented). O stylesheet do pai não tem
  mais nenhuma. Motivo: o `sac` roda em iframe, então (a) o seletor do
  documento pai nunca casa e (b) `var(--mg-*)` também não atravessa, por
  serem herdadas pela árvore do documento. **Dupla morte.**
- **`src/dashboard/ui/theme.py`: 6 regras `.ant-tabs-*` removidas** da
  injeção JS. Essa injeção **é viva** (alcança `iframe.contentDocument`),
  mas as regras de tabs ficaram sem alvo quando o último `sac.tabs` saiu.
  As de `.ant-divider*` / `.ant-segmented*` permanecem — esses componentes
  seguem em uso.

### Decisões não óbvias da remoção

- **A prova de que o CSS do pai nunca aplicou está no próprio codebase.**
  A injeção em `theme.py` hardcoda hex literal
  (`tc = isDark ? '#F5F4F2' : '#1F2937'`) em vez de usar `var(--mg-text)`.
  Isso só faz sentido se as vars não chegam lá dentro — e se elas não
  chegam, o bloco `.ant-*` do stylesheet nunca teve como funcionar, mesmo
  onde o seletor existia. O workaround já estava lá, documentando o
  problema sem dizer o nome dele.
- **Escopo maior que o flagado em 2026-07-31.** Aquela sessão flagou só a
  seção de tabs. O mesmo mecanismo condena divider e segmented, que nunca
  foram flagados — foram removidos após confirmação em separado, por
  serem componentes ainda em uso (a diferença: quem os estiliza é o
  `theme.py`, não o stylesheet; efeito visual esperado da remoção é zero).
- **⚠️ O `:focus-visible` flagado em 2026-07-31 NÃO era código morto e
  foi mantido.** A entrada daquela sessão diz "a seção 'Ant Design: tabs'
  **e o `:focus-visible` correspondente**". A regra em questão é
  `[data-testid="stTabs"] button:focus-visible`, que mira o `st.tabs`
  **nativo** do Streamlit — vivo, em `user_mgmt.py:323` e
  `produtos.py:1178`. Não tem relação com `sac`. Quem for reler aquela
  entrada não deve apagá-la.
- **Nenhuma var ficou órfã.** `--mg-text-secondary`, `--mg-secondary-bg`,
  `--mg-bg` e `--mg-shadow` eram usadas pelas regras removidas e seguem
  com 11, 10, 6 e 2 usos respectivamente.

## Pendências / follow-ups

- [ ] **Validar visualmente pós-login em 768px / 1024px / 1366px, nos
      dois temas.** A verificação feita foi: `ruff check` limpo, suíte
      completa (565 passed) e boot do app (HTTP 200, sem exceção no log).
      **A suíte não cobre navegação nem CSS** — `test_tabs_analiticos.py`
      testa `_opcoes_coluna` e hierarquia de produto. É regressão-guard,
      não cobertura do que mudou. A nav só renderiza autenticada.
      Confirmar em tela dois pontos distintos: (a) as sub-navs quebram em
      linhas em vez de esconder itens; (b) `sac.divider` e
      `sac.segmented` seguem corretos em claro/escuro após a remoção das
      regras `.ant-*` do stylesheet (efeito esperado: nenhum).
- [x] ~~Código morto `.ant-*`~~ — **resolvido nesta sessão**, com escopo
      maior que o previsto. Ver "Remoção de código morto" acima.
- [ ] Herdado de 2026-07-31, ainda aberto: fileiras de card com
      `display:flex` sem `flex-wrap` (`kpi_cards_reforma.py:172` e `:309`,
      `kpi_cards_pontuacao.py:116` e `:204`).

## Referências

- Precedente: commit `58bb028` (`fix(ui): make main nav and KPI cards
  responsive across screen sizes`) — mesma troca, na nav primária.
- Docs consultados: [docs/agents/ui-components.md](../ui-components.md),
  [docs/agents/conventions.md](../conventions.md),
  [2026-07-31-responsividade-nav-e-cards.md](2026-07-31-responsividade-nav-e-cards.md)
