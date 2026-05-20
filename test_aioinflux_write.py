from aioinflux import InfluxDBClient
import asyncio

async def test():
    # Will fail connection but we want to see if `headers={"Authorization": ...}` works
    try:
        client = InfluxDBClient(host='127.0.0.1', headers={"Authorization": "Bearer token"})
        print("Works!")
    except Exception as e:
        print(f"Failed: {e}")

asyncio.run(test())
