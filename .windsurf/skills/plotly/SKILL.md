---
name: plotly
description: Use this skill whenever the user wants to create interactive charts or dashboards in Python using Plotly.
---

# Plotly — Interactive Visualizations
 
Plotly has two APIs:
- **Plotly Express (`px`)** — high-level, one-liner charts. Use this first.
- **Graph Objects (`go`)** — low-level full control. Use for customization or chart types not in `px`.
 
For Streamlit integration: use `st.plotly_chart(fig, use_container_width=True)`.
For subplots and advanced layouts, see `references/subplots-layout.md`.
 
---
 
## 1. Setup
 
```python
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
```
 
---
 
## 2. Plotly Express — Quick Charts
 
### Scatter & Line
 
```python
# Scatter
fig = px.scatter(df, x="gdp", y="happiness",
                 color="continent", size="population",
                 hover_name="country", symbol="region",
                 title="GDP vs Happiness",
                 labels={"gdp": "GDP per Capita", "happiness": "Score"})
 
# Line
fig = px.line(df, x="date", y="value", color="category",
              line_dash="group",         # differentiate by dash style
              markers=True,
              title="Trend Over Time")
 
# Scatter with regression trendline
fig = px.scatter(df, x="x", y="y", trendline="ols",
                 trendline_color_override="red")
```
 
### Distributions
 
```python
# Histogram
fig = px.histogram(df, x="age", color="gender",
                   nbins=30, barmode="overlay", opacity=0.7,
                   marginal="box")     # adds box plot on margin
 
# Box
fig = px.box(df, x="category", y="value", color="group",
             points="outliers",        # all | outliers | suspectedoutliers | False
             notched=True)
 
# Violin
fig = px.violin(df, x="day", y="total_bill", color="sex",
                box=True, points="all", hover_data=df.columns)
```
 
### Bar & Categorical
 
```python
# Bar (aggregated)
fig = px.bar(df, x="region", y="sales", color="year",
             barmode="group",          # group | stack | overlay | relative
             text_auto=".2s",          # auto-label bars
             title="Sales by Region")
 
# Horizontal bar (sorted)
df_sorted = df.sort_values("value", ascending=True)
fig = px.bar(df_sorted, y="label", x="value", orientation="h",
             color="category")
```
 
### Part-of-Whole
 
```python
# Pie
fig = px.pie(df, names="category", values="amount",
             hole=0.4,                 # donut if > 0
             title="Revenue Share")
 
# Sunburst (hierarchical)
fig = px.sunburst(df, path=["continent", "country", "city"],
                  values="population", color="gdp")
 
# Treemap
fig = px.treemap(df, path=["region", "category"], values="sales",
                 color="growth", color_continuous_scale="RdYlGn")
 
# Funnel
fig = px.funnel(df, x="count", y="stage")
```
 
### Matrix & Statistical
 
```python
# Heatmap
fig = px.imshow(corr_matrix, text_auto=".2f",
                color_continuous_scale="RdBu_r",
                zmin=-1, zmax=1,
                title="Correlation Matrix")
 
# Scatter matrix (pairplot equivalent)
fig = px.scatter_matrix(df, dimensions=["a","b","c","d"],
                        color="species", symbol="species",
                        opacity=0.7)
```
 
### Geographic
 
```python
# Choropleth (country-level)
fig = px.choropleth(df, locations="iso_code",
                    color="value",
                    hover_name="country",
                    color_continuous_scale="Viridis",
                    title="World Map")
 
# Scatter map (lat/lon)
fig = px.scatter_map(df, lat="lat", lon="lon",
                     size="population", color="region",
                     hover_name="city", zoom=4)
```
 
### Animation
 
```python
# Animated scatter (gapminder style)
fig = px.scatter(df, x="gdp", y="life_exp",
                 animation_frame="year",
                 animation_group="country",
                 size="population", color="continent",
                 hover_name="country",
                 range_x=[100, 100_000], range_y=[25, 90],
                 log_x=True)
fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 500
```
 
---
 
## 3. Layout & Styling
 
```python
fig.update_layout(
    title=dict(text="My Chart", font_size=18, x=0.5),   # centered title
    template="plotly_white",    # plotly | plotly_white | plotly_dark | ggplot2 | seaborn
    font=dict(family="Inter, sans-serif", size=13),
    legend=dict(
        orientation="h",         # horizontal legend
        yanchor="bottom", y=1.02,
        xanchor="right",  x=1
    ),
    margin=dict(l=40, r=40, t=60, b=40),
    height=500,
    hoverlabel=dict(bgcolor="white", font_size=13),
    hovermode="x unified",       # x unified | x | y | closest
)
 
# Axis formatting
fig.update_xaxes(title_text="Date", showgrid=True, gridcolor="#e0e0e0",
                 tickangle=-45)
fig.update_yaxes(title_text="Value ($)", tickformat=",.0f",
                 rangemode="tozero")
 
# Color scale / colorbar
fig.update_coloraxes(colorbar_title="Score",
                     colorscale="Viridis")
```
 
---
 
## 4. Graph Objects — Full Control
 
```python
# When px isn't enough: build traces manually
fig = go.Figure()
 
fig.add_trace(go.Scatter(
    x=df["date"], y=df["value"],
    mode="lines+markers",
    name="Actual",
    line=dict(color="#3498db", width=2),
    marker=dict(size=6),
    hovertemplate="<b>%{x}</b><br>Value: %{y:,.0f}<extra></extra>",
))
 
fig.add_trace(go.Scatter(
    x=df["date"], y=df["forecast"],
    mode="lines",
    name="Forecast",
    line=dict(color="coral", dash="dash"),
))
 
# Confidence interval band
fig.add_trace(go.Scatter(
    x=pd.concat([df["date"], df["date"].iloc[::-1]]),
    y=pd.concat([df["upper"], df["lower"].iloc[::-1]]),
    fill="toself", fillcolor="rgba(231,76,60,0.15)",
    line=dict(color="rgba(255,255,255,0)"),
    name="95% CI", showlegend=True,
))
```
 
---
 
## 5. Annotations & Shapes
 
```python
# Text annotation with arrow
fig.add_annotation(
    x="2023-06-01", y=1500,
    text="<b>Peak</b>",
    showarrow=True, arrowhead=2, arrowcolor="#e74c3c",
    font=dict(size=12, color="#e74c3c"),
    bgcolor="white", bordercolor="#e74c3c",
)
 
# Horizontal reference line
fig.add_hline(y=1000, line_dash="dot", line_color="gray",
              annotation_text="Target", annotation_position="right")
 
# Vertical line (event marker)
fig.add_vline(x="2023-03-15", line_dash="dash", line_color="#2ecc71")
 
# Highlighted region
fig.add_vrect(x0="2023-01-01", x1="2023-03-31",
              fillcolor="yellow", opacity=0.15, line_width=0,
              annotation_text="Q1", annotation_position="top left")
```
 
---
 
## 6. Hover Customization
 
```python
# Custom hover template
fig.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "Revenue: $%{y:,.0f}<br>"
        "Growth: %{customdata[1]:.1%}<br>"
        "<extra></extra>"                # removes trace name box
    ),
    customdata=df[["name", "growth"]].values,
)
```
 
---
 
## 7. Export
 
```python
# Interactive HTML
fig.write_html("chart.html", include_plotlyjs="cdn")   # small file
 
# Static image (requires kaleido: pip install kaleido)
fig.write_image("chart.png", width=1200, height=600, scale=2)
fig.write_image("chart.pdf")    # vector
 
# Show in notebook / script
fig.show()
 
# Streamlit
import streamlit as st
st.plotly_chart(fig, use_container_width=True)
```
 
---
 
## 8. Common Patterns
 
```python
# ── Apply consistent theme across all charts ──────────────────────────────
import plotly.io as pio
 
MY_TEMPLATE = go.layout.Template()
MY_TEMPLATE.layout = go.Layout(
    font=dict(family="Inter"),
    paper_bgcolor="white",
    plot_bgcolor="#f9f9f9",
    colorway=["#2ecc71","#3498db","#e74c3c","#f39c12","#9b59b6"],
)
pio.templates["my_theme"] = MY_TEMPLATE
pio.templates.default = "my_theme"
 
# ── KPI sparkline ─────────────────────────────────────────────────────────
def sparkline(series, color="#3498db"):
    fig = go.Figure(go.Scatter(y=series, mode="lines",
                               line=dict(color=color, width=2)))
    fig.update_layout(height=80, margin=dict(l=0,r=0,t=0,b=0),
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      plot_bgcolor="white", paper_bgcolor="white")
    return fig
```
 
---
 
## 9. Common Pitfalls
 
| Problem | Fix |
|---|---|
| Chart appears blank in Streamlit | Use `st.plotly_chart(fig, use_container_width=True)` |
| `write_image` fails | Install kaleido: `pip install kaleido` |
| Hover shows wrong data | Check `customdata` alignment with DataFrame |
| Animation is too fast | Set `frame.duration` in `updatemenus` |
| Categorical axis wrong order | Use `category_orders={"col": ["A","B","C"]}` in `px` call |
| Colorscale out of range | Set `zmin` / `zmax` or `cmin` / `cmax` explicitly |
 
For subplots and complex multi-chart layouts, see `references/subplots-layout.md`.
