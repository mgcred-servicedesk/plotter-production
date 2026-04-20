---
trigger: model_decision
description: Consult when designing, refactoring, or reviewing dashboard layout, KPIs, or chart choices.
---

# Dashboard Design — Principles & Best Practices

## Core Principles

### 1. Avoid information overload
Maximum 5–10 KPIs per screen. Use visual hierarchy to surface what matters.
If everything is highlighted, nothing is.

### 2. Always include context
Numbers without comparison have no meaning. Every KPI must show:
- Delta vs. previous period or target
- `help=` tooltip explaining the metric

### 3. Match the audience

| Dashboard type | Focus |
|---|---|
| Executive (strategic) | High-level KPIs, long-term trends, goal comparisons |
| Management (tactical) | Department/region breakdown, drill-down, cross-area comparisons |
| Operational | Real-time data, granular detail, daily monitoring |

### 4. Choose the right visualization

| Goal | Chart type |
|---|---|
| Time trend | Line |
| Category comparison | Bar (horizontal if many labels) |
| Proportion | Pie/donut — max 5 categories |
| Correlation | Scatter |
| Statistical distribution | Histogram or box plot |
| Conversion funnel | Funnel |
| Hierarchy | Treemap |
| Target vs. actual | Grouped bar or bullet chart |

### 5. Actionable over vanity metrics

Vanity: total page views, follower count, total downloads.
Actionable: conversion rate, CAC, LTV, churn, ROI, % atingimento de meta.

---

## Design Rules

- **Consistent color palette:** use `CHART_COLORS` from the project. Green = achieved,
  Red = below target, Blue = primary series. Never use more than 3–4 colors per chart.
- **Transparent backgrounds:** all Plotly charts use `paper_bgcolor` and
  `plot_bgcolor` as `rgba(0,0,0,0)` to match the Streamlit theme.
- **Width:** always `width="stretch"` on `st.plotly_chart`, `st.dataframe`, `st.button` (Streamlit ≥ 1.35 — `use_container_width=True` está deprecated). Componentes `sac.*` ainda usam `use_container_width=`.
- **Spacing:** use `sac.divider` with `label=` and `icon=` to separate sections.
  Never stack KPI rows without a divider between logical groups.
- **No 3D charts.** No rainbow palettes. No decorative widgets.
- **Responsive layout:** `st.set_page_config(layout="wide")` is mandatory.

---

## Common Anti-Patterns to Avoid

- Isolated values with no delta or target reference
- More than 3 chart types on the same page
- Filters that don't cascade to all visuals on the page
- Hardcoded colors instead of `CHART_COLORS`
- `st.table` instead of `exibir_tabela` (loses AG Grid formatting)
- Calling KPI calculation functions inside render functions without caching

---

## Quality Checklist (before shipping a new view)

- [ ] Max 10 KPIs per screen?
- [ ] Every value has delta or target context?
- [ ] Correct chart type for the data?
- [ ] `CHART_COLORS` used consistently?
- [ ] Filters apply to all visuals on the page?
- [ ] `sac.divider` separating logical sections?
- [ ] Data functions cached with `@st.cache_data`?
- [ ] RLS applied before any render (`aplicar_rls` → `aplicar_rls_metas` → `aplicar_rls_supervisores`)?