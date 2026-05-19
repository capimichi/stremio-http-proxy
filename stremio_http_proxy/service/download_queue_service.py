import hashlib
import time

from injector import inject

from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.manager.redis_manager import RedisManager
from stremio_http_proxy.model.download_job import DownloadJob


class DownloadQueueService:
    @inject
    def __init__(self, cache_manager: CacheManager, redis_manager: RedisManager, max_attempts: int):
        self.cache_manager = cache_manager
        self.redis_manager = redis_manager
        self.max_attempts = max_attempts

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
        cache_key = self.cache_manager.build_cache_key(link, index)
        if cache_key is None or self.cache_manager.is_ready(cache_key):
            return False

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
            enqueued_at=now,
            available_at=now,
        )
        return await self.redis_manager.enqueue(job)
