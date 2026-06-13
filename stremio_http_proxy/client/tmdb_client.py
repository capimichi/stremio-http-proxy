from urllib.parse import urljoin

import httpx
from injector import inject


class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"

    @inject
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search_movie(self, query: str, page: int = 1) -> dict:
        if not self.is_available():
            return {"results": [], "page": 1, "total_pages": 1}
        return await self._search("movie", query, page)

    async def search_tv(self, query: str, page: int = 1) -> dict:
        if not self.is_available():
            return {"results": [], "page": 1, "total_pages": 1}
        return await self._search("tv", query, page)

    async def _search(self, media_type: str, query: str, page: int) -> dict:
        url = urljoin(self.BASE_URL + "/", f"search/{media_type}")
        params = {"api_key": self.api_key, "query": query, "language": "it-IT", "page": page}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title") or item.get("name"),
                "year": (item.get("release_date") or item.get("first_air_date") or "")[:4],
                "poster": f"https://image.tmdb.org/t/p/w185{item['poster_path']}" if item.get("poster_path") else None,
                "tmdb_id": item["id"],
            })
        return {
            "results": results,
            "page": data.get("page", 1),
            "total_pages": data.get("total_pages", 1),
        }

    async def get_imdb_id(self, tmdb_id: int, media_type: str) -> str | None:
        url = urljoin(self.BASE_URL + "/", f"{media_type}/{tmdb_id}/external_ids")
        params = {"api_key": self.api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return None
            return response.json().get("imdb_id")
