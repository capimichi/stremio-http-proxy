import asyncio
from stremio_http_proxy.client.upstream_client import UpstreamClient

async def main():
    client = UpstreamClient("https://torrentio.strem.fun/", 10)
    res = await client.get_json("/stream/series/tt0903747:1:1.json")
    print(len(res.get("streams", [])))

asyncio.run(main())
