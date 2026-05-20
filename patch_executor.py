import re

with open('src/main.py', 'r') as f:
    code = f.read()

code = code.replace("import concurrent.futures", "import asyncio\nimport aiohttp\nfrom aioinflux import InfluxDBClient as AsyncInfluxDBClient")

code = code.replace("def main():", "async def async_main():")
code = code.replace("if __name__ == \"__main__\":\n    main()", "if __name__ == \"__main__\":\n    asyncio.run(async_main())")

# Inject async client creations after `target_client = ...`
client_str = "target_client = InfluxDBClient(host=target_host, port=target_port, database=target_database, ssl=True, verify_ssl=True, headers={\"Authorization\": f\"Bearer {target_token}\"})"

async_client_str = client_str + """

    # Create async clients
    async_source_client = AsyncInfluxDBClient(host=source_host, port=source_port, db=source_database, ssl=True, headers={"Authorization": f"Bearer {source_token}"})
    async_target_client = AsyncInfluxDBClient(host=target_host, port=target_port, db=target_database, ssl=True, headers={"Authorization": f"Bearer {target_token}"})
"""
code = code.replace(client_str, async_client_str)

# Replace `def process_chunk` with `async def process_chunk`
code = code.replace("def process_chunk(t1_str, t2_str):", "async def process_chunk(t1_str, t2_str):")

# Replace query reading part
query_read_search = """                # 1. Read data
                result = source_client.query(query_read, method='GET')
                points = list(result.get_points())"""

query_read_replace = """                # 1. Read data
                result = await async_source_client.query(query_read)
                points = []
                if 'results' in result and result['results']:
                    for r in result['results']:
                        if 'series' in r:
                            for s in r['series']:
                                cols = s.get('columns', [])
                                vals = s.get('values', [])
                                for v in vals:
                                    points.append(dict(zip(cols, v)))"""
code = code.replace(query_read_search, query_read_replace)

# Replace writing part
write_search = "target_client.write_points(new_points_batch, database=target_database, batch_size=5000)"
write_replace = "await async_target_client.write(new_points_batch)"
code = code.replace(write_search, write_replace)

with open('src/main_async_part1.py', 'w') as f:
    f.write(code)
