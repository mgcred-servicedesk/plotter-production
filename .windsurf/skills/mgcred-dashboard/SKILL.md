---
name: mgcred-dashboard
description: Use for any work on app_supabase.py or dashboard components. Covers project-specific architecture, patterns, conventions, and the streamlit-antd-components library.
---

# MGCred Dashboard — Project Patterns

Primary file: `app_supabase.py`. All new features go here.
The Excel-based `app.py` is deprecated — do not add features to it.

---

## Architecture

```
app_supabase.py          ← main entry point
src/
  config/
    supabase_client.py   ← get_supabase_client()
    settings.py          ← MESES_PT, LISTA_PRODUTOS, etc.
  dashboard/
    auth.py              ← tela_login(), usuario_logado(), fazer_logout(), PERFIS
    rls.py               ← aplicar_rls(), aplicar_rls_metas(), aplicar_rls_supervisores(),
                            obter_regioes_permitidas()
    user_mgmt.py         ← render_pagina_usuarios()
    components/
      tables.py          ← exibir_tabela()
  data_processing/       ← deprecated (Excel pipeline)
  reports/               ← Excel and PDF generators
assets/
  dashboard_style.css
  logotipo-mg-cred.png
```

---

## RLS — Mandatory Order

Always apply in this exact sequence before any render or calculation:

```python
df      = aplicar_rls(df)
df_metas = aplicar_rls_metas(df_metas, df)
df_sup   = aplicar_rls_supervisores(df_sup, df)
```

Never render data that hasn't gone through RLS. Never apply RLS after filtering.

---

## Data Layer — Supabase

### Client shortcut

```python
def _sb():
    return get_supabase_client()
```

### Cache TTL conventions

```python
@st.cache_data(ttl=300)  # semi-static: categories, periods, supervisors
@st.cache_data(ttl=120)  # live data: contracts, points, goals
@st.cache_data           # no TTL only for truly static config
```

### Standard query pattern

```python
@st.cache_data(ttl=120)
def carregar_contratos_pagos(mes: int, ano: int) -> pd.DataFrame:
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    resp = (
        _sb()
        .table("contratos")
        .select("id, valor, lojas(nome, regioes(nome)), consultores(nome), produtos(tipo, categorias_produto(codigo, grupo_dashboard))")
        .eq("periodo_id", periodo["id"])
        .eq("status_pagamento_cliente", "PAGO AO CLIENTE")
        .execute()
    )

    if not resp.data:
        return pd.DataFrame()

    rows = []
    for c in resp.data:
        loja     = c.get("lojas") or {}
        regiao   = loja.get("regioes") or {}
        consultor = c.get("consultores") or {}
        produto  = c.get("produtos") or {}
        categoria = produto.get("categorias_produto") or {}
        rows.append({
            "LOJA":           loja.get("nome", ""),
            "REGIAO":         regiao.get("nome", ""),
            "CONSULTOR":      consultor.get("nome", ""),
            "TIPO_PRODUTO":   produto.get("tipo", ""),
            "categoria_codigo": categoria.get("codigo", ""),
            "grupo_dashboard": categoria.get("grupo_dashboard"),
            "VALOR":          float(c.get("valor", 0)),
        })

    return pd.DataFrame(rows)
```

### RPC calls

```python
resp = _sb().rpc("obter_pontuacao_periodo", {"p_mes": mes, "p_ano": ano}).execute()
df = pd.DataFrame(resp.data or [])
```

---

## Column Conventions

| Column | Type | Notes |
|---|---|---|
| `LOJA` | str | uppercase |
| `REGIAO` | str | uppercase |
| `CONSULTOR` | str | uppercase |
| `TIPO_PRODUTO` | str | uppercase |
| `VALOR` | float | always `float(c.get("valor", 0))` |
| `pontos` | float | lowercase — computed field |
| `DATA` | datetime | `pd.to_datetime(..., errors="coerce")` |
| `grupo_dashboard` | str or None | from `categorias_produto` |
| `grupo_meta` | str or None | from `categorias_produto` |
| `conta_valor` | bool | if False → VALOR = 0 |
| `conta_pontuacao` | bool | if False → pontos = 0 |

---

## KPI Calculation Patterns

### Dias úteis

```python
def calcular_dias_uteis(ano, mes, dia_atual=None):
    # Returns (du_total, du_decorridos, du_restantes)
    primeiro = datetime(ano, mes, 1)
    ultimo   = datetime(ano, mes + 1, 1) - pd.Timedelta(days=1) if mes < 12 \
               else datetime(ano + 1, 1, 1) - pd.Timedelta(days=1)
    total    = len(pd.bdate_range(primeiro, ultimo))
    data_ref = datetime(ano, mes, int(dia_atual)) if dia_atual else datetime.now()
    dec      = len(pd.bdate_range(primeiro, data_ref))
    return total, dec, total - dec
```

### Projeção

```python
media_du      = total / du_dec if du_dec > 0 else 0
projecao      = media_du * du_total
perc_proj     = projecao / meta * 100 if meta > 0 else 0
```

### Exclusão de supervisores

```python
def _excluir_supervisores(df, df_sup):
    if df_sup is not None and "SUPERVISOR" in df_sup.columns and "CONSULTOR" in df.columns:
        return df[~df["CONSULTOR"].isin(df_sup["SUPERVISOR"].unique())].copy()
    return df.copy()

def _contar_consultores(df, df_sup):
    if "CONSULTOR" not in df.columns:
        return 0
    cons = df["CONSULTOR"].unique()
    if df_sup is not None and "SUPERVISOR" in df_sup.columns:
        cons = [c for c in cons if c not in df_sup["SUPERVISOR"].unique()]
    return len(cons)
```

---

## Formatters (PT-BR)

```python
def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_numero(valor):
    return f"{valor:,.0f}".replace(",", ".")

def formatar_percentual(valor):
    return f"{valor:.1f}%"
```

---

## Chart Template

Every chart must use `_template()` and `_aplicar()`:

```python
def _template():
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor":  "rgba(0,0,0,0)",
        "font": dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", size=12),
        "legend": dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                       font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
        "margin": dict(l=60, r=30, t=60, b=50),
        "hoverlabel": dict(bgcolor="rgba(30,30,46,0.9)", font_color="#fff", font_size=12,
                           bordercolor="rgba(255,255,255,0.1)"),
    }

def _aplicar(fig, t):
    fig.update_layout(paper_bgcolor=t["paper_bgcolor"], plot_bgcolor=t["plot_bgcolor"],
                      font=t["font"], legend=t["legend"], hoverlabel=t["hoverlabel"])
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.1)", zerolinecolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)", zerolinecolor="rgba(128,128,128,0.15)")
    return fig
```

### Color palette

```python
CHART_COLORS = {
    "primary":      "#2563eb",
    "primary_dark": "#1e40af",
    "secondary":    "#0d9488",
    "success":      "#059669",  # >= 100% target
    "danger":       "#dc2626",  # < 100% target
    "warning":      "#d97706",
    "neutral":      "#64748b",
    "purple":       "#7c3aed",
    "rose":         "#e11d48",
    "seq": ["#2563eb","#0d9488","#7c3aed","#d97706","#059669","#e11d48","#64748b","#0284c7"],
}
```

Color-coding rule: `success` if `value >= 100`, else `danger`:

```python
cores = df["% Atingimento"].apply(
    lambda x: CHART_COLORS["success"] if x >= 100 else CHART_COLORS["danger"]
)
```

---

## streamlit-antd-components (sac)

This library is not in Streamlit's standard library. Import as:

```python
import streamlit_antd_components as sac
```

### Divider (use between every logical section)

```python
sac.divider(label="Section Title", icon="bar-chart-line", align="left", color="blue")
# color options: "blue" (primary), "gray" (secondary/table), "green", "orange"
# icon: Bootstrap Icons names (bar-chart-line, box, geo-alt, trophy, etc.)
```

### Tabs (primary navigation)

```python
tab = sac.tabs(
    items=[
        sac.TabsItem(label="Produtos", icon="box"),
        sac.TabsItem(label="Regioes",  icon="geo-alt"),
        sac.TabsItem(label="Rankings", icon="trophy"),
    ],
    align="center",       # "start" for sub-tabs
    variant="outline",
    use_container_width=True,
)
if tab == "Produtos":
    ...
```

### Segmented control (sub-selection within a tab)

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

---

## Table Display

Always use `exibir_tabela` — never use `st.dataframe` directly in tab renderers:

```python
from src.dashboard.components.tables import exibir_tabela

exibir_tabela(df)
exibir_tabela(df, colunas_moeda=["VALOR"], colunas_numero=["pontos"])
```

---

## Tab Renderer Pattern

Each tab is a private function `_render_tab_*`:

```python
def _render_tab_produtos(df, df_metas_produto, categorias, ano, mes, dia_atual, df_sup):
    sac.divider(label="Analise de Produtos", icon="box", align="left", color="blue")

    df_prod = calcular_kpis_por_produto(df, df_metas_produto, categorias, ano, mes, dia_atual, df_sup)
    fig = criar_grafico_produtos(df_prod)
    st.plotly_chart(fig, use_container_width=True)

    sac.divider(label="KPIs por Produto", icon="table", align="left", color="gray")
    exibir_tabela(df_prod)
```

---

## Auth & User Context

```python
from src.dashboard.auth import tela_login, usuario_logado, fazer_logout, PERFIS

if not tela_login():
    return  # stops execution if not authenticated

user = usuario_logado()
# user = {"nome": str, "perfil": str, "escopo": list | None}
# perfil values: "admin", "gestor", "gerente_comercial", "supervisor"

PERFIS  # dict mapping perfil key → display label
```

---

## Variable Naming Conventions

| Suffix | Meaning |
|---|---|
| `df_f` | filtered DataFrame (after region filter) |
| `df_sup` or `df_sup_f` | supervisors DataFrame |
| `df_metas_f` | filtered goals DataFrame |
| `df_metas_prod_f` | filtered per-product goals |
| `_render_*` | Streamlit render function (side effects only) |
| `calcular_*` | pure calculation function (returns DataFrame or dict) |
| `criar_grafico_*` | returns a Plotly `fig` object |
| `carregar_*` | Supabase query function (always cached) |