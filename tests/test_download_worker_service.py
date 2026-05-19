import asyncio

from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.model.download_job import DownloadJob
from stremio_http_proxy.service.download_worker_service import DownloadWorkerService


class FakeTorrServerClient:
    async def add_torrent(self, link: str, title=None, poster=None, category=None):
        return {}

    def build_play_url(self, link: str, title=None, poster=None, category=None, index=None) -> str:
        return "http://localhost:8090/stream?play=true"


class FakeCacheManager:
    def __init__(self):
        self.ready = False
        self.failed = []

    def is_ready(self, cache_key: str) -> bool:
        return self.ready

    def prune(self) -> None:
        return None

    def cleanup_partial(self, cache_key: str) -> None:
        return None

    def mark_failed(self, cache_key: str, error: str, attempt: int):
        self.failed.append((cache_key, error, attempt))


class FakeRedisManager:
    def __init__(self, job):
        self.job = job
        self.acknowledged = []
        self.retried = []
        self.dead = []

    async def claim_next_job(self):
        job, self.job = self.job, None
        return job

    async def acknowledge(self, job):
        self.acknowledged.append(job.job_id)

    async def retry(self, job, delay_seconds: int, error: str):
        self.retried.append((job.job_id, delay_seconds, error))

    async def move_to_dead_letter(self, job, error: str):
        self.dead.append((job.job_id, error))


def test_download_worker_retries_failed_job(tmp_path, monkeypatch):
    job = DownloadJob(
        job_id="job-1",
        cache_key="abc:1",
        link="magnet:?xt=urn:btih:abc",
        enqueued_at=0,
        available_at=0,
    )
    cache_manager = FakeCacheManager()
    redis_manager = FakeRedisManager(job)
    service = DownloadWorkerService(
        FakeTorrServerClient(),
        cache_manager,
        redis_manager,
        LoggerFactory(str(tmp_path)),
        1,
        10,
        30,
        1024,
        120,
        60,
        10,
    )

    async def fake_download(_job):
        raise TimeoutError("download progress stayed below threshold")

    monkeypatch.setattr(service, "_download", fake_download)

    asyncio.run(service.process_next_job())

    assert redis_manager.retried == [("job-1", 30, "download progress stayed below threshold")]
    assert cache_manager.failed == [("abc:1", "download progress stayed below threshold", 1)]
