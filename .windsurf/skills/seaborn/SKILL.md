---
name: seaborn
description: Use for static statistical plots and EDA. For dashboard charts, use plotly instead.
---

# Seaborn — Statistical Visualization

## Setup

```python
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
```

## Correlation Heatmap (most common use in this project)

```python
corr = df.select_dtypes("number").corr()
mask = np.triu(np.ones_like(corr, dtype=bool))  # hide upper triangle

fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm",
            mask=mask, vmin=-1, vmax=1, linewidths=0.5, ax=ax)
plt.tight_layout()
```

## Distribution + KDE

```python
sns.histplot(data=df, x="col", kde=True, bins=30)
sns.kdeplot(data=df, x="col", hue="group", fill=True, alpha=0.4)
```

## Categorical

```python
# Box with outliers
sns.boxplot(data=df, x="category", y="value", hue="group")

# Overlay violin + strip for full picture
fig, ax = plt.subplots()
sns.violinplot(data=df, x="day", y="value", inner=None, ax=ax)
sns.stripplot(data=df, x="day", y="value", color="black", alpha=0.4, ax=ax)
```

## Saving

```python
fig = plt.gcf()  # axes-level functions
fig.savefig("plot.png", dpi=150, bbox_inches="tight")
plt.close(fig)   # always close to free memory
```

## Pitfalls

| Problem | Fix |
|---|---|
| Axes-level vs figure-level confusion | `sns.histplot` → `Axes`; `sns.displot` → `Grid` object |
| Plot empty in Streamlit | `st.pyplot(fig)` — pass the figure explicitly |
| Hue not showing | `df[col].astype("category")` before plotting |
| Labels overlapping | `plt.xticks(rotation=45, ha="right")` |