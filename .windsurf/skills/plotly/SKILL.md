---
name: plotly
description: Use whenever the task involves creating interactive charts with Plotly. For project-specific chart patterns (template, CHART_COLORS, subplots), see mgcred-dashboard first.
---

# Plotly — Interactive Visualizations

Use `px` (Plotly Express) first. Fall back to `go` (Graph Objects) for
customization or chart types not in `px`.

## Plotly Express — Quick Charts

```python
import plotly.express as px

# Line
fig = px.line(df, x="date", y="value", color="category",
              markers=True, title="Trend Over Time")

# Bar
fig = px.bar(df, x="region", y="sales", color="year",
             barmode="group", text_auto=".2s")

# Horizontal bar (sorted)
df_s = df.sort_values("value", ascending=True)
fig = px.bar(df_s, y="label", x="value", orientation="h")

# Scatter
fig = px.scatter(df, x="gdp", y="happiness", color="continent",
                 size="population", hover_name="country")

# Histogram
fig = px.histogram(df, x="age", nbins=30, marginal="box")

# Box
fig = px.box(df, x="category", y="value", points="outliers", notched=True)

# Pie / Donut
fig = px.pie(df, names="category", values="amount", hole=0.4)

# Heatmap (correlation matrix)
fig = px.imshow(corr_matrix, text_auto=".2f",
                color_continuous_scale="RdBu_r", zmin=-1, zmax=1)

# Funnel
fig = px.funnel(df, x="count", y="stage")

# Treemap
fig = px.treemap(df, path=["region", "category"], values="sales",
                 color="growth", color_continuous_scale="RdYlGn")
```

## Layout & Styling

```python
fig.update_layout(
    title=dict(text="Title", font_size=18, x=0.5),
    template="plotly_white",
    font=dict(family="Inter, sans-serif", size=13),
    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1),
    margin=dict(l=40, r=40, t=60, b=40),
    hovermode="x unified",
)

fig.update_xaxes(title_text="Date", tickangle=-45)
fig.update_yaxes(title_text="Value", tickformat=",.0f", rangemode="tozero")
```

## Graph Objects — Full Control

```python
import plotly.graph_objects as go
from plotly.subplots import make_subplots

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=df["date"], y=df["value"],
    mode="lines+markers",
    name="Actual",
    line=dict(color="#3498db", width=2),
    hovertemplate="<b>%{x}</b><br>Value: %{y:,.0f}<extra></extra>",
))

# Subplots with mixed types
fig = make_subplots(
    rows=2, cols=2,
    specs=[[{"type": "bar"}, {"type": "bar"}],
           [{"type": "scatter"}, {"type": "bar"}]],
    subplot_titles=("Chart 1", "Chart 2", "Chart 3", "Chart 4"),
    vertical_spacing=0.14, horizontal_spacing=0.10,
)
```

## Reference Lines & Annotations

```python
fig.add_hline(y=1000, line_dash="dot", line_color="gray",
              annotation_text="Target", annotation_position="right")
fig.add_vline(x="2023-03-15", line_dash="dash", line_color="#2ecc71")
fig.add_vrect(x0="2023-01-01", x1="2023-03-31",
              fillcolor="yellow", opacity=0.15, line_width=0)
```

## Custom Hover

```python
fig.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "Revenue: $%{y:,.0f}<br>"
        "Growth: %{customdata[1]:.1%}<br>"
        "<extra></extra>"
    ),
    customdata=df[["name", "growth"]].values,
)
```

## Export

```python
fig.write_html("chart.html", include_plotlyjs="cdn")
fig.write_image("chart.png", width=1200, height=600, scale=2)  # needs kaleido
st.plotly_chart(fig, use_container_width=True)
```

## Pitfalls

| Problem | Fix |
|---|---|
| Blank chart in Streamlit | `use_container_width=True` |
| `write_image` fails silently | `pip install kaleido` |
| Hover shows wrong data | Check `customdata` row alignment with DataFrame index |
| Categorical axis wrong order | `category_orders={"col": ["A","B","C"]}` in `px` call |
| `add_hline` wrong subplot | Pass `row=` and `col=` explicitly |
| Bar text clipped | `textposition="outside"` + enough `margin.t` |