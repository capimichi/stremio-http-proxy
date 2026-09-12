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
    def __init__(self, tmp_dir=None):
        self.ready = False
        self.failed = []
        self.retried = []
        self.dead = []
        self.acknowledged = []
        self.ready_keys = []
        self.claimed_job = None
        self.tmp_dir = tmp_dir

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
        self.acknowledged.append(job.job_id)
        return None

    async def retry_download(self, job, delay_seconds: int, error: str):
        self.retried.append((job.job_id, delay_seconds, error))

    async def move_to_dead_letter(self, job, error: str):
        self.dead.append((job.job_id, error))

    def touch_processing_lease(self, cache_key: str, worker_id: str, lease_seconds: int = 180):
        return None

    def mark_downloading(self, cache_key: str, attempt: int):
        return None

    def mark_progress(self, cache_key: str, downloaded_bytes: int, expected_bytes, progress_percent, speed):
        return None

    def prepare_download_path(self, cache_key: str):
        p = self.tmp_dir / f"{cache_key.replace(':', '_')}.part"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def finalize_download(self, cache_key: str):
        p = self.prepare_download_path(cache_key)
        return p.stat().st_size if p.exists() else 0

    def mark_ready(self, cache_key: str, size_bytes: int):
        self.ready_keys.append((cache_key, size_bytes))

    def get_min_cache_size(self) -> int:
        return 10


def test_download_worker_retries_failed_job(tmp_path, monkeypatch):
    job = DownloadJob(
        job_id="job-1",
        cache_key="abc:1",
        link="magnet:?xt=urn:btih:abc",
        enqueued_at=0,
        available_at=0,
    )
    cache_manager = FakeCacheManager(tmp_path)
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


def test_download_worker_downloads_direct_http_stream(tmp_path, respx_mock):
    url = "https://example.com/video.mp4"
    payload = b"X" * 1024
    respx_mock.get(url).respond(200, content=payload, headers={"content-length": str(len(payload))})

    job = DownloadJob(
        job_id="job-http-1",
        cache_key="hash123:0",
        link=url,
        enqueued_at=0,
        available_at=0,
    )
    cache_manager = FakeCacheManager(tmp_path)
    cache_manager.claimed_job = job
    torrserver_client = FakeTorrServerClient()

    service = DownloadWorkerService(
        torrserver_client,
        cache_manager,
        LoggerFactory(str(tmp_path)),
        poll_seconds=1,
        connect_timeout_seconds=10,
        no_progress_timeout_seconds=30,
        min_progress_bytes=10,
        min_progress_window_seconds=120,
        max_total_seconds=60,
        progress_log_interval_seconds=10,
    )

    processed = asyncio.run(service.process_next_job())

    assert processed is True
    assert cache_manager.acknowledged == ["job-http-1"]
    assert len(cache_manager.ready_keys) == 1
    assert cache_manager.ready_keys[0] == ("hash123:0", 1024)


def test_download_worker_downloads_hls_stream(tmp_path, monkeypatch):
    hls_url = "https://mediaflow.example.com/_token_/proxy/hls/manifest.m3u8"
    job = DownloadJob(
        job_id="job-hls-1",
        cache_key="hash456:0",
        link=hls_url,
        enqueued_at=0,
        available_at=0,
    )
    cache_manager = FakeCacheManager(tmp_path)
    cache_manager.claimed_job = job

    # Mock subprocess for ffmpeg: creates dummy downloaded file
    class FakeProc:
        def __init__(self, target_file):
            self.returncode = 0
            self.target_file = target_file

        async def wait(self):
            with open(self.target_file, "wb") as f:
                f.write(b"HLS_VIDEO_DATA" * 100)
            return 0

        async def communicate(self):
            return b"", b""

        def kill(self):
            pass

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        output_file = cmd[-1]
        return FakeProc(output_file)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    service = DownloadWorkerService(
        FakeTorrServerClient(),
        cache_manager,
        LoggerFactory(str(tmp_path)),
        poll_seconds=1,
        connect_timeout_seconds=10,
        no_progress_timeout_seconds=30,
        min_progress_bytes=10,
        min_progress_window_seconds=120,
        max_total_seconds=60,
        progress_log_interval_seconds=1,
    )

    processed = asyncio.run(service.process_next_job())

    assert processed is True
    assert cache_manager.acknowledged == ["job-hls-1"]
    assert len(cache_manager.ready_keys) == 1
    assert cache_manager.ready_keys[0][0] == "hash456:0"
    assert cache_manager.ready_keys[0][1] == 1400
