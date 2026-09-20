import asyncio
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from stremio_http_proxy.client.mediaflow_client import MediaflowClient
from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.controller.cache_controller import CacheController
from stremio_http_proxy.controller.playback_controller import PlaybackController
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.cache_token_service import CacheTokenService
from stremio_http_proxy.service.dashboard_service import DashboardService
from stremio_http_proxy.service.download_queue_service import DownloadQueueService
from stremio_http_proxy.service.download_worker_service import DownloadWorkerService
from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class DummyTorrServerClient(TorrServerClient):
    def __init__(self):
        self.added = []

    async def add_torrent(self, link: str, title=None, poster=None, category=None):
        self.added.append(link)
        return {}

    async def preload(self, link: str, title=None, poster=None, category=None, index=None):
        return {}

    def build_play_url(self, link: str, title=None, poster=None, category=None, index=None) -> str:
        return "http://torrserver/stream"


@pytest.mark.asyncio
async def test_e2e_toastflix_mediaflow_flow(tmp_path, monkeypatch):
    # Setup test components
    db_file = tmp_path / "app.db"
    cache_dir = tmp_path / "cache"
    log_dir = tmp_path / "logs"

    db_manager = DbManager(db_url=f"sqlite:///{db_file}")
    logger_factory = LoggerFactory(str(log_dir))

    cache_manager = CacheManager(
        base_dir=str(cache_dir),
        db_manager=db_manager,
        max_age_days=30,
        max_size_gb=10,
        logger_factory=logger_factory,
    )
    cache_manager.get_min_cache_size = lambda: 10

    cache_token_service = CacheTokenService(app_secret="test_secret", ttl_seconds=3600)
    cache_service = CacheService(
        cache_manager=cache_manager,
        public_base_url="http://localhost:8691",
        cache_token_service=cache_token_service,
    )

    mediaflow_client = MediaflowClient(
        base_url="https://mediaflow-proxy.michelecapicchioni.com",
        api_password="test_password",
    )

    stream_rewrite_service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
        mediaflow_client=mediaflow_client,
    )

    torrserver_client = DummyTorrServerClient()
    download_queue_service = DownloadQueueService(cache_manager=cache_manager, max_attempts=3)
    next_episode_prefetch_service = NextEpisodePrefetchService(None, None, logger_factory)

    playback_controller = PlaybackController(
        torrserver_client=torrserver_client,
        cache_service=cache_service,
        download_queue_service=download_queue_service,
        next_episode_prefetch_service=next_episode_prefetch_service,
        logger_factory=logger_factory,
    )

    worker_service = DownloadWorkerService(
        torrserver_client=torrserver_client,
        cache_manager=cache_manager,
        logger_factory=logger_factory,
        poll_seconds=1,
        connect_timeout_seconds=10,
        no_progress_timeout_seconds=30,
        min_progress_bytes=10,
        min_progress_window_seconds=120,
        max_total_seconds=60,
        progress_log_interval_seconds=1,
    )

    basic_auth_service = BasicAuthService()
    dashboard_service = DashboardService(cache_manager, "http://localhost:8691")
    cache_controller = CacheController(cache_service, cache_token_service, dashboard_service, basic_auth_service)

    # 1. Incoming Toastflix stream with /proxy/stream wrapping an HLS playlist (.m3u8#video.mp4)
    raw_toastflix_url = (
        "https://mediaflow-proxy.michelecapicchioni.com/_token123/proxy/stream"
        "?d=https%3A%2F%2Ftoastflix.stremio-italia.eu%2Fmanifest.m3u8%23video.mp4"
    )
    expected_fixed_hls_url = (
        "https://mediaflow-proxy.michelecapicchioni.com/_token123/proxy/hls/manifest.m3u8"
        "?d=https%3A%2F%2Ftoastflix.stremio-italia.eu%2Fmanifest.m3u8%23video.mp4"
    )

    manifest_payload = {
        "streams": [
            {
                "name": "[TF] Toastflix",
                "title": "Gotham S01E01 - Pilot\n1080p | ITA/ENG",
                "url": raw_toastflix_url,
            }
        ]
    }

    # Step 1: Manifest rewrite when not yet cached
    rewritten_1 = await stream_rewrite_service.rewrite(
        manifest_payload,
        category="series",
        content_type="series",
        content_id="tt3749900:1:1",
    )

    assert len(rewritten_1["streams"]) == 1
    stream_1 = rewritten_1["streams"][0]
    # No flame icon yet
    assert "🔥" not in stream_1["name"]
    # Proxied through /play/manifest.m3u8 with fixed HLS URL
    parsed_play_url = urlparse(stream_1["url"])
    assert parsed_play_url.path == "/play/manifest.m3u8"
    play_params = parse_qs(parsed_play_url.query)
    assert play_params["link"] == [expected_fixed_hls_url]
    assert play_params["content_id"] == ["tt3749900:1:1"]

    # Step 2: Stremio plays the stream -> calls PlaybackController.play
    play_response = await playback_controller.play(
        link=play_params["link"][0],
        title=play_params.get("title", [None])[0],
        content_type=play_params.get("content_type", [None])[0],
        content_id=play_params.get("content_id", [None])[0],
    )

    # Immediately returns 307 Redirect to the live fixed MediaFlow HLS URL
    assert play_response.status_code == 307
    assert play_response.headers["location"] == expected_fixed_hls_url
    # TorrServer must NOT be involved
    assert len(torrserver_client.added) == 0

    # Yield control to let asyncio background task enqueue the job
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Step 3: Background Worker downloads the HLS stream
    class FakeProc:
        def __init__(self, target_file):
            self.returncode = 0
            self.target_file = target_file

        async def wait(self):
            with open(self.target_file, "wb") as f:
                f.write(b"GOTHAM_EPISODE_1_CONTENT" * 100)
            return 0

        async def communicate(self):
            return b"", b""

        def kill(self):
            pass

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        output_file = cmd[-1]
        return FakeProc(output_file)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    processed = await worker_service.process_next_job()
    assert processed is True

    # Expected cache key
    url_hash = hashlib.sha1(expected_fixed_hls_url.encode("utf-8")).hexdigest()
    expected_cache_key = f"{url_hash}:0"
    assert cache_manager.is_ready(expected_cache_key) is True

    # Step 4: Subsequent Manifest Rewrite now returns cached stream with 🔥 icon!
    rewritten_2 = await stream_rewrite_service.rewrite(
        manifest_payload,
        category="series",
        content_type="series",
        content_id="tt3749900:1:1",
    )

    stream_2 = rewritten_2["streams"][0]
    assert stream_2["name"].startswith("🔥")
    parsed_play_url_2 = urlparse(stream_2["url"])
    assert parsed_play_url_2.path == "/play"

    # Step 5: Stremio plays the cached stream via /play
    play_cached_response = await playback_controller.play(
        link=expected_fixed_hls_url,
        content_type="series",
        content_id="tt3749900:1:1",
    )
    assert play_cached_response.status_code == 307
    cached_location = play_cached_response.headers["location"]
    parsed_cache_url = urlparse(cached_location)
    assert parsed_cache_url.path == f"/cache/{url_hash}/0"

    cache_params = parse_qs(parsed_cache_url.query)
    assert "expires" in cache_params
    assert "token" in cache_params

    # Step 6: Player fetches the cached media file
    file_response = await cache_controller.serve(
        infohash=url_hash,
        index=0,
        expires=int(cache_params["expires"][0]),
        token=cache_params["token"][0],
    )
    assert file_response.status_code == 200
    assert file_response.path.endswith("0.media")
