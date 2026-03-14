---
trigger: model_decision
description:  When thinking about styling, designing, or creating new visuals, consider this when refactoring the code.
---

# Dashboard Design - Principles and Best Practices

Skill for effective design of business dashboards and KPIs.

## When to Use

- Create dashboards for stakeholders
- Visualize business KPIs
- Communicate data insights
- Monitor performance

## Fundamental Principles

### 1. Avoid Information Overload

**Problem**: Dashboards with many elements confuse instead of inform.

**Solution**:
- Maximum of 5-10 KPIs per screen
- If everything is important, nothing is important
- Use visual hierarchy to highlight the essential

```python
# ❌ Bad: 20 metrics on the same screen
st.metric("Metric 1", value1)
st.metric("Metric 2", value2)
# ... 18 more

# ✅ Good: 5-8 main KPIs
main_kpis = ["Revenue", "Conversion", "CAC", "ROI", "Average Ticket"]
for kpi in main_kpis:
    st.metric(kpi, values[kpi])
```

### 2. Always Include Context

**Problem**: Numbers without context have no meaning.

**Solution**:
- Compare with previous period
- Show goals/targets
- Use deltas and visual indicators

```python
# ❌ Bad: Isolated value
st.metric("Revenue", "R$ 50,000")

# ✅ Good: Value with context
st.metric(
    "Revenue",
    "R$ 50,000",
    delta="10% vs. previous month",
    delta_color="normal",
    help="Target: R$ 55,000",
)
```

### 3. Dashboards by Audience

**Problem**: Single dashboard for everyone doesn't serve anyone well.

**Dashboard Types**:

#### Executive Dashboard (Strategic)
- High-level overview
- Consolidated KPIs
- Long-term trends
- Comparisons with goals

```python
def executive_dashboard():
    st.title("Executive Dashboard")
    
    # Main KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Revenue", "R$ 1M", "+15%")
    with col2:
        st.metric("ROI", "250%", "+20pp")
    with col3:
        st.metric("Customers", "1,500", "+10%")
    with col4:
        st.metric("NPS", "8.5", "+0.5")
    
    # Trends
    st.plotly_chart(revenue_trend_chart())
```

#### Management Dashboard (Tactical)
- Metrics by department/region
- Drill-down available
- Comparisons between areas
- Performance analysis

```python
def managerial_dashboard():
    st.title("Management Dashboard")
    
    # Filters
    region = st.selectbox("Region", regions)
    
    # Regional metrics
    show_regional_kpis(region)
    
    # Comparison with other regions
    show_regional_comparison(region)
    
    # Breakdown by store
    show_store_breakdown(region)
```

#### Operational Dashboard
- Real-time data
- Granular details
- Specific actions
- Daily monitoring

```python
def operational_dashboard():
    st.title("Operational Dashboard")
    
    # Today's data
    st.metric("Today's Sales", "R$ 15,000")
    
    # Pending actions list
    show_pending_actions()
    
    # Transaction details
    st.dataframe(today_transactions)
```

### 4. Choose Correct Visualizations

**Rules**:

| Objective | Visualization |
|-----------|---------------|
| Time trend | Line chart |
| Category comparison | Bar chart |
| Proportion/distribution | Pie (use in moderation) |
| Correlation | Scatter plot |
| Statistical distribution | Histogram/Box plot |
| Process/funnel | Funnel chart |
| Hierarchy | Treemap |

```python
# ✅ Trend
px.line(df, x="date", y="value")

# ✅ Comparison
px.bar(df, x="category", y="value")

# ⚠️ Pie: use only for 3-5 categories
px.pie(df, names="category", values="value")

# ✅ Conversion funnel
go.Funnel(y=stages, x=values)
```

### 5. Actionable vs. Vanity Metrics

**Vanity Metrics**: Look good but don't lead to actions.
- Total pageviews
- Number of followers
- Total downloads

**Actionable Metrics**: Connected to objectives and actions.
- Conversion rate
- CAC (Customer Acquisition Cost)
- LTV (Lifetime Value)
- ROI
- Churn rate

```python
# ❌ Vanity metric
st.metric("Total Visitors", "10,000")

# ✅ Actionable metric
st.metric(
    "Conversion Rate",
    "2.5%",
    delta="-0.3pp",
    help="Target: 3%. Action: Review checkout funnel",
)
```

## Design Best Practices

### 1. Visual Hierarchy

```python
# Order of importance
st.title("Main Title")  # Most important
st.header("Section")
st.subheader("Subsection")
st.markdown("Explanatory text")  # Less important

# KPI sizes
# Main: Large and at the top
# Secondary: Smaller and below
```

### 2. Consistent Color Palette

```python
# Define project colors
COLORS = {
    "primary": "#1976d2",      # Main blue
    "secondary": "#1565c0",    # Secondary blue
    "success": "#2e7d32",      # Green (positive)
    "warning": "#f57c00",      # Orange (attention)
    "danger": "#c62828",       # Red (negative)
    "neutral": "#757575",      # Gray
}

# Use consistently
fig = px.bar(df, x="x", y="y", color_discrete_sequence=[COLORS["primary"]])
```

### 3. Spacing and Organization

```python
# Use dividers
st.markdown("---")

# Group related items
with st.container():
    st.subheader("Financial KPIs")
    col1, col2, col3 = st.columns(3)
    # Financial KPIs together

st.markdown("---")

with st.container():
    st.subheader("Operational KPIs")
    # Operational KPIs together
```

### 4. Responsiveness

```python
# Use adaptive columns
col1, col2 = st.columns([2, 1])  # 2:1 ratio

# Responsive charts
st.plotly_chart(fig, use_container_width=True)

# Wide layout for dashboards
st.set_page_config(layout="wide")
```

### 5. Useful Interactivity

```python
# Relevant filters
with st.sidebar:
    date_range = st.date_input("Period")
    region = st.multiselect("Region", regions)

# Drill-down
selected_category = st.selectbox("Category", categories)
show_category_details(selected_category)

# Informative tooltips
st.metric(
    "CAC",
    "R$ 150",
    help="Customer Acquisition Cost: Total cost / New customers",
)
```

## Common Errors to Avoid

### 1. ❌ 3D Charts

```python
# ❌ Avoid: Distorts proportions
fig = go.Figure(data=[go.Pie(values=values, labels=labels, hole=.3)])

# ✅ Use: Simple and clear 2D
fig = px.pie(df, values="value", names="label")
```

### 2. ❌ Too Many Colors

```python
# ❌ Avoid: Confusing rainbow
colors = ["red", "blue", "green", "yellow", "purple", "orange"]

# ✅ Use: Limited and consistent palette
colors = [COLORS["primary"], COLORS["secondary"], COLORS["success"]]
```

### 3. ❌ Unnecessary Widgets

```python
# ❌ Avoid: Irrelevant information
st.write("Last update:", datetime.now())
st.image("random_image.png")

# ✅ Focus: Actionable data
st.metric("Last Sale", "5 minutes ago")
```

### 4. ❌ Lack of Updates

```python
# ❌ Avoid: Outdated static data
data = load_old_data()

# ✅ Use: Cache with TTL
@st.cache_data(ttl=3600)  # 1 hour
def load_fresh_data():
    return fetch_latest_data()
```

## Quality Checklist

### Before Publishing

- [ ] Maximum of 5-10 KPIs per page?
- [ ] All values have context (comparison, target)?
- [ ] Correct visualizations for each data type?
- [ ] Consistent colors with visual identity?
- [ ] Relevant and functional filters?
- [ ] Metrics connected to business objectives?
- [ ] Explanatory tooltips where needed?
- [ ] Tested on different resolutions?
- [ ] Acceptable performance (< 3s loading)?
- [ ] Data updated automatically?

## Complete Example

```python
import streamlit as st
import plotly.express as px
import pandas as pd

COLORS = {
    "primary": "#1976d2",
    "success": "#2e7d32",
    "warning": "#f57c00",
}

st.set_page_config(layout="wide", page_title="Sales Dashboard")

st.title("📊 Sales Dashboard")
st.markdown("---")

# Filters in sidebar
with st.sidebar:
    st.header("Filters")
    period = st.selectbox("Period", ["Today", "Week", "Month"])
    region = st.multiselect("Region", ["North", "South", "East", "West"])

# Main KPIs (maximum 5)
st.subheader("Main Indicators")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "Revenue",
        "R$ 150k",
        delta="15%",
        help="Total revenue vs. previous period",
    )

with col2:
    st.metric(
        "Conversion",
        "3.2%",
        delta="0.5pp",
        help="Lead conversion rate",
    )

with col3:
    st.metric(
        "CAC",
        "R$ 120",
        delta="-10%",
        delta_color="inverse",
        help="Customer acquisition cost",
    )

with col4:
    st.metric(
        "Average Ticket",
        "R$ 450",
        delta="5%",
        help="Average value per sale",
    )

with col5:
    st.metric(
        "ROI",
        "280%",
        delta="20pp",
        help="Return on investment",
    )

st.markdown("---")

# Visualizations (maximum 2-3 per section)
col1, col2 = st.columns(2)

with col1:
    # Time trend
    fig = px.line(
        df_trend,
        x="date",
        y="revenue",
        title="Revenue Over Time",
        color_discrete_sequence=[COLORS["primary"]],
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    # Category comparison
    fig = px.bar(
        df_category,
        x="category",
        y="value",
        title="Sales by Category",
        color_discrete_sequence=[COLORS["success"]],
    )
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Detailed analysis (with drill-down)
st.subheader("Detailed Analysis")
selected = st.selectbox("Select a category", categories)
st.dataframe(get_category_details(selected), use_container_width=True)
```

## References

- [Dashboard Design Best Practices](https://www.simplekpi.com/Blog/KPI-Dashboards-a-comprehensive-guide)
- [Data Visualization Principles](https://www.qlik.com/us/dashboard-examples/kpi-dashboards)
- [Storytelling with Data](https://www.storytellingwithdata.com/)

