---
name: pandas-numpy
description: Use whenever the task involves data manipulation, cleaning, transformation, or aggregation in Python.
---

# Pandas + NumPy — Data Manipulation

## Options (set once at module level)

```python
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", "{:.2f}".format)
pd.set_option("display.max_colwidth", 80)
```

## Loading Data

```python
df = pd.read_csv("data.csv", sep=",", encoding="utf-8",
                 parse_dates=["date_col"], dtype={"id": str})
df = pd.read_excel("data.xlsx", sheet_name="Sheet1")
```

## Data Cleaning

```python
df.isna().sum()
df.dropna(subset=["critical_col"])
df["col"].fillna(df["col"].median())
df.fillna({"col_a": 0, "col_b": "unknown"})

df.drop_duplicates(subset=["id"], keep="first", inplace=True)

df["price"]    = pd.to_numeric(df["price"], errors="coerce")
df["date"]     = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
df["category"] = df["category"].astype("category")

df["name"] = df["name"].str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
df.rename(columns={"old": "new"}, inplace=True)
```

## Selection & Filtering

```python
df.query("region == 'North' and value > 50")
df.loc[df["id"] == 42, "name"]

mask = (df["age"] >= 18) & (df["status"] == "active") & ~(df["country"] == "BR")
df[mask]

df[df["region"].isin(["North", "South"])]
df[df["age"].between(18, 65)]
```

## Creating & Transforming Columns

```python
df["margin"] = (df["revenue"] - df["cost"]) / df["revenue"]

df["flag"]  = np.where(df["value"] > df["threshold"], 1, 0)

conditions  = [df["score"] >= 0.9, df["score"] >= 0.7, df["score"] >= 0.5]
choices     = ["A", "B", "C"]
df["grade"] = np.select(conditions, choices, default="F")

df["age_group"] = pd.cut(df["age"], bins=[0, 18, 35, 60, 99],
                          labels=["child", "young", "adult", "senior"])
df["quartile"]  = pd.qcut(df["value"], q=4, labels=["Q1","Q2","Q3","Q4"])
```

## Groupby & Aggregation

```python
df.groupby("region").agg(
    total_sales=("sales", "sum"),
    avg_ticket=("sales", "mean"),
    n_orders=("order_id", "count"),
)

df.groupby(["region", "year"])["revenue"].sum().reset_index()

df["region_avg"] = df.groupby("region")["sales"].transform("mean")

pivot = df.pivot_table(
    values="sales", index="region", columns="year",
    aggfunc="sum", fill_value=0, margins=True
)
```

## Merging & Joining

```python
result = pd.merge(df_left, df_right, on="id", how="left")
result = pd.merge(df_orders, df_customers,
                  left_on="customer_id", right_on="id", how="inner")
df_all = pd.concat([df_2022, df_2023, df_2024], ignore_index=True)
```

## Reshaping

```python
df_long = df.melt(id_vars=["id", "region"],
                  value_vars=["q1", "q2", "q3", "q4"],
                  var_name="quarter", value_name="revenue")

df_wide = df_long.pivot(index="id", columns="quarter", values="revenue")
```

## NumPy Essentials

```python
np.where(condition, true_val, false_val)
np.select(conditions, choices, default="F")
np.percentile(arr, [25, 50, 75])

rng = np.random.default_rng(seed=42)

df["pct"] = df["part"] / df["total"].replace(0, np.nan) * 100
```

## Chaining Pattern

```python
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
```

## Pitfalls

| Problem | Fix |
|---|---|
| `SettingWithCopyWarning` | `.copy()` after slicing: `sub = df[mask].copy()` |
| Slow `apply()` | Replace with vectorized Pandas/NumPy operations |
| Duplicate columns after merge | Check `suffixes=("_x","_y")` or rename before merging |
| Lost index after groupby | Add `.reset_index()` |
| Dates parsed as strings | `parse_dates=["col"]` or `pd.to_datetime()` |
| Division by zero | `.replace(0, np.nan)` before dividing |