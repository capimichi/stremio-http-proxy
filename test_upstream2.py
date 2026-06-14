import asyncio
import httpx
from urllib.parse import urljoin

async def main():
    url = urljoin("https://torrentio.strem.fun/", "stream/series/tt0903747:1:1.json")
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        res = await client.get(url)
        print(res.status_code)
        if res.status_code == 200:
            print(len(res.json().get("streams", [])))

asyncio.run(main())
