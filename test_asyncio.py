import asyncio
import time

async def process_chunk(t1, t2):
    await asyncio.sleep(0.1)
    return 100

async def main():
    start = time.time()

    tasks = []
    for i in range(10):
        tasks.append(asyncio.create_task(process_chunk(i, i+1)))

    results = await asyncio.gather(*tasks)
    end = time.time()
    print(f"Total time: {end-start}")
    print(results)

asyncio.run(main())
