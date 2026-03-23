# CLAUDE.md — Project Guidelines

## Project Overview

Sales analysis system for a financial products company. Processes monthly sales data (Excel/CSV in Brazilian Portuguese), calculates a point-based scoring system per product, and generates:
- Interactive **Streamlit** dashboard (`src/dashboard/app.py`)
- Automated **Excel** reports (`gerar_relatorio.py`)
- **PDF** reports: executive, complete, regional, per-product (`gerar_relatorio_pdf.py`)

### Key Business Rules
- Points = Value × PTS (from product table)
- **Card issuance** (`CARTÃO BENEFICIO`, `Venda Pré-Adesão`): count only as quantity, excluded from values/points
- **Insurance** (`BMG MED` → "Med", `Seguro` → "Vida Familiar"): count only as quantity, excluded from values/points. Identified via `TIPO OPER.` field. **In the Supabase dashboard**, these contracts do NOT have `status_pagamento_cliente = 'PAGO AO CLIENTE'` — they are loaded via `sub_status_banco = 'Liquidada'` combined with `tipo_operacao IN ('BMG MED', 'Seguro')`
- **Super Conta** (`SUBTIPO = SUPER CONTA`): CNC subtype — counts for values/points as CNC AND is counted separately as Super Conta production quantity. In the Supabase DB, category `SUPER_CONTA` must have `grupo_dashboard = 'CNC'` and its own entry in the `pontuacao` table with the same multiplier as CNC
- Meta Prata (base target) and Meta Ouro (premium target) in points
- Daily target = (Meta Prata - Current Points) / Remaining Business Days

### Pipeline (Em Análise) Rules
The source system only returns two values for `status_banco`: `EM ANALISE` and `CANCELADO`. It does **not** update `status_banco` when a proposal is paid. The dashboard applies the following filters to determine what appears in the analysis pipeline:

| Excluded condition | Reason |
|---|---|
| `status_pagamento_cliente = 'PAGO AO CLIENTE'` | Already paid — remove from pipeline |
| `status_banco = 'CANCELADO'` | Cancelled — must not appear |
| `sub_status_banco = 'Liquidada'` | Insurance paid (BMG Med / Vida Familiar) — already settled |

### Authentication & Row-Level Security
- Login required to access the dashboard (bcrypt-hashed passwords)
- User store: `configuracao/usuarios.json`
- **Roles**:
  - `admin` — full access to all data; can "view as" other profiles; manages users
  - `gerente_comercial` — restricted to assigned region(s) via `escopo`
  - `supervisor` — restricted to assigned store(s) via `escopo`
- RLS is applied immediately after data load, before any filtering or KPI calculation
- Admin "Visualizar Como" allows simulating any profile/scope combination
- Default credentials: `admin` / `admin123` (change after first login)

---

## Project Stack

```
Python 3.11+ | Pandas 2.2+ | NumPy 1.26+ | Plotly 5.20+
Matplotlib 3.8+ | Streamlit 1.35+ | Seaborn 0.13+
openpyxl | kaleido | ReportLab | python-dotenv
bcrypt | pytest | ruff | uv
```

---

## Project Structure

```
src/
├── config/settings.py          # Centralized constants and business mappings
├── data_processing/
│   ├── loader.py               # Unified pipeline: carregar_e_processar_dados(mes, ano)
│   ├── column_mapper.py        # Column mapping from source files
│   ├── business_rules.py       # Exclusion and classification rules
│   ├── consolidator.py         # Data consolidation
│   ├── pontuacao_loader.py     # Monthly scoring table loader
│   ├── points_calculator.py    # Scoring system
│   └── transformer.py          # Data transformations
├── reports/
│   ├── formatters.py           # Shared formatting: formatar_moeda(), formatar_percentual(), etc.
│   ├── pdf_styles.py           # Centralized PDF styles, colors, footer
│   ├── pdf_executivo.py        # Executive PDF (KPIs + charts)
│   ├── pdf_completo.py         # Full rankings PDF
│   ├── pdf_regional.py         # Per-region PDFs
│   ├── pdf_produto.py          # Per-product PDFs
│   ├── pdf_charts.py           # Matplotlib charts for PDFs
│   └── resumo_geral.py         # Consolidated summary data
├── dashboard/
│   ├── app.py                  # Streamlit app (original)
│   ├── auth.py                 # Authentication: login, logout, bcrypt passwords
│   ├── rls.py                  # Row-Level Security: per-profile data filtering
│   ├── user_mgmt.py            # User management UI (admin CRUD, password change)
│   ├── kpi_dashboard.py        # Dashboard KPI calculations
│   ├── kpi_analiticos.py       # Analytical KPI calculations
│   └── components/
│       └── tables.py           # AG Grid / st.dataframe with auto-formatting
└── analysis/                   # Comparative analyses
```

---

## Code Style

- **Language**: Code in English; comments, docstrings, and documentation in **Brazilian Portuguese**
- **Conventions**: PEP 8 — `snake_case` functions/variables, `CamelCase` classes, `UPPER_CASE` constants
- **Indentation**: 4 spaces; max line length 79 chars (72 for comments/docstrings)
- **Functions**: Small and focused; avoid duplication; use type hints where practical
- **Comments**: Only where logic isn't self-evident; no unnecessary logs or debug prints
- **Secrets**: Never log, expose, or commit credentials or tokens

---

## Data Notes

- Source files: Excel (`.xlsx`) in Brazilian Portuguese with Brazilian currency format (R$ X.XXX,XX)
- Use `openpyxl` for Excel reads; `parse_dates` or `pd.to_datetime()` for date columns
- Numeric columns may need `pd.to_numeric(errors="coerce")` due to mixed types in source data
- Configuration files live in `configuracao/`: HC_Colaboradores.xlsx, loja_regiao.xlsx, Supervisores.xlsx
- Supervisors are excluded from consultant-level analyses

---

## Coding Behavior Rules

### Before Coding
- State understanding of the task before writing any code
- Confirm the plan with the user before starting
- Never infer missing requirements — list open questions first
- If multiple approaches exist, present options and trade-offs
- Identify which existing files/modules the change touches before proposing anything

### During Coding
- **Never install new packages without asking first**
- Prefer editing existing code over creating new abstractions
- When refactoring, change only what the task requires — no unrelated cleanups
- Do not introduce new patterns not already present in the codebase without flagging them
- Follow existing naming conventions without asking; document the choice afterward if no convention exists
- For error handling: follow existing patterns in the codebase; if none exists and impact is low, apply language idioms and document; if high-impact, stop and discuss
- **Never silently swallow errors**

### Code Deletion
- Never delete or deprecate existing code unilaterally
- If code appears unused, flag it with description, reason it seems unnecessary, and consequences of removal
- Wait for explicit confirmation before taking any action

### After Coding
- Run `ruff check` and fix any errors introduced by the changes
- Summarize every decision made, including alternatives discarded and why
- List any assumptions explicitly so the user can validate them
- Ask the user to update project context files when the task is complete

### Decision Tiers
| Tier | Actions |
|------|---------|
| **Always do** (no confirmation) | Follow existing patterns, apply standard idioms, fix errors you introduced |
| **Ask first** | New files with structural decisions, new dependencies, module boundaries, error handling without an established pattern |
| **Never without explicit instruction** | Delete/deprecate code, create config/infrastructure files, change public APIs, log or commit credentials |

---

## Visualization Guidelines

### Plotly (interactive charts)
- Prefer `plotly.express` (`px`) for standard charts; use `plotly.graph_objects` (`go`) for customization
- Always use `st.plotly_chart(fig, use_container_width=True)` in Streamlit
- For subplots: use `make_subplots` from `plotly.subplots` (see `references/subplots-layout.md`)
- Export static images with `fig.write_image()` (requires kaleido)

### Seaborn (statistical charts for PDFs/notebooks)
- Always set theme first: `sns.set_theme(style="whitegrid", palette="muted")`
- Use axes-level functions (`sns.histplot`, `sns.boxplot`) with `ax=` param for fine-grained control
- For advanced customization, use Matplotlib interop (see `references/matplotlib-interop.md`)

### Dashboard Design Principles
- **5–10 KPIs maximum per screen** — if everything is important, nothing is
- Always include context: compare with previous period, show targets, use deltas
- Use correct chart types: line for trends, bar for comparisons, funnel for conversion, pie sparingly (≤5 categories)
- Focus on **actionable metrics** (conversion rate, CAC, ROI) not vanity metrics (total pageviews)
- Define and reuse a consistent color palette:
  ```python
  CORES = {
      "primary": "#1976d2",
      "secondary": "#1565c0",
      "success": "#2e7d32",
      "warning": "#f57c00",
      "danger": "#c62828",
      "neutral": "#757575",
  }
  ```
- `layout="wide"` for all dashboards; `use_container_width=True` for all charts
- Filters belong in the sidebar (`st.sidebar`)

### Streamlit Best Practices
- Use `@st.cache_data` for DataFrames and files; `@st.cache_resource` for connections/models
- Organize with functions: `show_kpis()`, `show_charts()`, called from `main()`
- Use `st.session_state` for persistent state across reruns

---

## Pandas/NumPy Best Practices

- Prefer vectorized operations over `apply()`, and `apply()` over loops
- Use method chaining (`.query().assign().groupby().agg()`) for readability
- Safe division: `df["pct"] = df["part"] / df["total"].replace(0, np.nan) * 100`
- After slicing: `sub = df[mask].copy()` to avoid `SettingWithCopyWarning`
- For large files: read with `usecols=`, filter early, consider Parquet for repeated reads
- Time series: use `pd.to_datetime()`, set index with `.set_index("date").sort_index()`

---

## Testing

```bash
pytest tests/
ruff check src/
```

- Add tests for new functionality before committing
- Tests live in `tests/`; see `tests/README.md` for organization

---

## Running the Project

```bash
# Dashboard
streamlit run src/dashboard/app.py

# Excel report
python gerar_relatorio.py

# PDF reports (13 files)
python gerar_relatorio_pdf.py
```

Outputs: `outputs/relatorios_excel/` and `outputs/relatorios_pdf/`
