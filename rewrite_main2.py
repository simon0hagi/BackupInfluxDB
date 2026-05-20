import re

with open('src/main_async_draft.py', 'r') as f:
    code = f.read()

# Replace test source connection using sync client to just keep sync client for initial stuff?
# Actually, the user asked to use aioinflux for reading/writing.
# We can just keep the sync client for count/ping, and instantiate async clients for the loop.

async_clients = """
    # Async Clients
    async_source_client = AsyncInfluxDBClient(host=source_host, port=source_port, db=source_database, ssl=True, headers={"Authorization": f"Bearer {source_token}"})
    async_target_client = AsyncInfluxDBClient(host=target_host, port=target_port, db=target_database, ssl=True, headers={"Authorization": f"Bearer {target_token}"})
"""

code = code.replace("    # Initialize InfluxDB Client", async_clients + "\n    # Initialize InfluxDB Client")

# Now change process_chunk to async
code = code.replace("def process_chunk(t1_str, t2_str):", "async def process_chunk(t1_str, t2_str):")

# Change query and write_points to use async clients
# The query response in aioinflux differs slightly from influxdb.
# InfluxDB python: `result.get_points()`
# Aioinflux: `result['results'][0].get('series', [])` then parse, OR use output='dataframe'.
# Since we already do `points_df = pd.DataFrame(points)`, we can just use `output='dataframe'`!

code = code.replace("result = source_client.query(query_read, method='GET')", "result = await async_source_client.query(query_read, output='dataframe')")

# The dataframe output returns either a single DataFrame or a dict of DataFrames.
# We'll need to manually modify the `process_chunk` function body.
