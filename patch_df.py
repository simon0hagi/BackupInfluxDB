import re

with open('src/main.py', 'r') as f:
    code = f.read()

# We need to adapt the pandas code since we get `points` as a list of dicts:
# The `aioinflux` output we parse:
# result = await async_source_client.query(query_read)
# points = [] ... dict(zip(cols, v))
# The keys in `points` might be different than the sync `get_points()`. Wait, `get_points()` also returns dicts. So pd.DataFrame(points) works the exact same way.

# One small fix: we need to replace `method='GET'` which we already replaced. Let's make sure `async_source_client.query` doesn't pass unsupported kwargs if any are left.
code = code.replace("result = await async_source_client.query(query_read, method='GET')", "result = await async_source_client.query(query_read)")

# Also `import concurrent.futures` is gone.

with open('src/main.py', 'w') as f:
    f.write(code)
