import time

from injector import inject
from redis.asyncio import Redis

from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.model.download_job import DownloadJob


class RedisManager:
    @inject
    def __init__(self, redis_url: str, logger_factory: LoggerFactory, client: Redis | None = None):
        self.redis = client or Redis.from_url(redis_url, decode_responses=True)
        self.logger = logger_factory.get_logger("stremio_http_proxy.redis", "redis.log")

    async def enqueue(self, job: DownloadJob) -> bool:
        lock_key = self._lock_key(job.cache_key)
        acquired = await self.redis.set(lock_key, job.job_id, ex=86400, nx=True)
        if not acquired:
            return False

        await self.redis.set(self._job_key(job.job_id), job.model_dump_json())
        await self.redis.zadd("download_queue:ready", {job.job_id: self._score(job.available_at, job.priority)})
        self.logger.info("Enqueued job %s for %s", job.job_id, job.cache_key)
        return True

    async def claim_next_job(self, lease_seconds: int = 120) -> DownloadJob | None:
        await self.requeue_expired_processing()
        now = time.time()
        job_ids = await self.redis.zrangebyscore("download_queue:ready", min="-inf", max=now, start=0, num=1)
        if not job_ids:
            return None

        job_id = job_ids[0]
        removed = await self.redis.zrem("download_queue:ready", job_id)
        if not removed:
            return None

        await self.redis.zadd("download_queue:processing", {job_id: now + lease_seconds})
        payload = await self.redis.get(self._job_key(job_id))
        if payload is None:
            await self.redis.zrem("download_queue:processing", job_id)
            return None
        return DownloadJob.model_validate_json(payload)

    async def acknowledge(self, job: DownloadJob) -> None:
        await self.redis.zrem("download_queue:processing", job.job_id)
        await self.redis.delete(self._job_key(job.job_id), self._lock_key(job.cache_key))
        self.logger.info("Acknowledged job %s for %s", job.job_id, job.cache_key)

    async def retry(self, job: DownloadJob, delay_seconds: int, error: str) -> None:
        updated = job.model_copy(
            update={
                "attempt": job.attempt + 1,
                "available_at": time.time() + delay_seconds,
                "last_error": error,
            }
        )
        await self.redis.zrem("download_queue:processing", job.job_id)
        await self.redis.set(self._job_key(job.job_id), updated.model_dump_json())
        await self.redis.zadd(
            "download_queue:ready",
            {updated.job_id: self._score(updated.available_at, updated.priority)},
        )
        self.logger.warning("Retrying job %s in %ss: %s", job.job_id, delay_seconds, error)

    async def move_to_dead_letter(self, job: DownloadJob, error: str) -> None:
        updated = job.model_copy(update={"attempt": job.attempt + 1, "last_error": error})
        await self.redis.zrem("download_queue:processing", job.job_id)
        await self.redis.set(self._job_key(job.job_id), updated.model_dump_json())
        await self.redis.zadd("download_queue:dead", {updated.job_id: time.time()})
        await self.redis.delete(self._lock_key(job.cache_key))
        self.logger.error("Moved job %s to dead-letter: %s", job.job_id, error)

    async def requeue_expired_processing(self) -> None:
        expired_job_ids = await self.redis.zrangebyscore("download_queue:processing", min="-inf", max=time.time())
        for job_id in expired_job_ids:
            payload = await self.redis.get(self._job_key(job_id))
            if payload is None:
                await self.redis.zrem("download_queue:processing", job_id)
                continue
            job = DownloadJob.model_validate_json(payload)
            await self.redis.zrem("download_queue:processing", job_id)
            await self.redis.zadd("download_queue:ready", {job_id: self._score(time.time(), job.priority)})
            self.logger.warning("Requeued expired processing job %s", job_id)

    async def close(self) -> None:
        await self.redis.aclose()

    def _score(self, available_at: float, priority: int) -> float:
        return available_at - (priority / 1000)

    def _job_key(self, job_id: str) -> str:
        return f"download_job:{job_id}"

    def _lock_key(self, cache_key: str) -> str:
        return f"download_lock:{cache_key}"
