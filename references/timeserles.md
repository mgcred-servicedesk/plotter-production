# Time Series with Pandas
 
## Parsing & Indexing
 
```python
df["date"] = pd.to_datetime(df["date"])
df = df.set_index("date").sort_index()
 
# DatetimeIndex
df["2023"]                    # full year slice
df["2023-01":"2023-06"]       # date range slice
df.loc["2023-01-15"]          # specific date
```
 
## Resampling (like groupby for time)
 
```python
# Downsample: daily → monthly
monthly = df["value"].resample("ME").sum()    # ME = Month End
weekly  = df["value"].resample("W").mean()
yearly  = df["value"].resample("YE").agg({"sales": "sum", "orders": "count"})
 
# Upsample + interpolate
daily = df.resample("D").interpolate("linear")
```
 
## Offset Aliases
 
| Alias | Meaning |
|---|---|
| `D` | Calendar day |
| `W` | Weekly |
| `ME` | Month end |
| `MS` | Month start |
| `QE` | Quarter end |
| `YE` | Year end |
| `h` | Hour |
| `min` | Minute |
 
## Rolling & Expanding Windows
 
```python
# Rolling mean (moving average)
df["ma_7"]  = df["value"].rolling(window=7).mean()
df["ma_30"] = df["value"].rolling(window=30).mean()
 
# Rolling with min_periods (avoid NaN at start)
df["ma_7"] = df["value"].rolling(7, min_periods=1).mean()
 
# Expanding (cumulative)
df["cumsum"]  = df["value"].expanding().sum()
df["cum_max"] = df["value"].expanding().max()
```
 
## Date Features (for ML / EDA)
 
```python
df["year"]      = df.index.year
df["month"]     = df.index.month
df["dayofweek"] = df.index.dayofweek   # 0=Mon, 6=Sun
df["quarter"]   = df.index.quarter
df["is_weekend"] = df.index.dayofweek >= 5
 
# Lag features
df["lag_1"] = df["value"].shift(1)
df["lag_7"] = df["value"].shift(7)
 
# Difference (stationarity)
df["diff_1"] = df["value"].diff(1)
```
 
## Period Arithmetic
 
```python
# Date offsets
df["next_month"]   = df["date"] + pd.DateOffset(months=1)
df["prev_quarter"] = df["date"] - pd.DateOffset(months=3)
 
# Business days
df["due_date"] = df["date"] + pd.offsets.BDay(5)  # 5 business days ahead
 
# Time between dates
df["tenure_days"] = (pd.Timestamp.today() - df["start_date"]).dt.days
```
 
