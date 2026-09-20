import hashlib
import time

from injector import inject

from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.model.download_job import DownloadJob
from stremio_http_proxy.service.media_metadata_service import MediaMetadataService


class DownloadQueueService:
    @inject
    def __init__(
        self,
        cache_manager: CacheManager,
        max_attempts: int,
        cache_enabled: bool = True,
        media_metadata_service: MediaMetadataService | None = None,
    ):
        self.cache_manager = cache_manager
        self.max_attempts = max_attempts
        self.cache_enabled = cache_enabled
        self.media_metadata_service = media_metadata_service

    async def enqueue_download(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        index: int | None = None,
        priority: int = 100,
        trigger: str = "playback",
        content_type: str | None = None,
        content_id: str | None = None,
    ) -> bool:
        if not self.cache_enabled:
            return False
        cache_key = self.cache_manager.build_cache_key(link, index)
        if cache_key is None or self.cache_manager.is_ready(cache_key):
            return False

        media_item_id = None
        if content_id and self.media_metadata_service:
            try:
                _, media_item = self.media_metadata_service.ensure_media_and_item(
                    content_id=content_id,
                    content_type=content_type,
                    fallback_title=title,
                    fallback_poster=poster,
                )
                media_item_id = media_item.id
            except Exception:
                media_item_id = None

        now = time.time()
        job_id = hashlib.sha1(f"{cache_key}:{trigger}".encode()).hexdigest()
        job = DownloadJob(
            job_id=job_id,
            cache_key=cache_key,
            link=link,
            title=title,
            poster=poster,
            category=category,
            index=index,
            priority=priority,
            max_attempts=self.max_attempts,
            trigger=trigger,
            content_type=content_type,
            content_id=content_id,
            media_item_id=media_item_id,
            enqueued_at=now,
            available_at=now,
        )
        return await self.cache_manager.enqueue_download(job)
