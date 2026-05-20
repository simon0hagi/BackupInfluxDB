with open('src/main.py', 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if line.startswith("import concurrent.futures"):
        new_lines.append("import asyncio\nfrom aioinflux import InfluxDBClient as AsyncInfluxDBClient\nimport aiohttp\n")
    elif line.startswith("def main():"):
        new_lines.append("async def async_main():\n")
    elif "def process_chunk(t1_str, t2_str):" in line:
        new_lines.append("    async def process_chunk(t1_str, t2_str):\n")
    elif "source_client.query(query_read, method='GET')" in line:
        new_lines.append("                result = await async_source_client.query(query_read, method='GET')\n")
    elif "points = list(result.get_points())" in line:
        # Aioinflux standard output is raw JSON dictionary
        # The structure is: {'results': [{'series': [{'columns': [...], 'values': [...]}]}]}
        new_lines.append("""                points = []
                if 'results' in result and result['results']:
                    for r in result['results']:
                        if 'series' in r:
                            for s in r['series']:
                                cols = s.get('columns', [])
                                vals = s.get('values', [])
                                for v in vals:
                                    points.append(dict(zip(cols, v)))
""")
    elif "target_client.write_points(new_points_batch, database=target_database, batch_size=5000)" in line:
        new_lines.append("                    await async_target_client.write(new_points_batch)\n")
    elif "with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent_queries) as executor:" in line:
        # We need to replace the entire chunk logic loop with asyncio
        # Let's skip replacing here, we will just manually rewrite this section
        pass
    else:
        new_lines.append(line)
    i += 1
