import asyncio
from stremio_http_proxy.client.tmdb_client import TMDBClient

async def main():
    client = TMDBClient(api_key="546644f12eb60ad4ddffba8d23428989") # I will use a dummy one or maybe it fails with 401
    print(await client.get_meta_by_imdb_id("tt0944947", "series"))

asyncio.run(main())
