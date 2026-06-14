import asyncio
from stremio_http_proxy.client.tmdb_client import TMDBClient

async def main():
    client = TMDBClient(api_key="18ebcf8860631cc3fce94146a9ace342")
    meta = await client.get_meta_by_imdb_id("tt0944947", "series")
    print(f"Meta retrieved: {bool(meta)}")
    print(f"Poster: {meta.get('poster')}")
    print(f"Background: {meta.get('background')}")
    print(f"Videos count: {len(meta.get('videos', []))} items")
    if meta.get('videos'):
        print(f"First video: {meta['videos'][0]}")

asyncio.run(main())
