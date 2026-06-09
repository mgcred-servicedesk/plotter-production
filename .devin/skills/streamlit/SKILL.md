---
name: streamlit
description: Padrões Streamlit (layout, widgets, state, caching, Width API). Para padrões específicos do projeto, consultar mgcred-dashboard primeiro.
---

# Streamlit — Router

Padrões específicos do projeto (cache `_atual`/`_historico`, `exibir_tabela`,
tab renderer, componentes `sac.*`) vivem em `docs/agents/`. Consulte
`mgcred-dashboard` **antes** de usar esta skill.

## Onde procurar

| Tópico | Doc |
|---|---|
| Estratégia de cache Supabase (`_atual`/`_historico`, TTLs) | `docs/agents/data-layer.md` |
| Width API (`width="stretch"` vs `use_container_width`) | `docs/agents/conventions.md` |
| `exibir_tabela`, `sac.*`, tab renderer | `docs/agents/ui-components.md` |

## Resumo rápido — padrões Streamlit

### Page config (sempre primeiro)

```python
st.set_page_config(
    page_title="Title",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

### Layout

```python
col1, col2 = st.columns([2, 1])   # colunas com ratio
with col1: ...

tab1, tab2 = st.tabs(["A", "B"])  # nativo (prefira sac.tabs no projeto)

with st.expander("Detalhes", expanded=False): ...
with st.sidebar: ...
```

### Widgets principais

```python
st.selectbox("Label", options, help="...")
st.multiselect("Label", options)
st.slider("Label", min_value=0, max_value=100, value=50)
st.date_input("Data")
st.file_uploader("Upload", type=["csv", "xlsx"])
```

### Caching (genérico)

```python
@st.cache_data           # dados, DataFrames
@st.cache_data(ttl=300)  # TTL em segundos
@st.cache_resource       # conexões, modelos
```

> **No projeto**, preferir o padrão `_atual`/`_historico` — ver `docs/agents/data-layer.md`.

### Session state

```python
if "key" not in st.session_state:
    st.session_state.key = default

st.session_state.key = new
st.rerun()
```

### Width API (Streamlit ≥ 1.35)

```python
st.plotly_chart(fig, width="stretch")
st.dataframe(df, width="stretch", hide_index=True)
st.button("Sair", width="stretch")
```

`use_container_width=True` está **deprecated** (exceto componentes
`sac.*`, que são de biblioteca externa).

### Messages

```python
st.success("OK"); st.info("…"); st.warning("…"); st.error("…")
```

## Pitfalls

| Problema | Correção |
|---|---|
| Gráfico não preenche largura | `width="stretch"` |
| State perdido entre interações | `st.session_state` |
| Query pesada roda a cada interação | `@st.cache_data` ou `@st.cache_resource` |
| `hide_index` ausente | Sempre `hide_index=True` em `st.dataframe` |
| `DeprecationWarning` para `use_container_width` | Migrar para `width="stretch"` |
