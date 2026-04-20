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

### Tabs — navegação primária

```python
tab = sac.tabs(
    items=[
        sac.TabsItem(label="Produtos", icon="box"),
        sac.TabsItem(label="Regioes",  icon="geo-alt"),
        sac.TabsItem(label="Rankings", icon="trophy"),
    ],
    align="center",        # "start" em sub-tabs
    variant="outline",
    use_container_width=True,
)
if tab == "Produtos":
    ...
```

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

- `aplicar_tema()` — injeta variáveis CSS `--mg-*` e `--st-*` conforme o tema ativo.
- `get_theme()` — lê `st.session_state["theme"]` (`"light"` | `"dark"`).
- `carregar_estilos_customizados()` — carrega `assets/dashboard_style.css`.
- `CHART_THEME` / `NATIVE_THEME` — paletas para Plotly e para o tema nativo do Streamlit.

`app.py` chama `carregar_estilos_customizados()` e `aplicar_tema()` no
início de `main()`; o toggle na sidebar alterna entre `light`/`dark` e
chama `st.rerun()`. Toda cor de gráfico **deve** vir do `CHART_THEME`
associado ao tema ativo (ver [conventions.md](conventions.md)).
