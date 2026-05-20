import asyncio
from aioinflux import InfluxDBClient

async def main():
    async with InfluxDBClient(db='testdb') as client:
        # Just want to see if the syntax works
        print("Aioinflux client created")

asyncio.run(main())
