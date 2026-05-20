import re

with open('src/main_async_part1.py', 'r') as f:
    code = f.read()

# Replace thread pool executor logic with asyncio.gather
executor_search = """    try:
        # We process in batches equal to max_concurrent_queries.
        # This keeps state saving robust—we only advance the state when a full batch is safely completed.
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent_queries) as executor:
            while current_time < end_time:"""

executor_replace = """    try:
        # We process in batches equal to max_concurrent_queries.
        # This keeps state saving robust—we only advance the state when a full batch is safely completed.
        async with async_source_client, async_target_client:
            while current_time < end_time:"""
code = code.replace(executor_search, executor_replace)

submit_search = "future = executor.submit(process_chunk, t1, t2)"
submit_replace = "task = asyncio.create_task(process_chunk(t1, t2))"
code = code.replace(submit_search, submit_replace)

batch_tasks_search = """                    for future in concurrent.futures.as_completed(batch_tasks):
                        points_in_chunk = future.result()"""
batch_tasks_replace = """                    results = await asyncio.gather(*batch_tasks)
                    for points_in_chunk in results:"""
code = code.replace(batch_tasks_search, batch_tasks_replace)


with open('src/main_async.py', 'w') as f:
    f.write(code)
