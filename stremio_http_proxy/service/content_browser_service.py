import asyncio
from injector import inject

from stremio_http_proxy.client.tmdb_client import TMDBClient
from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.manager.media_asset_manager import MediaAssetManager
from stremio_http_proxy.repository.media_item_repository import MediaItemRepository
from stremio_http_proxy.repository.media_repository import MediaRepository
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class ContentBrowserService:
    @inject
    def __init__(
        self,
        upstream_client: UpstreamClient,
        tmdb_client: TMDBClient,
        stream_rewrite_service: StreamRewriteService,
        media_repository: MediaRepository | None = None,
        media_item_repository: MediaItemRepository | None = None,
        media_asset_manager: MediaAssetManager | None = None,
    ):
        self.upstream_client = upstream_client
        self.tmdb_client = tmdb_client
        self.stream_rewrite_service = stream_rewrite_service
        self.media_repository = media_repository
        self.media_item_repository = media_item_repository
        self.media_asset_manager = media_asset_manager

    async def search_content(self, query: str, content_type: str, page: int = 1) -> dict:
        if not self.tmdb_client.is_available():
            return {"results": [], "page": 1, "total_pages": 1}
        if content_type == "movie":
            return await self.tmdb_client.search_movie(query, page)
        return await self.tmdb_client.search_tv(query, page)

    async def resolve_content(self, tmdb_id: int, content_type: str) -> str | None:
        tmdb_type = "tv" if content_type == "series" else content_type
        return await self.tmdb_client.get_imdb_id(tmdb_id, tmdb_type)

    async def import_media(self, tmdb_id: int, content_type: str) -> dict:
        if not self.media_repository or not self.media_item_repository:
            raise RuntimeError("Database repositories are not configured")

        details = await self.tmdb_client.get_full_details_by_tmdb_id(tmdb_id, content_type)
        if not details:
            raise ValueError(f"Could not fetch details for TMDB ID {tmdb_id}")

        existing = self.media_repository.get_by_tmdb_id(str(tmdb_id))
        imdb_id = details.get("imdb_id")
        if not existing and imdb_id:
            existing = self.media_repository.get_by_imdb_id(imdb_id)

        target_media_id = existing.id if existing else None

        poster_url = details.get("poster")
        backdrop_url = details.get("backdrop")
        local_poster = poster_url
        local_backdrop = backdrop_url

        if self.media_asset_manager:
            local_poster = await self.media_asset_manager.save_image_from_url(
                poster_url, "posters", f"tmdb_{tmdb_id}_poster"
            )
            local_backdrop = await self.media_asset_manager.save_image_from_url(
                backdrop_url, "backdrops", f"tmdb_{tmdb_id}_backdrop"
            )

        media = self.media_repository.upsert_media(
            media_type=content_type,
            title=details.get("title") or "Senza titolo",
            imdb_id=imdb_id,
            tmdb_id=str(tmdb_id),
            year=details.get("year"),
            poster=local_poster,
            backdrop=local_backdrop,
            overview=details.get("overview"),
            media_id=target_media_id,
        )

        episodes = details.get("episodes", [])
        if content_type == "movie":
            self.media_item_repository.upsert_media_item(
                media_id=media.id,
                season=None,
                episode=None,
                title=media.title,
                overview=media.overview,
                thumbnail=local_poster,
                release_date=details.get("year"),
            )
        else:
            sem = asyncio.Semaphore(5)

            async def process_episode(ep):
                thumb = ep.get("thumbnail")
                if self.media_asset_manager and thumb:
                    async with sem:
                        thumb = await self.media_asset_manager.save_image_from_url(
                            thumb, "episodes", f"media_{media.id}_s{ep['season']}_e{ep['episode']}"
                        )
                return {
                    "season": ep.get("season"),
                    "episode": ep.get("episode"),
                    "title": ep.get("title"),
                    "overview": ep.get("overview"),
                    "thumbnail": thumb,
                    "release_date": ep.get("release_date"),
                }

            processed_episodes = await asyncio.gather(*[process_episode(ep) for ep in episodes])
            for ep_data in processed_episodes:
                self.media_item_repository.upsert_media_item(
                    media_id=media.id,
                    season=ep_data["season"],
                    episode=ep_data["episode"],
                    title=ep_data["title"],
                    overview=ep_data["overview"],
                    thumbnail=ep_data["thumbnail"],
                    release_date=ep_data["release_date"],
                )

        return {"media_id": media.id, "status": "updated" if target_media_id else "imported"}

    async def refresh_media(self, media_id: int) -> dict:
        if not self.media_repository:
            raise RuntimeError("Database repository not configured")

        media = self.media_repository.get_media(media_id)
        if not media:
            raise ValueError(f"Media with ID {media_id} not found")

        tmdb_id = media.tmdb_id
        if not tmdb_id and media.imdb_id:
            tmdb_id = await self.tmdb_client.get_tmdb_id_by_imdb_id(media.imdb_id, media.type)

        if not tmdb_id:
            raise ValueError(f"Impossibile risalire all'ID TMDB per il media {media.title}")

        result = await self.import_media(int(tmdb_id), media.type)
        return {"success": True, "media_id": result["media_id"], "status": result.get("status")}

    async def browse_content(self, content_type: str, content_id: str, season: int | None = None, episode: int | None = None) -> dict:
        stream_id = content_id
        if content_type == "series" and season is not None and episode is not None:
            stream_id = f"{content_id}:{season}:{episode}"

        stream_path = f"/stream/{content_type}/{stream_id}.json"

        meta_payload = await self.tmdb_client.get_meta_by_imdb_id(content_id, content_type, season)

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
                "description": s.get("description"),
                "infohash": infohash,
                "url": s.get("url"),
                "meta": s.get("_meta"),
            })

        return {
            "meta": meta_payload.get("meta", meta_payload),
            "streams": streams,
        }
