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
        self.retried = []
        self.dead = []
        self.claimed_job = None

    def is_ready(self, cache_key: str) -> bool:
        return self.ready

    def prune(self) -> None:
        return None

    def cleanup_partial(self, cache_key: str) -> None:
        return None

    def mark_failed(self, cache_key: str, error: str, attempt: int):
        self.failed.append((cache_key, error, attempt))

    async def claim_next_download(self, worker_id: str):
        job, self.claimed_job = self.claimed_job, None
        return job

    async def acknowledge_download(self, job):
        return None

    async def retry_download(self, job, delay_seconds: int, error: str):
        self.retried.append((job.job_id, delay_seconds, error))

    async def move_to_dead_letter(self, job, error: str):
        self.dead.append((job.job_id, error))

    def touch_processing_lease(self, cache_key: str, worker_id: str, lease_seconds: int = 180):
        return None


def test_download_worker_retries_failed_job(tmp_path, monkeypatch):
    job = DownloadJob(
        job_id="job-1",
        cache_key="abc:1",
        link="magnet:?xt=urn:btih:abc",
        enqueued_at=0,
        available_at=0,
    )
    cache_manager = FakeCacheManager()
    cache_manager.claimed_job = job
    service = DownloadWorkerService(
        FakeTorrServerClient(),
        cache_manager,
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

    assert cache_manager.retried == [("job-1", 30, "download progress stayed below threshold")]
    assert cache_manager.failed == [("abc:1", "download progress stayed below threshold", 1)]
