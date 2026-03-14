# Matplotlib Interoperability
 
Use this reference when Seaborn alone isn't enough — e.g., twin axes, custom annotations, 
complex subplot layouts, or fine-grained tick control.
 
## Accessing the Underlying Axes
 
```python
# Axes-level: all seaborn functions accept `ax=`
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
sns.histplot(data=df, x="age", ax=ax1)
sns.boxplot(data=df, x="group", y="value", ax=ax2)
plt.tight_layout()
```
 
## Twin Axes (dual Y-axis)
 
```python
fig, ax1 = plt.subplots(figsize=(10, 5))
ax2 = ax1.twinx()
 
sns.lineplot(data=df, x="date", y="revenue", ax=ax1, color="steelblue")
sns.lineplot(data=df, x="date", y="units", ax=ax2, color="coral")
 
ax1.set_ylabel("Revenue", color="steelblue")
ax2.set_ylabel("Units", color="coral")
```
 
## Annotations
 
```python
ax = sns.barplot(data=df, x="category", y="value")
 
# Annotate bar values
for container in ax.containers:
    ax.bar_label(container, fmt="%.1f", padding=3)
 
# Arrow annotation
ax.annotate("Peak", xy=(2, 95), xytext=(3.5, 90),
            arrowprops=dict(arrowstyle="->", color="red"), color="red")
```
 
## Subplot Grid with Seaborn + Matplotlib
 
```python
fig = plt.figure(figsize=(14, 10))
gs = fig.add_gridspec(2, 3, hspace=0.4, wspace=0.3)
 
ax_main = fig.add_subplot(gs[0, :])     # spans full top row
ax_bl   = fig.add_subplot(gs[1, 0])
ax_bc   = fig.add_subplot(gs[1, 1])
ax_br   = fig.add_subplot(gs[1, 2])
 
sns.lineplot(data=df, x="date", y="total", ax=ax_main)
sns.histplot(data=df, x="age", ax=ax_bl)
sns.boxplot(data=df, x="group", y="score", ax=ax_bc)
sns.heatmap(corr, ax=ax_br, annot=True, fmt=".1f")
```
 
## Removing / Styling Spines
 
```python
ax = sns.scatterplot(data=df, x="x", y="y")
sns.despine(left=False, bottom=False)    # remove top/right spines (default)
ax.spines["left"].set_linewidth(1.5)
```
 
## Legend Control
 
```python
# Move legend outside plot
ax = sns.lineplot(data=df, x="x", y="y", hue="group")
ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", borderaxespad=0)
plt.tight_layout()
```
 
