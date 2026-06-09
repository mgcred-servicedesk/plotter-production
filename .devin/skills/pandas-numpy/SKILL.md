---
name: pandas-numpy
description: Manipulação, limpeza, transformação e agregação de dados com Pandas e NumPy.
---

# Pandas + NumPy — Router

Para padrões específicos do projeto (colunas padronizadas, filtros RLS,
cache), veja `docs/agents/data-layer.md` e `docs/agents/conventions.md`.

## Onde procurar

| Tópico | Doc |
|---|---|
| Colunas padronizadas após `_fetch_*` (LOJA, CONSULTOR, pontos, …) | `docs/agents/data-layer.md` |
| Formatters PT-BR, divisão segura | `docs/agents/conventions.md` |

## Resumo rápido

### Opções (uma vez no módulo)

```python
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", "{:.2f}".format)
pd.set_option("display.max_colwidth", 80)
```

### Carregar

```python
df = pd.read_csv("data.csv", sep=",", encoding="utf-8",
                 parse_dates=["date_col"], dtype={"id": str})
df = pd.read_excel("data.xlsx", sheet_name="Sheet1")
```

### Limpeza

```python
df.isna().sum()
df.dropna(subset=["critical_col"])
df["col"].fillna(df["col"].median())
df.drop_duplicates(subset=["id"], keep="first", inplace=True)

df["price"]    = pd.to_numeric(df["price"], errors="coerce")
df["date"]     = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
df["category"] = df["category"].astype("category")

df["name"] = df["name"].str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
```

### Seleção e filtragem

```python
df.query("region == 'North' and value > 50")
df.loc[df["id"] == 42, "name"]

mask = (df["age"] >= 18) & (df["status"] == "active") & ~(df["country"] == "BR")
df[mask]

df[df["region"].isin(["North", "South"])]
df[df["age"].between(18, 65)]
```

### Criando e transformando colunas

```python
df["margin"] = (df["revenue"] - df["cost"]) / df["revenue"]
df["flag"]   = np.where(df["value"] > df["threshold"], 1, 0)

conditions  = [df["score"] >= 0.9, df["score"] >= 0.7, df["score"] >= 0.5]
choices     = ["A", "B", "C"]
df["grade"] = np.select(conditions, choices, default="F")

df["age_group"] = pd.cut(df["age"], bins=[0, 18, 35, 60, 99],
                          labels=["child", "young", "adult", "senior"])
df["quartile"]  = pd.qcut(df["value"], q=4, labels=["Q1","Q2","Q3","Q4"])
```

### Groupby e agregação

```python
df.groupby("region").agg(
    total_sales=("sales", "sum"),
    avg_ticket=("sales", "mean"),
    n_orders=("order_id", "count"),
)

df.groupby(["region", "year"])["revenue"].sum().reset_index()

df["region_avg"] = df.groupby("region")["sales"].transform("mean")

pivot = df.pivot_table(values="sales", index="region", columns="year",
                       aggfunc="sum", fill_value=0, margins=True)
```

### Merge e concat

```python
result = pd.merge(df_left, df_right, on="id", how="left")
result = pd.merge(df_orders, df_customers,
                  left_on="customer_id", right_on="id", how="inner")
df_all = pd.concat([df_2022, df_2023, df_2024], ignore_index=True)
```

### Reshape

```python
df_long = df.melt(id_vars=["id", "region"],
                  value_vars=["q1", "q2", "q3", "q4"],
                  var_name="quarter", value_name="revenue")

df_wide = df_long.pivot(index="id", columns="quarter", values="revenue")
```

### NumPy essencial

```python
np.where(cond, a, b)
np.select(conds, choices, default="F")
np.percentile(arr, [25, 50, 75])

rng = np.random.default_rng(seed=42)

df["pct"] = df["part"] / df["total"].replace(0, np.nan) * 100  # divisão segura
```

### Chaining

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

| Problema | Correção |
|---|---|
| `SettingWithCopyWarning` | `.copy()` após slice: `sub = df[mask].copy()` |
| `apply()` lento | Vetorizar com Pandas/NumPy |
| Colunas duplicadas após merge | Checar `suffixes=("_x","_y")` ou renomear antes |
| Índice perdido após groupby | `.reset_index()` |
| Datas como string | `parse_dates=` ou `pd.to_datetime()` |
| Divisão por zero | `.replace(0, np.nan)` antes de dividir |
