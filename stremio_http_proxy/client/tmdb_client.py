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

    async def get_meta_by_imdb_id(self, imdb_id: str, media_type: str, season: int | None = None) -> dict:
        if not self.is_available():
            return {}

        tmdb_type = "tv" if media_type == "series" else "movie"
        url = urljoin(self.BASE_URL + "/", f"find/{imdb_id}")
        params = {"api_key": self.api_key, "external_source": "imdb_id", "language": "it-IT"}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return {}
            data = resp.json()
            results = data.get(f"{tmdb_type}_results", [])
            if not results:
                return {}
            tmdb_id = results[0]["id"]

            detail_url = urljoin(self.BASE_URL + "/", f"{tmdb_type}/{tmdb_id}")
            detail_params = {"api_key": self.api_key, "language": "it-IT"}
            detail_resp = await client.get(detail_url, params=detail_params)
            if detail_resp.status_code != 200:
                return {}
            detail = detail_resp.json()

            meta = {
                "name": detail.get("title") or detail.get("name"),
                "poster": f"https://image.tmdb.org/t/p/w500{detail['poster_path']}" if detail.get("poster_path") else None,
                "background": f"https://image.tmdb.org/t/p/w1280{detail['backdrop_path']}" if detail.get("backdrop_path") else None,
                "videos": [],
            }

            if media_type == "series":
                for s in detail.get("seasons", []):
                    season_number = s.get("season_number")
                    if season_number is not None and season_number > 0:
                        meta["videos"].append({"season": season_number})

                if season is not None:
                    season_url = urljoin(self.BASE_URL + "/", f"tv/{tmdb_id}/season/{season}")
                    season_resp = await client.get(season_url, params=detail_params)
                    if season_resp.status_code == 200:
                        season_data = season_resp.json()
                        for ep in season_data.get("episodes", []):
                            meta["videos"].append({
                                "season": season,
                                "episode": ep.get("episode_number"),
                                "title": ep.get("name"),
                            })

            return meta
