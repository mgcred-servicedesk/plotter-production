# Plotly Subplots & Advanced Layout
 
## Basic Subplots
 
```python
from plotly.subplots import make_subplots
import plotly.graph_objects as go
 
fig = make_subplots(
    rows=2, cols=2,
    subplot_titles=("Chart A", "Chart B", "Chart C", "Chart D"),
    shared_xaxes=False,
    shared_yaxes=False,
    vertical_spacing=0.12,
    horizontal_spacing=0.08,
)
 
fig.add_trace(go.Bar(x=df["cat"], y=df["val"], name="Sales"),    row=1, col=1)
fig.add_trace(go.Scatter(x=df["x"], y=df["y"], name="Trend"),    row=1, col=2)
fig.add_trace(go.Histogram(x=df["age"], name="Age Dist"),         row=2, col=1)
fig.add_trace(go.Box(y=df["score"], name="Score"),                row=2, col=2)
 
fig.update_layout(height=700, title_text="Dashboard Overview")
```
 
## Mixed Chart Types in Subplots
 
```python
# Specify chart types when mixing (e.g., 3D, pie, geo)
fig = make_subplots(
    rows=1, cols=2,
    specs=[[{"type": "xy"}, {"type": "pie"}]]
)
 
fig.add_trace(go.Bar(x=cats, y=vals, name="Bar"),   row=1, col=1)
fig.add_trace(go.Pie(labels=cats, values=vals),      row=1, col=2)
```
 
## specs Matrix Options
 
| type | Use for |
|---|---|
| `"xy"` | Standard 2D charts (default) |
| `"pie"` | Pie / donut |
| `"polar"` | Polar / radar |
| `"geo"` | Geographic maps |
| `"mapbox"` | Mapbox maps |
| `"scene"` | 3D charts |
| `"domain"` | Full-domain charts (table, sunburst) |
 
## Colspan / Rowspan
 
```python
fig = make_subplots(
    rows=2, cols=3,
    specs=[
        [{"colspan": 2}, None, {"rowspan": 2}],  # A spans 2 cols; C spans 2 rows
        [{"type": "xy"}, {"type": "xy"}, None],
    ]
)
```
 
## Secondary Y-Axis
 
```python
fig = make_subplots(specs=[[{"secondary_y": True}]])
 
fig.add_trace(
    go.Bar(x=df["date"], y=df["revenue"], name="Revenue"),
    secondary_y=False,
)
fig.add_trace(
    go.Scatter(x=df["date"], y=df["growth_pct"], name="Growth %",
               mode="lines+markers"),
    secondary_y=True,
)
 
fig.update_yaxes(title_text="Revenue ($)", secondary_y=False)
fig.update_yaxes(title_text="Growth (%)", secondary_y=True)
```
 
## Synced Axes Across Subplots
 
```python
# Shared x-axis (useful for time series stacked charts)
fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                    vertical_spacing=0.05)
 
fig.add_trace(go.Scatter(x=df["date"], y=df["price"]),  row=1, col=1)
fig.add_trace(go.Bar(x=df["date"], y=df["volume"]),     row=2, col=1)
fig.add_trace(go.Scatter(x=df["date"], y=df["rsi"]),    row=3, col=1)
 
# Remove x-axis labels except bottom
fig.update_xaxes(showticklabels=False, row=1, col=1)
fig.update_xaxes(showticklabels=False, row=2, col=1)
```
 
## Facet Grids via Plotly Express
 
```python
# px natively creates subplot grids via col= / row= / facet_col_wrap=
import plotly.express as px
 
fig = px.histogram(df, x="value", color="group",
                   facet_col="region", facet_col_wrap=3,
                   height=500)
 
# Remove "region=" prefix from facet titles
fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
```
 
## Updating Specific Subplot Axes
 
```python
# Target by row/col
fig.update_xaxes(tickangle=-45, row=2, col=1)
fig.update_yaxes(tickformat="$,.0f", row=1, col=1)
fig.update_yaxes(range=[0, 100], row=1, col=2)
 
# Or by axis id
fig.update_layout(
    xaxis3=dict(title="Custom X for 3rd chart"),
    yaxis2=dict(showgrid=False),
)
```