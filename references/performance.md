# Performance & Large Datasets
 
## Profiling First
 
```python
# Check where the bottleneck is before optimizing
%timeit df.groupby("region")["value"].sum()
 
import cProfile
cProfile.run("my_function(df)")
```
 
## Memory Reduction
 
```python
def reduce_memory(df):
    for col in df.select_dtypes("integer"):
        df[col] = pd.to_numeric(df[col], downcast="integer")
    for col in df.select_dtypes("float"):
        df[col] = pd.to_numeric(df[col], downcast="float")
    for col in df.select_dtypes("object"):
        if df[col].nunique() / len(df) < 0.5:  # <50% unique → category
            df[col] = df[col].astype("category")
    return df
 
print(f"Before: {df.memory_usage(deep=True).sum() / 1e6:.1f} MB")
df = reduce_memory(df)
print(f"After:  {df.memory_usage(deep=True).sum() / 1e6:.1f} MB")
```
 
## Vectorized > Apply > Loop
 
```python
# SLOW: Python loop
for i, row in df.iterrows():
    df.at[i, "result"] = row["a"] * row["b"]
 
# FASTER: apply (still Python overhead)
df["result"] = df.apply(lambda r: r["a"] * r["b"], axis=1)
 
# FASTEST: vectorized (NumPy under the hood)
df["result"] = df["a"] * df["b"]
 
# When apply is unavoidable, use axis=1 only if needed
# Prefer axis=0 (column-wise) — it's ~10x faster
```
 
## Reading Large Files
 
```python
# Read in chunks
chunk_list = []
for chunk in pd.read_csv("large.csv", chunksize=50_000):
    chunk = chunk[chunk["value"] > 0]   # filter early
    chunk_list.append(chunk)
df = pd.concat(chunk_list, ignore_index=True)
 
# Select only needed columns
df = pd.read_csv("data.csv", usecols=["id", "date", "value"])
 
# Use Parquet for repeated reads (10-50x faster than CSV)
df.to_parquet("data.parquet", index=False)
df = pd.read_parquet("data.parquet", columns=["id", "value"])
```
 
## NumPy Vectorization Tips
 
```python
# Replace loops with ufuncs
result = np.vectorize(my_func)(arr)       # last resort — still pure Python
 
# Prefer built-in ufuncs
result = np.maximum(arr, 0)               # ReLU
result = np.clip(arr, 0, 1)              # clamp
result = np.log1p(np.abs(arr))           # safe log
```
 
