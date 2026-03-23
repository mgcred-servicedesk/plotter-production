---
name: streamlit
description: Use for Streamlit-specific patterns not covered by mgcred-dashboard. Covers layout, widgets, state, and caching.
---

# Streamlit — Core Patterns

## Page Config (always first)

```python
st.set_page_config(
    page_title="Title",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

## Layout

```python
# Columns
col1, col2 = st.columns([2, 1])  # ratio
with col1: ...

# Tabs (native)
tab1, tab2 = st.tabs(["Overview", "Details"])
with tab1: ...

# Expander
with st.expander("Details", expanded=False):
    st.write(...)

# Sidebar
with st.sidebar:
    option = st.selectbox("Filter", choices)
```

## Key Widgets

```python
st.selectbox("Label", options, help="...")
st.multiselect("Label", options)
st.slider("Label", min_value=0, max_value=100, value=50)
st.date_input("Date")
st.file_uploader("Upload", type=["csv", "xlsx"])
```

## Data Display

```python
# DataFrame (prefer exibir_tabela in this project)
st.dataframe(df, use_container_width=True, hide_index=True)

# Metric with context — always include delta and help
st.metric(label="KPI", value="R$ 1.000", delta="10%",
          delta_color="normal", help="Description")
```

## Caching

```python
@st.cache_data          # data, DataFrames — recomputes on arg change
def load_data(): ...

@st.cache_data(ttl=300) # explicit TTL in seconds for live data
def fetch_from_db(): ...

@st.cache_resource      # connections, models — shared across sessions
def get_connection(): ...
```

## Session State

```python
if "key" not in st.session_state:
    st.session_state.key = default_value

st.session_state.key = new_value
st.rerun()  # force rerun after state change
```

## Messages

```python
st.success("OK")
st.info("Info")
st.warning("Attention")
st.error("Error")
```

## Common Pitfalls

| Problem | Fix |
|---|---|
| Chart not filling width | `use_container_width=True` |
| State lost between interactions | Use `st.session_state` |
| Heavy query runs on every interaction | `@st.cache_data` or `@st.cache_resource` |
| `hide_index` missing | Always pass `hide_index=True` to `st.dataframe` |
| Layout breaks on resize | Use `st.columns` with ratios, not fixed widths |