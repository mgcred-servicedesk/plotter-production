# Componentes de UI

## streamlit-antd-components (sac)

Biblioteca externa (não faz parte do Streamlit padrão). Import:

```python
import streamlit_antd_components as sac
```

### Divider — separar seções lógicas

Usar entre **toda** seção lógica. Nunca empilhar grupos de KPI sem divider.

```python
sac.divider(label="Analise de Produtos", icon="bar-chart-line", align="left", color="blue")
```

- `color`: `"blue"` (primário), `"gray"` (secundário/tabela), `"green"`, `"orange"`.
- `icon`: Bootstrap Icons (`bar-chart-line`, `box`, `geo-alt`, `trophy`, `heart-pulse`, `shop`, `people`, `table`, …).

### Tabs — sub-navegação dentro de uma aba

```python
tab = sac.tabs(
    items=[
        sac.TabsItem(label="Lojas",       icon="shop"),
        sac.TabsItem(label="Consultores", icon="people"),
    ],
    align="start",
    variant="outline",
    use_container_width=True,
)
```

⚠️ **Não usar `sac.tabs` na navegação primária.** O `sac` roda dentro de
um iframe e o CSS empacotado na lib tem
`.ant-tabs-nav-more{display:none}` — o botão de overflow do antd está
escondido, então as abas que não cabem na largura ficam **inacessíveis**
(não apenas cortadas). CSS do documento pai não atravessa o iframe, logo
não há correção possível do lado do app. Use `sac.tabs` apenas onde o
número de itens é pequeno e estável.

### Navegação primária — `st.pills`

A nav principal do `app.py` usa `st.pills`, não `sac.tabs`:

```python
tab = st.pills(
    "Navegacao principal",
    options=rotulos_visiveis,
    default=rotulos_visiveis[0],
    required=True,                       # nunca cair sem aba selecionada
    format_func=lambda r: f":material/{icones_aba[r]}: {r}",
    label_visibility="collapsed",
    key="nav_principal",
)
if tab == "Produtos":
    ...
```

- O button group nativo tem `flex-wrap: wrap` — as abas **quebram em
  linhas** em vez de sumirem quando não cabem.
- Retorna o rótulo selecionado, então o **render é lazy** (só o branch
  ativo executa). `st.tabs` nativo **não** serve aqui: renderiza o
  conteúdo de todas as abas no mesmo rerun.
- Ícones são Material Symbols (`:material/<nome>:`), não Bootstrap.
  Nomes válidos: `streamlit.material_icon_names.ALL_MATERIAL_ICONS`.
- Estilo em `assets/dashboard_style.css`, escopado por
  `.st-key-nav_principal` (classe que o Streamlit gera para widgets com
  `key`).
- ⚠️ O flex container **não** é o `[data-testid="stButtonGroup"]` (esse
  é só o wrapper label + grupo), e sim o `> div` filho. Para centralizar
  as pills: `justify-content: center` + `margin-inline: auto` **nesse
  filho**. Não use `width="stretch"` para isso — o wrapper de cada botão
  vira `width: 100%` e cada pill cai numa linha.

### Segmented — sub-seleção dentro de uma aba

```python
sel = sac.segmented(
    items=[
        sac.SegmentedItem(label="Lojas",       icon="shop"),
        sac.SegmentedItem(label="Consultores", icon="people"),
    ],
    align="start",
    use_container_width=False,
)
tipo = "loja" if sel == "Lojas" else "consultor"
```

## Tabelas — `exibir_tabela`

Em renderers de tab **nunca** usar `st.dataframe` diretamente. Sempre:

```python
from src.dashboard.components.tables import exibir_tabela

exibir_tabela(df)
exibir_tabela(df, colunas_moeda=["VALOR"], colunas_numero=["pontos"])
```

`exibir_tabela` aplica formatação PT-BR automática, `hide_index=True`,
`width="stretch"` e estilos consistentes com o design system.

Exceção: fora de renderers de tab (ex.: breakdowns rápidos em
`_render_tab_em_analise`) pode-se usar `st.dataframe` direto, sempre com
`width="stretch"` e `hide_index=True`.

## Tab renderer pattern

Cada aba é uma função pública `render_tab_*` em `src/dashboard/tabs/*.py`
(um arquivo por aba: `produtos.py`, `regioes.py`, `rankings.py`,
`analiticos.py`, `evolucao.py`, `em_analise.py`, `detalhes.py`,
`consultor.py`). `app.py` importa e despacha conforme o item
selecionado em `sac.tabs`. Contrato:

- Recebe todos os DataFrames já filtrados (pós-RLS) e os parâmetros de período.
- Chama funções de `src/dashboard/kpis/*.py` para KPIs e
  `src/dashboard/ui/charts.py` para figuras.
- Renderiza com `sac.divider` → gráfico → divider → tabela.
- **Não** executa queries nem aplica RLS (já foi feito em `app.py`).

**Exceção — dado que só uma aba consome.** Quando um DataFrame é usado
por uma única aba, ele é carregado *dentro* dela (lazy), não em
`app.py`: quem está em outra aba não paga a query nem a consolidação.
Nesse caso a aba executa a cadeia inteira — `consolidar_dados` →
`aplicar_nomes_display_produto` → `aplicar_rls` → `aplicar_filtros_ui` —
e memoiza o resultado em `st.session_state` sob uma chave que **precisa**
carregar os mesmos seis componentes de `_chave_kpis` (período, perfil
efetivo, escopo, filtro de lojas ordenado, filtro de consultor): a chave
é a fronteira entre perfis. Único caso hoje:
`tabs/produtos.py::_carregar_mes_comparativo` (mês anterior e mesmo mês
do ano anterior, para as curvas do gráfico acumulado e do heatmap).

```python
# src/dashboard/tabs/produtos.py
def render_tab_produtos(df, df_metas_produto, categorias, ano, mes, dia_atual, df_sup, ...):
    sac.divider(label="Analise de Produtos", icon="box", align="left", color="blue")

    df_prod = calcular_kpis_por_produto(df, df_metas_produto, categorias, ano, mes, dia_atual, df_sup)
    fig = criar_grafico_produtos(df_prod)
    st.plotly_chart(fig, width="stretch")

    sac.divider(label="KPIs por Produto", icon="table", align="left", color="gray")
    exibir_tabela(df_prod)
```

Gating de render é centralizado em `src/dashboard/permissions.py`:
`app.py` só inclui uma aba em `sac.tabs` se `pode_ver(chave, role)`
retorna `True`.

## Messages

```python
st.success("OK")
st.info("Info")
st.warning("Atenção")
st.error("Erro")
```

Preferir `st.info` com prefixo `📌 **Resumo:**` para notas explicativas
(padrão observado em breakdowns BMG Med/Vida Familiar).

## Session state

```python
if "key" not in st.session_state:
    st.session_state.key = default_value

st.session_state.key = new_value
st.rerun()  # força rerun após mudança de estado
```

## Tema

Sistema de tema via CSS custom properties + localStorage, implementado
em `src/dashboard/ui/theme.py`:

- `get_theme_mode()` — modo escolhido: `"light"` | `"dark"` | `"system"`
  (default `"system"`).
- `set_theme_mode(mode)` — persiste o modo; invalida tema cacheado se
  `"system"`.
- `get_theme()` — tema ativo derivado do mode (`"light"` | `"dark"`).
  Em `"system"` lê do JS via query param `_theme`.
- `aplicar_tema()` — injeta variáveis CSS `--mg-*` e `--st-*`, sincroniza
  tema nativo do Streamlit.
- `carregar_estilos_customizados()` — carrega `assets/dashboard_style.css`.
- `ocultar_widgets_nativos()` — esconde menu ⋮, botão de deploy e status
  widget. Esconde os três **individualmente**: ocultar
  `[data-testid="stHeader"]` inteiro leva junto o
  `stExpandSidebarButton` e deixa a sidebar sem como reabrir. Quem
  decide *para quem* ocultar é o chamador (`app.py` aplica a não-admins).
- `render_overlay_fresh_login(nome)` — overlay de transição pós-login
  (fade-out por animação CSS, sem rerun). O chamador consome a flag
  `_fresh_login` de `st.session_state`; o módulo não conhece perfil.
- `CHART_COLORS` / `_CHART_THEME` / `_NATIVE_THEME` — paletas para Plotly
  e tema nativo. Todas OKLCH-aproximadas em hex (Streamlit não suporta
  `oklch()` em `config.toml`).

`app.py` chama `carregar_estilos_customizados()` e `aplicar_tema()` no
início de `main()`. O segmented toggle na sidebar (☀/🖥/🌙) alterna entre
os 3 modos e chama `st.rerun()`. Toda cor de gráfico **deve** vir do
`CHART_COLORS` (ver [conventions.md](conventions.md)).

### Design tokens (CSS custom properties)

Todos os componentes consomem tokens `--mg-*` definidos em
`_CSS_VARS` (theme.py) e injetados no `:root`:

**Cores de superfície:**
- `--mg-bg` — app background (warm neutral light / warm black dark)
- `--mg-surface` — card / surface background
- `--mg-surface-elevated` — popovers, tooltips, dropdowns
- `--mg-sidebar-bg` — background da sidebar

**Texto:**
- `--mg-text` — corpo principal
- `--mg-text-muted` — rótulos, captions, secundário
- `--mg-text-subtle` — terciário, hints

**Bordas:**
- `--mg-border` — separadores sutis, bordas de cards
- `--mg-border-strong` — inputs, hover de cards

**Accent + estados:**
- `--mg-primary`, `--mg-primary-hover`, `--mg-primary-soft`,
  `--mg-primary-ring`
- `--mg-success` / `--mg-warning` / `--mg-danger` (+ variantes `-soft`)

**Sombras (elevation system em camadas):**
- `--mg-shadow-xs` — cards em repouso, status widgets
- `--mg-shadow-sm` — cards default
- `--mg-shadow-md` — cards hover, chart-card hover, hero default
- `--mg-shadow-lg` — popovers, hero hover

**Radius / spacing:**
- `--mg-radius-sm` (6px) / `--mg-radius-md` (8px) /
  `--mg-radius-lg` (12px) / `--mg-radius-xl` (16px)
- `--mg-space-xs` (4) / `sm` (8) / `md` (12) / `lg` (16) /
  `xl` (24) / `2xl` (32) / `3xl` (48)

Novos componentes **devem** consumir esses tokens; nunca hardcode cores
ou sombras em CSS ou HTML inline.

### KPI cards (`.mg-prod-card`)

Sistema unificado em `src/dashboard/ui/kpi_cards.py`. Variantes:

| Classe | Uso |
|---|---|
| `.mg-prod-card` | Base neutra |
| `.mg-prod-card--hero` | KPI principal destacado (Total Pago) |
| `.mg-prod-card--success/warning/danger` | Status por meta |
| `.mg-prod-card--mix` | KPI primário / mix geral |
| `.mg-prod-card--neutral` | KPI informativo sem meta |

Aliases `.mg-prod-card--accent-teal/indigo` redirecionados para
`--neutral` (mantidos para backwards compat).

Sparklines: helper `_sparkline_svg(values, width=180, height=36)`
retorna SVG inline. Usa classes `.mg-spark-line/area/dot` que herdam
`--mg-primary`.

### Responsividade dos cards — use `cqi`, não `vw`

`st.columns` só empilha abaixo de **640px de viewport**
(`breakpoints.columns` do Streamlit) — e é media query de *viewport*,
não de container. Entre 640px e ~1200px as colunas apenas encolhem, sem
empilhar. Por isso:

- `.mg-prod-card`, `.mg-kpi-hero` e `.mg-kpi-context` declaram
  `container-type: inline-size` (nome `kpi-card`).
- Tipografia dentro deles usa `clamp(min, Ncqi, max)` — escala pela
  largura **do card**. Nunca `vw`: superdimensiona dentro de coluna
  estreita ou do carrossel `#mg-mix-scroll`.
- **Calibre o coeficiente `cqi` por largura de card real.** Converter
  `vw → cqi` mantendo o número encolhe o texto em telas grandes (o card
  é muito mais estreito que o viewport). Régua do projeto: reproduzir o
  tamanho desejado na largura de card de uma tela grande (~510px para 3
  cards hero, ~395px para 4 cards de contexto, em ~1620px de conteúdo) e
  deixar o `max` acima disso, para o texto acompanhar o card em
  monitores maiores.
- **`cqi` mede o *content box* do container**, não o border box —
  desconte o `padding` do card ao calibrar (o `.mg-kpi-context` tem
  18/20px, e menos nos breakpoints).
- **Quando a mesma classe serve larguras muito diferentes, use
  `calc(fixo + Ncqi)`, não `Ncqi` puro.** `.mg-kpi-context` aparece em
  três regimes: linha `flex:1` (~390–530px), carrossel Produtos MIX
  (~240–340px) e cards de dimensão em `detalhes` (`max-width:300px`).
  Com coeficiente puro, calibrar para um regime trava os outros no
  `min` do `clamp`. A parcela fixa é o piso legível; o `cqi` é o
  crescimento.
- **Media query de viewport anula container query.** Um
  `@media (max-width:1024px){ .x { font-size: 12px } }` sobrescreve o
  `clamp(..., cqi, ...)` e prende o texto no valor fixo. Se o
  breakpoint precisa mesmo reduzir, reduza mantendo a fórmula fluida.
- Grids em HTML custom usam
  `repeat(auto-fit, minmax(min(Npx, 100%), 1fr))`, não `repeat(N, 1fr)`.
- `div[data-testid="column"]` também é container (`kpi-col`), usado
  pelas regras `@container` de `[data-testid="stMetric"]`.

**Markdown não é processado dentro de bloco HTML bruto.** Em
`st.markdown(..., unsafe_allow_html=True)` ou `st.html`, use
`<strong>`; `**negrito**` aparece com os asteriscos literais.
