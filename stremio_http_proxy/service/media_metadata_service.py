import asyncio
import re
from typing import Any
from injector import inject

from stremio_http_proxy.client.tmdb_client import TMDBClient
from stremio_http_proxy.entity.media import Media
from stremio_http_proxy.entity.media_item import MediaItem
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.repository.media_repository import MediaRepository


class MediaMetadataService:
    @inject
    def __init__(
        self,
        media_repository: MediaRepository,
        tmdb_client: TMDBClient,
        logger_factory: LoggerFactory,
        task_service: Any = None,
    ):
        self.media_repository = media_repository
        self.tmdb_client = tmdb_client
        self.task_service = task_service
        self.logger = logger_factory.get_logger("stremio_http_proxy.media_metadata", "media_metadata.log")

    def parse_content_id(
        self, content_id: str | None, content_type: str | None = None
    ) -> tuple[str, str, int | None, int | None, str]:
        """
        Parses content_id into:
        (media_id, item_id, season, episode, media_type)
        """
        if not content_id:
            return "", "", None, None, content_type or "movie"

        if ":" in content_id:
            parts = content_id.split(":")
            media_id = parts[0]
            season = None
            episode = None
            if len(parts) >= 3:
                try:
                    season = int(parts[1])
                    episode = int(parts[2])
                except (ValueError, TypeError):
                    pass
            elif len(parts) == 2:
                try:
                    episode = int(parts[1])
                except (ValueError, TypeError):
                    pass

            if season is not None and episode is not None:
                item_id = f"{media_id}:{season}:{episode}"
            else:
                item_id = content_id
            determined_type = content_type or "series"
            return media_id, item_id, season, episode, determined_type

        # Single ID (e.g. movie tt0088763)
        determined_type = content_type or "movie"
        return content_id, content_id, None, None, determined_type

    def clean_raw_title(self, raw_title: str | None) -> str:
        """
        Removes typical torrent release tags (1080p, HDTV, LOL, Ita, etc.) to get a cleaner fallback.
        """
        if not raw_title:
            return "Senza titolo"
        title = raw_title.replace(".", " ").replace("_", " ")
        # Cut off at common release patterns
        title = re.split(r"(?i)\b(1080p|720p|2160p|4k|hdtv|web-dl|bluray|x264|x265|hevc|ita|eng|sub|dvdrip)\b", title)[0]
        title = title.strip(" -_")
        return title or raw_title

    def ensure_media_and_item(
        self,
        content_id: str,
        content_type: str | None = None,
        fallback_title: str | None = None,
        fallback_poster: str | None = None,
        schedule_enrichment: bool = True,
    ) -> tuple[Media, MediaItem]:
        media_id, item_id, season, episode, media_type = self.parse_content_id(content_id, content_type)

        # Check existing media
        existing_media = self.media_repository.get_media(media_id)
        if existing_media is None:
            clean_fallback = self.clean_raw_title(fallback_title)
            media = self.media_repository.upsert_media(
                media_id=media_id,
                media_type=media_type,
                title=clean_fallback,
                poster=fallback_poster,
            )
            should_enrich = True
        else:
            media = existing_media
            should_enrich = not existing_media.poster or existing_media.title == "Senza titolo"

        # Ensure MediaItem exists
        item = self.media_repository.upsert_media_item(
            item_id=item_id,
            media_id=media_id,
            season=season,
            episode=episode,
        )

        # If enrichment needed, schedule background task or async task
        if should_enrich and schedule_enrichment and self.tmdb_client.is_available():
            self._schedule_enrichment(media_id, media_type, season)

        return media, item

    def _schedule_enrichment(self, media_id: str, media_type: str, season: int | None = None) -> None:
        if self.task_service and hasattr(self.task_service, "enqueue_task"):
            self.task_service.enqueue_task(
                name="enrich_media_metadata",
                arguments={"media_id": media_id, "media_type": media_type, "season": season},
                delay_seconds=0,
                deduplicate=True,
            )
        else:
            # Fallback fire-and-forget in current loop if available
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.enrich_from_tmdb(media_id, media_type, season))
            except RuntimeError:
                pass

    async def enrich_from_tmdb(self, media_id: str, media_type: str, season: int | None = None) -> bool:
        if not self.tmdb_client.is_available():
            return False

        try:
            meta = await self.tmdb_client.get_meta_by_imdb_id(media_id, media_type, season=season)
            if not meta:
                return False

            name = meta.get("name")
            poster = meta.get("poster")
            backdrop = meta.get("background")
            year = meta.get("year")
            overview = meta.get("overview")

            if name or poster:
                self.media_repository.upsert_media(
                    media_id=media_id,
                    media_type=media_type,
                    title=name or "Senza titolo",
                    year=year,
                    poster=poster,
                    backdrop=backdrop,
                    overview=overview,
                )

            # Also update episode names if provided in videos
            for vid in meta.get("videos", []):
                s = vid.get("season")
                ep = vid.get("episode")
                ep_title = vid.get("title")
                if s is not None and ep is not None and ep_title:
                    item_id = f"{media_id}:{s}:{ep}"
                    self.media_repository.upsert_media_item(
                        item_id=item_id,
                        media_id=media_id,
                        season=s,
                        episode=ep,
                        title=ep_title,
                    )

            self.logger.info("Successfully enriched metadata for %s (%s)", media_id, name)
            return True
        except Exception as e:
            self.logger.warning("Failed to enrich metadata for %s from TMDB: %s", media_id, e)
            return False
