from injector import inject

from stremio_http_proxy.client.tmdb_client import TMDBClient
from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.entity.whitelist_entry import WhitelistEntry
from stremio_http_proxy.repository.whitelist_repository import WhitelistRepository
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class WhitelistService:
    @inject
    def __init__(
        self,
        upstream_client: UpstreamClient,
        tmdb_client: TMDBClient,
        whitelist_repository: WhitelistRepository,
        stream_rewrite_service: StreamRewriteService,
    ):
        self.upstream_client = upstream_client
        self.tmdb_client = tmdb_client
        self.whitelist_repository = whitelist_repository
        self.stream_rewrite_service = stream_rewrite_service

    async def search_content(self, query: str, content_type: str) -> list[dict]:
        if not self.tmdb_client.is_available():
            return []
        if content_type == "movie":
            return await self.tmdb_client.search_movie(query)
        return await self.tmdb_client.search_tv(query)

    async def browse_content(
        self,
        content_type: str,
        content_id: str,
        season: int | None = None,
        episode: int | None = None,
    ) -> dict:
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

        rules = self.whitelist_repository.list_entries(imdb_id=content_id)

        return {
            "meta": meta_payload.get("meta", meta_payload),
            "streams": streams,
            "whitelist": [
                {
                    "id": r.id,
                    "infohash": r.infohash,
                    "season": r.season,
                    "episode": r.episode,
                }
                for r in rules
            ],
        }

    def add_to_whitelist(
        self,
        infohash: str,
        imdb_id: str,
        season: int | None = None,
        episode: int | None = None,
    ) -> WhitelistEntry:
        return self.whitelist_repository.add_entry(
            infohash=infohash,
            imdb_id=imdb_id,
            season=season,
            episode=episode,
        )

    def remove_from_whitelist(self, entry_id: int) -> bool:
        return self.whitelist_repository.remove_entry(entry_id)

    def list_whitelist(
        self,
        search: str | None = None,
        season: int | None = None,
        episode: int | None = None,
        infohash: str | None = None,
        imdb_id: str | None = None,
    ) -> list[dict]:
        entries = self.whitelist_repository.list_entries(
            search=search,
            season=season,
            episode=episode,
            infohash=infohash,
            imdb_id=imdb_id,
        )
        return [
            {
                "id": e.id,
                "infohash": e.infohash,
                "imdb_id": e.imdb_id,
                "season": e.season,
                "episode": e.episode,
                "created_at": e.created_at,
            }
            for e in entries
        ]
