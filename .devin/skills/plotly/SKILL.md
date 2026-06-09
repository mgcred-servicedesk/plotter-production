---
name: plotly
description: Padrões Plotly para gráficos interativos. Para template do projeto (CHART_COLORS, _template, _aplicar), consultar mgcred-dashboard primeiro.
---

# Plotly — Router

Template de gráfico, paleta `CHART_COLORS` e padrões do projeto vivem em
`docs/agents/conventions.md`. Use esta skill apenas para referência rápida
de APIs Plotly genéricas.

## Onde procurar

| Tópico | Doc |
|---|---|
| `_template()`, `_aplicar()`, fundos transparentes | `docs/agents/conventions.md` |
| Paleta `CHART_COLORS` + regra de color-coding | `docs/agents/conventions.md` |
| `st.plotly_chart(fig, width="stretch")` | `docs/agents/conventions.md` |

## Resumo rápido — APIs Plotly

Prefira `plotly.express` (`px`); caia para `plotly.graph_objects` (`go`)
para customização ou tipos não cobertos por `px`.

### Express — gráficos rápidos

```python
import plotly.express as px

fig = px.line(df, x="date", y="value", color="cat", markers=True)
fig = px.bar(df, x="region", y="sales", color="year", barmode="group", text_auto=".2s")
fig = px.scatter(df, x="gdp", y="happiness", color="continent", size="pop")
fig = px.histogram(df, x="age", nbins=30, marginal="box")
fig = px.box(df, x="category", y="value", points="outliers", notched=True)
fig = px.pie(df, names="cat", values="amount", hole=0.4)
fig = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1)
fig = px.funnel(df, x="count", y="stage")
fig = px.treemap(df, path=["region", "cat"], values="sales")
```

### Graph objects — controle total

```python
import plotly.graph_objects as go
from plotly.subplots import make_subplots

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df["date"], y=df["value"],
    mode="lines+markers",
    name="Actual",
    line=dict(color="#3498db", width=2),
    hovertemplate="<b>%{x}</b><br>Valor: %{y:,.0f}<extra></extra>",
))

fig = make_subplots(
    rows=2, cols=2,
    specs=[[{"type": "bar"}, {"type": "bar"}],
           [{"type": "scatter"}, {"type": "bar"}]],
    subplot_titles=("C1", "C2", "C3", "C4"),
    vertical_spacing=0.14, horizontal_spacing=0.10,
)
```

### Linhas de referência, anotações, hover

```python
fig.add_hline(y=1000, line_dash="dot", line_color="gray",
              annotation_text="Meta", annotation_position="right")
fig.add_vline(x="2023-03-15", line_dash="dash", line_color="#2ecc71")
fig.add_vrect(x0="2023-01-01", x1="2023-03-31",
              fillcolor="yellow", opacity=0.15, line_width=0)

fig.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "Receita: R$%{y:,.0f}<br>"
        "Crescimento: %{customdata[1]:.1%}<br>"
        "<extra></extra>"
    ),
    customdata=df[["name", "growth"]].values,
)
```

### Export

```python
fig.write_html("chart.html", include_plotlyjs="cdn")
fig.write_image("chart.png", width=1200, height=600, scale=2)  # precisa kaleido
st.plotly_chart(fig, width="stretch")
```

## Pitfalls

| Problema | Correção |
|---|---|
| Gráfico branco no Streamlit | `width="stretch"` |
| `write_image` falha silenciosamente | `pip install kaleido` |
| Hover mostra dados errados | Verificar alinhamento de `customdata` com índice do DF |
| Ordem categórica errada | `category_orders={"col": ["A","B","C"]}` no `px` |
| `add_hline` no subplot errado | Passar `row=` e `col=` explicitamente |
| Texto da barra cortado | `textposition="outside"` + mais `margin.t` |
