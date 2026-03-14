---
name: seaborn
description: Use this skill whenever the user wants to create statistical data visualizations in Python using Seaborn.
---

# Seaborn — Statistical Data Visualization
 
Seaborn is built on top of Matplotlib and integrates natively with Pandas DataFrames.
For complex chart customization beyond what's listed here, read `references/matplotlib-interop.md`.
 
---
 
## 1. Setup & Theming
 
```python
import seaborn as sns
import matplotlib.pyplot as plt
 
# Always set theme at the start
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.2)
 
# Styles: whitegrid | darkgrid | white | dark | ticks
# Palettes: muted | deep | pastel | bright | colorblind | husl | flare | crest
# Custom palette
sns.set_palette(["#2ecc71", "#e74c3c", "#3498db"])
 
# Figure size (set via matplotlib)
plt.figure(figsize=(10, 6))
```
 
---
 
## 2. Distribution Plots
 
```python
# Histogram + KDE
sns.histplot(data=df, x="age", kde=True, bins=30, color="steelblue")
 
# KDE only (smooth density)
sns.kdeplot(data=df, x="income", hue="region", fill=True, alpha=0.4)
 
# KDE 2D (bivariate)
sns.kdeplot(data=df, x="height", y="weight", fill=True, cmap="Blues")
 
# ECDF (cumulative distribution)
sns.ecdfplot(data=df, x="score", hue="group")
 
# Combined view: histogram + rug + KDE
sns.displot(data=df, x="salary", kde=True, rug=True, height=5, aspect=1.5)
```
 
---
 
## 3. Categorical Plots
 
```python
# Boxplot — distribution summary + outliers
sns.boxplot(data=df, x="category", y="value", hue="group", palette="Set2")
 
# Violin — boxplot + full KDE
sns.violinplot(data=df, x="day", y="total_bill", hue="sex", split=True)
 
# Stripplot — raw data points
sns.stripplot(data=df, x="species", y="petal_length", jitter=True, alpha=0.6)
 
# Combine violin + strip for maximum info
fig, ax = plt.subplots()
sns.violinplot(data=df, x="day", y="tip", inner=None, ax=ax)
sns.stripplot(data=df, x="day", y="tip", color="black", alpha=0.4, ax=ax)
 
# Bar (mean + CI) and Count
sns.barplot(data=df, x="region", y="sales", hue="year", errorbar="ci")
sns.countplot(data=df, x="category", order=df["category"].value_counts().index)
 
# Swarmplot (non-overlapping points — avoid for n > 1000)
sns.swarmplot(data=df, x="group", y="value", hue="sex")
```
 
---
 
## 4. Relational Plots
 
```python
# Scatter
sns.scatterplot(data=df, x="gdp", y="happiness", hue="continent",
                size="population", style="region", alpha=0.8)
 
# Line with CI
sns.lineplot(data=df, x="date", y="value", hue="category",
             errorbar="sd", dashes=False, markers=True)
 
# Regression line + scatter
sns.regplot(data=df, x="x", y="y", ci=95, scatter_kws={"alpha": 0.3})
 
# Regression with faceting + hue
sns.lmplot(data=df, x="x", y="y", hue="group", col="region",
           height=4, aspect=0.8)
```
 
---
 
## 5. Matrix Plots
 
```python
# Heatmap (correlation matrix)
corr = df.select_dtypes("number").corr()
mask = np.triu(np.ones_like(corr, dtype=bool))  # hide upper triangle
 
sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm",
            mask=mask, vmin=-1, vmax=1, linewidths=0.5)
 
# Clustermap (hierarchical clustering + heatmap)
sns.clustermap(corr, cmap="vlag", figsize=(10, 10),
               annot=True, fmt=".2f", method="ward")
```
 
---
 
## 6. Multi-Plot Grids
 
```python
# Pairplot — all pairwise relationships
sns.pairplot(df, hue="species", diag_kind="kde",
             plot_kws={"alpha": 0.5}, corner=True)
 
# FacetGrid — custom grid layout
g = sns.FacetGrid(df, col="region", row="year", height=3, aspect=1.2)
g.map_dataframe(sns.histplot, x="sales", kde=True)
g.set_axis_labels("Sales", "Count")
g.add_legend()
 
# catplot — figure-level categorical API
sns.catplot(data=df, x="day", y="total_bill", hue="sex",
            kind="violin", col="time", height=4)
```
 
---
 
## 7. Hue / Size / Style Semantics
 
| Parameter | Use for | Example |
|---|---|---|
| `hue` | Categorical grouping by color | `hue="continent"` |
| `size` | Quantitative encoding by marker size | `size="population"` |
| `style` | Categorical grouping by marker shape | `style="region"` |
| `palette` | Color mapping for hue | `palette="viridis"` |
| `hue_order` | Control hue category order | `hue_order=["A","B","C"]` |
| `sizes` | Range for size encoding | `sizes=(20, 200)` |
 
---
 
## 8. Saving & Post-processing
 
```python
# Always get the Figure object for saving
fig = plt.gcf()         # for axes-level functions
# or
g = sns.pairplot(...)   # figure-level functions return a Grid
fig = g.figure
 
# Save high-res
fig.savefig("plot.png", dpi=150, bbox_inches="tight")
fig.savefig("plot.pdf", bbox_inches="tight")          # vector
 
# Adjust after plotting
plt.title("My Title", fontsize=14, fontweight="bold")
plt.xlabel("X Label")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.show()
```
 
---
 
## 9. Common Pitfalls
 
| Problem | Fix |
|---|---|
| Plot appears empty | Call `plt.show()` or `st.pyplot(fig)` in Streamlit |
| Axes-level vs figure-level API confusion | Axes-level (`sns.histplot`) returns `Axes`; figure-level (`sns.displot`) returns `Grid` |
| Hue not showing | Ensure column is categorical; use `df[col].astype("category")` |
| Clustermap ignores `figsize` | Use `figsize=` param directly on `clustermap()` |
| Font too small | `sns.set_theme(font_scale=1.3)` |
| Overlapping x-labels | `plt.xticks(rotation=45, ha="right")` |
 
---
 
## 10. Quick EDA Template
 
```python
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
 
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
 
def quick_eda(df, target: str):
    numeric = df.select_dtypes("number").columns.tolist()
 
    # 1. Distributions
    fig, axes = plt.subplots(1, len(numeric), figsize=(5 * len(numeric), 4))
    for ax, col in zip(axes, numeric):
        sns.histplot(df[col], kde=True, ax=ax)
        ax.set_title(col)
    plt.tight_layout()
    plt.savefig("distributions.png", dpi=120, bbox_inches="tight")
 
    # 2. Correlation heatmap
    fig, ax = plt.subplots(figsize=(10, 8))
    corr = df[numeric].corr()
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm",
                mask=mask, ax=ax)
    plt.tight_layout()
    plt.savefig("correlation.png", dpi=120, bbox_inches="tight")
 
    # 3. Target vs features
    for col in numeric:
        if col != target:
            fig, ax = plt.subplots(figsize=(6, 4))
            sns.scatterplot(data=df, x=col, y=target, alpha=0.5, ax=ax)
            sns.regplot(data=df, x=col, y=target, scatter=False,
                        color="red", ax=ax)
            plt.tight_layout()
            plt.savefig(f"{col}_vs_{target}.png", dpi=120, bbox_inches="tight")
```
 
For advanced Matplotlib customization (twin axes, annotations, subplots), see `references/matplotlib-interop.md`.
