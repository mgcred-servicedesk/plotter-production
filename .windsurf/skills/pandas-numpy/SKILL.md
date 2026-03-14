---
name: pandas-numpy
description: Use this skill whenever the user needs to manipulate, clean, transform, or analyze tabular data in Python.
---

# Pandas + NumPy — Data Manipulation & Analysis
 
NumPy provides the array foundation; Pandas builds the tabular API on top of it.
For time series specifics, see `references/timeseries.md`.
For performance and large datasets, see `references/performance.md`.
 
---
 
## 1. Imports & Setup
 
```python
import pandas as pd
import numpy as np
 
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", "{:.2f}".format)
pd.set_option("display.max_colwidth", 80)
```
 
---
 
## 2. Loading Data
 
```python
# CSV
df = pd.read_csv("data.csv", sep=",", encoding="utf-8",
                 parse_dates=["date_col"], dtype={"id": str})
 
# Excel (requires openpyxl)
df = pd.read_excel("data.xlsx", sheet_name="Sheet1", header=0)
 
# JSON
df = pd.read_json("data.json", orient="records")
 
# From dict / list
df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
 
# Quick inspection
df.head()
df.info()
df.describe()
df.shape           # (rows, cols)
df.dtypes
df.value_counts()  # on a Series
```
 
---
 
## 3. Data Cleaning
 
```python
# Missing values
df.isna().sum()                              # count per column
df.dropna(subset=["critical_col"])           # drop rows
df["col"].fillna(df["col"].median())         # fill with median
df.fillna({"col_a": 0, "col_b": "unknown"}) # fill per column
 
# Duplicates
df.duplicated().sum()
df.drop_duplicates(subset=["id"], keep="first", inplace=True)
 
# Type conversion
df["price"]    = pd.to_numeric(df["price"], errors="coerce")
df["date"]     = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
df["category"] = df["category"].astype("category")
 
# String cleaning
df["name"] = (df["name"]
              .str.strip()
              .str.lower()
              .str.replace(r"\s+", " ", regex=True))
 
# Rename & reorder columns
df.rename(columns={"old": "new"}, inplace=True)
df = df[["id", "name", "date", "value"]]  # select + reorder
```
 
---
 
## 4. Selection & Filtering
 
```python
# Column selection
df["col"]                        # Series
df[["col_a", "col_b"]]           # DataFrame
 
# Row filtering
df[df["value"] > 100]
df.query("region == 'North' and value > 50")  # readable syntax
 
# loc (label-based) / iloc (position-based)
df.loc[df["id"] == 42, "name"]
df.iloc[0:5, 2:4]
 
# Multiple conditions
mask = (df["age"] >= 18) & (df["status"] == "active") & ~(df["country"] == "BR")
df[mask]
 
# isin / between
df[df["region"].isin(["North", "South"])]
df[df["age"].between(18, 65)]
```
 
---
 
## 5. Creating & Transforming Columns
 
```python
# Arithmetic
df["margin"] = (df["revenue"] - df["cost"]) / df["revenue"]
 
# Apply (use vectorized ops when possible — apply is slower)
df["label"] = df["score"].apply(lambda x: "high" if x > 0.8 else "low")
 
# np.where (vectorized if/else)
df["flag"] = np.where(df["value"] > df["threshold"], 1, 0)
 
# np.select (multiple conditions)
conditions  = [df["score"] >= 0.9, df["score"] >= 0.7, df["score"] >= 0.5]
choices     = ["A", "B", "C"]
df["grade"] = np.select(conditions, choices, default="F")
 
# cut / qcut (binning)
df["age_group"] = pd.cut(df["age"], bins=[0, 18, 35, 60, 99],
                          labels=["child", "young", "adult", "senior"])
df["quartile"]  = pd.qcut(df["value"], q=4, labels=["Q1","Q2","Q3","Q4"])
 
# One-hot encoding
dummies = pd.get_dummies(df["category"], prefix="cat", drop_first=True)
df = pd.concat([df, dummies], axis=1)
```
 
---
 
## 6. Groupby & Aggregation
 
```python
# Single aggregation
df.groupby("region")["sales"].sum()
 
# Multiple aggregations
df.groupby("region").agg(
    total_sales=("sales", "sum"),
    avg_ticket=("sales", "mean"),
    n_orders=("order_id", "count"),
    max_value=("value", "max"),
)
 
# Multiple keys
df.groupby(["region", "year"])["revenue"].sum().reset_index()
 
# Transform (keeps original index — useful for adding group stats back)
df["region_avg"] = df.groupby("region")["sales"].transform("mean")
df["rank"]       = df.groupby("region")["sales"].rank(ascending=False)
 
# Pivot table
pivot = df.pivot_table(
    values="sales", index="region", columns="year",
    aggfunc="sum", fill_value=0, margins=True
)
```
 
---
 
## 7. Merging & Joining
 
```python
# Merge (SQL-style join)
result = pd.merge(df_left, df_right, on="id", how="left")
# how: inner | left | right | outer | cross
 
# Merge on different column names
result = pd.merge(df_orders, df_customers,
                  left_on="customer_id", right_on="id", how="inner")
 
# Concatenate
df_all = pd.concat([df_2022, df_2023, df_2024], ignore_index=True)
df_wide = pd.concat([df_main, df_features], axis=1)  # side by side
```
 
---
 
## 8. Reshaping
 
```python
# Wide → Long
df_long = df.melt(id_vars=["id", "region"],
                  value_vars=["q1", "q2", "q3", "q4"],
                  var_name="quarter", value_name="revenue")
 
# Long → Wide
df_wide = df_long.pivot(index="id", columns="quarter", values="revenue")
 
# Stack / Unstack (MultiIndex operations)
df.stack()     # columns → rows
df.unstack()   # inner row index → columns
```
 
---
 
## 9. NumPy Essentials
 
```python
# Array creation
arr = np.array([1, 2, 3, 4, 5])
zeros = np.zeros((3, 4))
ones  = np.ones((3, 4))
rng   = np.arange(0, 10, 0.5)     # like range() with floats
space = np.linspace(0, 1, 100)    # 100 evenly spaced points
 
# Random (use Generator — modern API)
rng = np.random.default_rng(seed=42)
samples = rng.normal(loc=0, scale=1, size=(100, 5))
ints    = rng.integers(0, 10, size=50)
 
# Math & statistics
np.mean(arr), np.median(arr), np.std(arr), np.var(arr)
np.percentile(arr, [25, 50, 75])
np.corrcoef(x, y)          # correlation matrix
np.dot(A, B)               # matrix multiplication (also A @ B)
 
# Boolean masking
arr[arr > 3]               # filter
arr[(arr > 1) & (arr < 4)]
 
# Vectorized operations (avoid Python loops)
result = np.sqrt(arr) * 2 + np.log1p(arr)
```
 
---
 
## 10. Common Patterns
 
```python
# ── Chaining (fluent API) ─────────────────────────────────────────────────
result = (
    df
    .query("year >= 2022")
    .dropna(subset=["revenue"])
    .assign(margin=lambda x: x["revenue"] / x["cost"])
    .groupby("region")
    .agg(total=("revenue", "sum"), avg_margin=("margin", "mean"))
    .sort_values("total", ascending=False)
    .reset_index()
)
 
# ── Safe percentage calculation ───────────────────────────────────────────
df["pct"] = df["part"] / df["total"].replace(0, np.nan) * 100
 
# ── Explode list columns ──────────────────────────────────────────────────
df_exploded = df.explode("tags").reset_index(drop=True)
 
# ── Sample & split ────────────────────────────────────────────────────────
df_sample = df.sample(frac=0.1, random_state=42)
train = df.sample(frac=0.8, random_state=42)
test  = df.drop(train.index)
```
 
---
 
## 11. Common Pitfalls
 
| Problem | Fix |
|---|---|
| `SettingWithCopyWarning` | Use `.copy()` after slicing: `sub = df[mask].copy()` |
| Slow `apply()` | Replace with vectorized Pandas/NumPy ops |
| `merge` creates duplicate columns | Check `suffixes=("_x","_y")` or rename before merging |
| Lost index after groupby | Add `.reset_index()` |
| `read_csv` parses dates as strings | Use `parse_dates=["col"]` or `pd.to_datetime()` |
| Category column breaks groupby | Call `.astype(str)` before groupby if needed |
 
For time series: see `references/timeseries.md`
For large data / performance: see `references/performance.md`
 

