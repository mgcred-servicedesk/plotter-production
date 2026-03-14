---
name: streamlit
description: A brief description, shown to the model to help it understand when to use this skill
---

# Streamlit - Interactive Dashboard

Skill for developing interactive dashboards with Streamlit.

## When to Use

- Create interactive dashboards for data analysis
- Prototype visualization applications quickly
- Enable self-service data exploration
- Build analysis tools for stakeholders

## Fundamental Concepts

### Basic Structure

```python
import streamlit as st

st.set_page_config(
    page_title="Title",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("My Dashboard")
st.markdown("---")
```

### Main Components

#### 1. Layout

```python
# Columns
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("KPI 1", "100")

# Tabs
tab1, tab2 = st.tabs(["Overview", "Details"])
with tab1:
    st.write("Tab 1 content")

# Sidebar
with st.sidebar:
    st.title("Navigation")
    page = st.radio("Select", ["Page 1", "Page 2"])

# Expander
with st.expander("See more details"):
    st.write("Expandable content")
```

#### 2. Input Widgets

```python
# Text input
name = st.text_input("Name")

# Number input
age = st.number_input("Age", min_value=0, max_value=120)

# Select box
option = st.selectbox("Choose", ["A", "B", "C"])

# Multi-select
options = st.multiselect("Choose multiple", ["A", "B", "C"])

# Slider
value = st.slider("Value", 0, 100, 50)

# Date input
date = st.date_input("Date")

# File uploader
file = st.file_uploader("Upload file", type=["csv", "xlsx"])
```

#### 3. Data Display

```python
import pandas as pd

# DataFrame
st.dataframe(df, use_container_width=True, hide_index=True)

# Static table
st.table(df)

# Metrics
st.metric(
    label="Revenue",
    value="$1,000",
    delta="10%",
    delta_color="normal",
)

# JSON
st.json({"key": "value"})
```

#### 4. Visualizations

```python
import plotly.express as px

# Plotly
fig = px.line(df, x="date", y="value")
st.plotly_chart(fig, use_container_width=True)

# Matplotlib
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot(df["x"], df["y"])
st.pyplot(fig)

# Altair
import altair as alt
chart = alt.Chart(df).mark_line().encode(x="date", y="value")
st.altair_chart(chart, use_container_width=True)
```

#### 5. Messages

```python
st.success("Operation successful!")
st.info("Important information")
st.warning("Attention!")
st.error("Error found")
```

### State Management

```python
# Initialize state
if "counter" not in st.session_state:
    st.session_state.counter = 0

# Use state
st.write(f"Counter: {st.session_state.counter}")

# Update state
if st.button("Increment"):
    st.session_state.counter += 1
```

### Caching and Performance

```python
# Data cache (doesn't reload on every interaction)
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

# Resource cache (connections, models)
@st.cache_resource
def get_database_connection():
    return create_connection()
```

## Best Practices

### 1. Code Organization

```python
# Separate into functions
def show_kpis(data):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total", len(data))
    # ...

def show_charts(data):
    st.plotly_chart(create_chart(data))

# Use in main
def main():
    data = load_data()
    show_kpis(data)
    show_charts(data)

if __name__ == "__main__":
    main()
```

### 2. Reusable Components

```python
# components/filters.py
def date_filter(key="date"):
    return st.date_input("Date", key=key)

# components/kpi_cards.py
def kpi_card(label, value, delta=None):
    st.metric(label, value, delta)
```

### 3. Multi-Page Apps

```
app.py
pages/
├── 1_📊_Overview.py
├── 2_🌍_Regional.py
└── 3_🔍_Details.py
```

### 4. Performance

- Use `@st.cache_data` for data that doesn't change frequently
- Use `@st.cache_resource` for connections and models
- Avoid heavy processing in the main body
- Filter data before displaying

### 5. UX/UI

- Use `layout="wide"` for dashboards
- Organize with columns and tabs
- Add `help` to widgets
- Use emojis for better visualization
- Maintain visual consistency

## Complete Example

```python
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="Sales Dashboard",
    page_icon="📊",
    layout="wide",
)

@st.cache_data
def load_data():
    return pd.read_csv("sales.csv")

def main():
    st.title("📊 Sales Dashboard")
    st.markdown("---")
    
    data = load_data()
    
    # Filters in sidebar
    with st.sidebar:
        st.header("Filters")
        date_range = st.date_input("Period", [])
        region = st.multiselect("Region", data["region"].unique())
    
    # Apply filters
    if region:
        data = data[data["region"].isin(region)]
    
    # KPIs
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Sales", f"$ {data['value'].sum():,.2f}")
    with col2:
        st.metric("Average Ticket", f"$ {data['value'].mean():,.2f}")
    with col3:
        st.metric("Customers", data["customer_id"].nunique())
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    with col1:
        fig = px.line(data, x="date", y="value", title="Sales Over Time")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.bar(data, x="region", y="value", title="Sales by Region")
        st.plotly_chart(fig, use_container_width=True)
    
    # Table
    st.subheader("Detailed Data")
    st.dataframe(data, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
```

## Deploy

### Local

```bash
streamlit run app.py
```

### Streamlit Cloud

1. Push code to GitHub
2. Access share.streamlit.io
3. Connect repository
4. Automatic deploy

### Server

```bash
# Install
pip install streamlit

# Run in production
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

## Troubleshooting

### Problem: Slow app

**Solution**: Use `@st.cache_data` and `@st.cache_resource`

### Problem: Lost state

**Solution**: Use `st.session_state`

### Problem: Broken layout

**Solution**: Use `use_container_width=True` in charts

## References

- [Official Documentation](https://docs.streamlit.io/)
- [App Gallery](https://streamlit.io/gallery)
- [Cheat Sheet](https://docs.streamlit.io/library/cheatsheet)
