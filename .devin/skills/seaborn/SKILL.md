---
name: seaborn
description: Gráficos estatísticos estáticos (EDA e PDFs). Para gráficos do dashboard, use plotly.
---

# Seaborn — Router

Para dashboard interativo, use **plotly**. Seaborn é usado apenas em EDA e
relatórios PDF (via `src/reports/pdf_charts.py`).

## Onde procurar

| Tópico | Doc |
|---|---|
| Geração de PDFs | `src/reports/pdf_charts.py`, `src/reports/pdf_styles.py` |
| Paleta do projeto (para manter consistência visual) | `docs/agents/conventions.md` |

## Resumo rápido

### Setup

```python
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
```

### Heatmap de correlação (uso mais comum)

```python
corr = df.select_dtypes("number").corr()
mask = np.triu(np.ones_like(corr, dtype=bool))  # esconder triângulo superior

fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm",
            mask=mask, vmin=-1, vmax=1, linewidths=0.5, ax=ax)
plt.tight_layout()
```

### Distribuição + KDE

```python
sns.histplot(data=df, x="col", kde=True, bins=30)
sns.kdeplot(data=df, x="col", hue="group", fill=True, alpha=0.4)
```

### Categóricos

```python
sns.boxplot(data=df, x="category", y="value", hue="group")

fig, ax = plt.subplots()
sns.violinplot(data=df, x="day", y="value", inner=None, ax=ax)
sns.stripplot(data=df, x="day", y="value", color="black", alpha=0.4, ax=ax)
```

### Salvar

```python
fig = plt.gcf()
fig.savefig("plot.png", dpi=150, bbox_inches="tight")
plt.close(fig)   # sempre fechar para liberar memória
```

## Pitfalls

| Problema | Correção |
|---|---|
| Confusão axes-level × figure-level | `sns.histplot` → `Axes`; `sns.displot` → `Grid` |
| Plot vazio no Streamlit | `st.pyplot(fig)` — passar a figura explicitamente |
| `hue` não mostra | `df[col].astype("category")` antes de plotar |
| Labels sobrepostos | `plt.xticks(rotation=45, ha="right")` |
