from injector import inject

from stremio_http_proxy.client.tmdb_client import TMDBClient
from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class ContentBrowserService:
    @inject
    def __init__(
        self,
        upstream_client: UpstreamClient,
        tmdb_client: TMDBClient,
        stream_rewrite_service: StreamRewriteService,
    ):
        self.upstream_client = upstream_client
        self.tmdb_client = tmdb_client
        self.stream_rewrite_service = stream_rewrite_service

    async def search_content(self, query: str, content_type: str, page: int = 1) -> dict:
        if not self.tmdb_client.is_available():
            return {"results": [], "page": 1, "total_pages": 1}
        if content_type == "movie":
            return await self.tmdb_client.search_movie(query, page)
        return await self.tmdb_client.search_tv(query, page)

    async def resolve_content(self, tmdb_id: int, content_type: str) -> str | None:
        tmdb_type = "tv" if content_type == "series" else content_type
        return await self.tmdb_client.get_imdb_id(tmdb_id, tmdb_type)

    async def browse_content(self, content_type: str, content_id: str) -> dict:
        stream_path = f"/stream/{content_type}/{content_id}.json"
        meta_path = f"/meta/{content_type}/{content_id}.json"

        meta_payload = await self.upstream_client.get_json(meta_path)

        stream_payload = await self.stream_rewrite_service.rewrite(
            await self.upstream_client.get_json(stream_path),
            category="movie" if content_type == "movie" else "tv",
            content_type=content_type,
            content_id=content_id,
        )

        streams = []
        for s in stream_payload.get("streams", []):
            if not isinstance(s, dict):
                continue
            infohash = self.stream_rewrite_service._extract_infohash_from_stream(s)
            streams.append({
                "name": s.get("name"),
                "title": s.get("title"),
                "infohash": infohash,
                "url": s.get("url"),
                "meta": s.get("_meta"),
            })

        return {
            "meta": meta_payload.get("meta", meta_payload),
            "streams": streams,
        }
