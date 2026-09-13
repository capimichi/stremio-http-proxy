import asyncio
from pathlib import Path

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


def test_download_worker_downloads_hls_chunks_cooperatively(tmp_path, monkeypatch):
    import respx
    from stremio_http_proxy.manager.hls_chunk_manager import HlsChunkManager

    hls_url = "https://mediaflow.example.com/manifest.m3u8"
    job = DownloadJob(
        job_id="job-hls-chunks-1",
        cache_key="hash789:0",
        link=hls_url,
        enqueued_at=0,
        available_at=0,
    )
    cache_manager = FakeCacheManager(tmp_path)
    cache_manager.claimed_job = job

    chunk_manager = HlsChunkManager(tmp_path / "cache", LoggerFactory(str(tmp_path)))

    # Pre-seed chunk 0 (simulating player already buffered chunk 0)
    chunks_dir = chunk_manager.get_chunks_dir("hash789:0")
    (chunks_dir / "00000.ts").write_bytes(b"CHUNK_0_PRE_CACHED")

    variant_url = "https://mediaflow.example.com/variant.m3u8"
    chunk1_url = "https://mediaflow.example.com/chunk1.ts"

    raw_master = f"""#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000
{variant_url}
"""
    raw_variant = f"""#EXTM3U
#EXTINF:4.000000,
https://mediaflow.example.com/chunk0.ts
#EXTINF:4.000000,
{chunk1_url}
"""

    with respx.mock:
        respx.get(hls_url).respond(status_code=200, text=raw_master)
        respx.get(variant_url).respond(status_code=200, text=raw_variant)
        # chunk 0 should NOT be requested because it's already pre-cached!
        respx.get("https://mediaflow.example.com/chunk0.ts").respond(status_code=500)
        # chunk 1 is downloaded by the worker
        respx.get(chunk1_url).respond(status_code=200, content=b"CHUNK_1_DOWNLOADED_DATA")

        class FakeProc:
            def __init__(self, target_file):
                self.returncode = 0
                self.target_file = target_file

            async def communicate(self):
                self.target_file.parent.mkdir(parents=True, exist_ok=True)
                self.target_file.write_bytes(b"MERGED_MP4_RESULT" * 10)
                return b"", b""

        async def fake_create_subprocess_exec(*cmd, **kwargs):
            output_file = Path(cmd[-1])
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
            hls_chunk_manager=chunk_manager,
        )

        processed = asyncio.run(service.process_next_job())

        assert processed is True
        assert (cache_manager.retried, cache_manager.dead) == ([], [])
        assert cache_manager.acknowledged == ["job-hls-chunks-1"]
        assert len(cache_manager.ready_keys) == 1
        assert cache_manager.ready_keys[0][0] == "hash789:0"
        assert chunk_manager.has_chunk("hash789:0", 1)


def test_download_worker_discards_job_on_permanent_403_error(tmp_path):
    import respx

    hls_url = "https://mediaflow.example.com/dead_manifest.m3u8"
    job = DownloadJob(
        job_id="job-dead-403",
        cache_key="dead403:0",
        link=hls_url,
        enqueued_at=0,
        available_at=0,
    )
    cache_manager = FakeCacheManager(tmp_path)
    cache_manager.claimed_job = job

    with respx.mock:
        respx.get(hls_url).respond(status_code=403, text="Access Denied")

        from stremio_http_proxy.manager.hls_chunk_manager import HlsChunkManager

        chunk_manager = HlsChunkManager(tmp_path / "cache", LoggerFactory(str(tmp_path)))
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
            hls_chunk_manager=chunk_manager,
        )

        processed = asyncio.run(service.process_next_job())
        assert processed is True
        # Must be moved to dead letter immediately without retry
        assert cache_manager.retried == []
        assert len(cache_manager.dead) == 1
        assert cache_manager.dead[0][0] == "job-dead-403"


def test_download_worker_triggers_prefetch_fallback_on_permanent_failure(tmp_path):
    from unittest.mock import AsyncMock
    import respx

    prefetch_service = AsyncMock()

    job = DownloadJob(
        job_id="job-prefetch-fail",
        cache_key="prefetchfail:0",
        link="https://example.com/dead.m3u8",
        enqueued_at=0,
        available_at=0,
        trigger="next_episode_prefetch",
        content_type="series",
        content_id="tt3749900:1:2",
        category="tv",
    )
    cache_manager = FakeCacheManager(tmp_path)
    cache_manager.claimed_job = job

    with respx.mock:
        respx.get("https://example.com/dead.m3u8").respond(status_code=403, text="Forbidden")

        service = DownloadWorkerService(
            FakeTorrServerClient(),
            cache_manager,
            LoggerFactory(str(tmp_path)),
            poll_seconds=1,
            connect_timeout_seconds=10,
            no_progress_timeout_seconds=30,
            min_progress_bytes=100,
            min_progress_window_seconds=120,
            max_total_seconds=60,
            progress_log_interval_seconds=1,
            prefetch_min_progress_bytes=10,
            next_episode_prefetch_service=prefetch_service,
        )

        processed = asyncio.run(service.process_next_job())
        assert processed is True
        assert len(cache_manager.dead) == 1
        assert prefetch_service.on_download_failed.call_count == 1
        prefetch_service.on_download_failed.assert_called_once_with("series", "tt3749900:1:2", "tv")


def test_download_worker_uses_prefetch_min_progress_bytes(tmp_path):
    service = DownloadWorkerService(
        FakeTorrServerClient(),
        FakeCacheManager(tmp_path),
        LoggerFactory(str(tmp_path)),
        poll_seconds=1,
        connect_timeout_seconds=10,
        no_progress_timeout_seconds=90,
        min_progress_bytes=33554432,
        min_progress_window_seconds=600,
        max_total_seconds=60,
        progress_log_interval_seconds=1,
        prefetch_min_progress_bytes=1048576,
    )

    playback_job = DownloadJob(job_id="1", cache_key="1", link="http://example.com", enqueued_at=0, available_at=0, trigger="playback")
    prefetch_job = DownloadJob(job_id="2", cache_key="2", link="http://example.com", enqueued_at=0, available_at=0, trigger="next_episode_prefetch")

    assert service._required_min_progress_bytes(playback_job) == 33554432
    assert service._required_min_progress_bytes(prefetch_job) == 1048576


