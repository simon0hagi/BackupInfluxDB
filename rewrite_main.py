import re

with open('src/main.py', 'r') as f:
    code = f.read()

# Replace concurrent.futures with asyncio
code = code.replace("import concurrent.futures", "import asyncio\nimport aiohttp\nfrom aioinflux import InfluxDBClient as AsyncInfluxDBClient")

# Update main function to be async
code = re.sub(r'def main\(\):', 'async def async_main():', code)

# Update bottom block
bottom_block = """if __name__ == "__main__":
    main()"""

new_bottom_block = """if __name__ == "__main__":
    asyncio.run(async_main())"""
code = code.replace(bottom_block, new_bottom_block)

with open('src/main_async_draft.py', 'w') as f:
    f.write(code)
