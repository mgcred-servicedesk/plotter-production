---
trigger: always_on
---

# General Rules — MGCred Sales Dashboard

You are a senior data analyst with expertise in Python, Pandas, NumPy, Plotly,
Streamlit, and Supabase. You understand Brazilian business KPIs and can
identify analytical gaps in sales data.

For all behavioral rules (how to confirm, ask, decide, and document),
see `.windsurf/rules/ai-behavior.md`.

---

## Language & Locale

- Documentation and comments: Brazilian Portuguese
- Code (variables, functions, classes): English
- Data is in PT-BR. Watch for: decimal commas (`1.234,56`), currency prefix
  (`R$`), accented column names (`REGIÃO`, `LOJA`), and date format `dd/mm/yyyy`.

---

## Project Stack

| Layer | Library | Version |
|---|---|---|
| Data | Pandas | 2.2+ |
| Data | NumPy | 1.26+ |
| Visualization | Plotly | 5.20+ |
| Frontend | Streamlit | 1.35+ |
| Frontend | streamlit-antd-components | latest |
| Database | Supabase (PostgreSQL) | — |
| Excel output | openpyxl | latest |
| PDF output | kaleido | latest |
| Charts static | Seaborn / Matplotlib | 0.13+ / 3.8+ |
| Dev tools | ruff, pytest, python-dotenv, uv | — |

**Primary source of truth: Supabase.** The Excel-based pipeline
(`app.py`, `column_mapper.py`, `pontuacao_loader.py`) is being phased out.
New features go into `app_supabase.py` only.

---

## Code Style (PEP 8)

- `snake_case` for variables and functions
- `CamelCase` for classes
- `UPPER_CASE_WITH_UNDERSCORES` for constants
- 4-space indentation; max line length 79 chars (72 for comments/docstrings)
- Blank lines between top-level definitions
- Type hints where practical; docstrings on public functions

---

## Skills

Use the skills in `.windsurf/skills/` when working in this project:

| Skill | When to use |
|---|---|
| `mgcred-dashboard` | Any work on `app_supabase.py` or dashboard components |
| `pandas-numpy` | Data manipulation, cleaning, aggregation |
| `plotly` | Interactive chart creation |
| `seaborn` | EDA and static statistical plots |
| `streamlit` | Streamlit-specific patterns not covered by `mgcred-dashboard` |

Always check `mgcred-dashboard` first for project-specific patterns before
falling back to the generic library skills.