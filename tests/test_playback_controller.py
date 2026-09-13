import asyncio
from urllib.parse import parse_qs, urlparse

from stremio_http_proxy.controller.playback_controller import PlaybackController
from stremio_http_proxy.logger.logger_factory import LoggerFactory


class FakeTorrServerClient:
    def __init__(self):
        self.added = []
        self.preloaded = []

    async def add_torrent(self, link: str, title=None, poster=None, category=None) -> dict:
        self.added.append((link, title, poster, category))
        return {}

    async def preload(self, link: str, title=None, poster=None, category=None, index=None) -> None:
        self.preloaded.append((link, title, poster, category, index))

    async def add_and_get_status(self, link: str, timeout=None) -> dict:
        return {
            "hash": "abc",
            "file_stats": [
                {"id": 1, "path": "Show S01E01.mkv"},
                {"id": 2, "path": "Show S01E02.mkv"},
                {"id": 3, "path": "Show S01E03.srt"},
            ]
        }

    def build_play_url(self, link: str, title=None, poster=None, category=None, index=None) -> str:
        return f"http://localhost:8090/stream?link={link}&play=true&index={index}"


class FakeCacheService:
    def __init__(self, ready=False):
        self.ready = ready

    def get_cached_route(self, link: str, index: int | None = None) -> str | None:
        if not self.ready:
            return None
        return "https://proxy.example.com/cache/abc/18?expires=1700000000&token=signed"


class FakeDownloadQueueService:
    def __init__(self):
        self.calls = []

    async def enqueue_download(self, *args, **kwargs) -> bool:
        self.calls.append((args, kwargs))
        return True


class FakeNextEpisodePrefetchService:
    def __init__(self):
        self.calls = []

    async def enqueue_next_episode(self, *args) -> None:
        self.calls.append(args)


class DummyTask:
    def __init__(self):
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)


def build_controller(tmp_path, ready=False, http_streams_proxy_enabled=True):
    return PlaybackController(
        FakeTorrServerClient(),
        FakeCacheService(ready=ready),
        FakeDownloadQueueService(),
        FakeNextEpisodePrefetchService(),
        LoggerFactory(str(tmp_path)),
        http_streams_proxy_enabled=http_streams_proxy_enabled,
    )


def test_playback_controller_redirects_immediately_and_schedules_background_work(monkeypatch, tmp_path):
    controller = build_controller(tmp_path)
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        return DummyTask()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    response = asyncio.run(
        controller.play(
            link="magnet:?xt=urn:btih:abc",
            title="demo",
            category="movie",
            index=18,
        )
    )

    for coro in scheduled:
        coro.close()

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:8090/stream?link=magnet:?xt=urn:btih:abc&play=true&index=18"
    assert len(scheduled) == 2


def test_playback_controller_deduplicates_in_flight_initialization(tmp_path, monkeypatch):
    controller = build_controller(tmp_path)
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        return DummyTask()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    controller._schedule_initialization("abc", "demo", None, "movie", 18)
    controller._schedule_initialization("abc", "demo", None, "movie", 18)

    for coro in scheduled:
        coro.close()

    assert len(scheduled) == 1


def test_playback_controller_background_task_adds_preloads_and_enqueues(tmp_path):
    controller = build_controller(tmp_path)

    async def main():
        response = await controller.play(
            link="magnet:?xt=urn:btih:abc",
            title="demo",
            category="movie",
            index=18,
            content_type="series",
            content_id="tt123:1:2",
        )
        assert response.status_code == 307
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert controller.torrserver_client.added == [("magnet:?xt=urn:btih:abc", "demo", None, "movie")]
        assert controller.torrserver_client.preloaded == [("magnet:?xt=urn:btih:abc", "demo", None, "movie", 18)]
        assert len(controller.download_queue_service.calls) == 1
        assert controller.next_episode_prefetch_service.calls == [("series", "tt123:1:2", "movie")]

    asyncio.run(main())


def test_playback_controller_redirects_to_cache_when_ready(tmp_path):
    controller = build_controller(tmp_path, ready=True)

    response = asyncio.run(controller.play(link="magnet:?xt=urn:btih:abc", index=18))

    assert response.status_code == 307
    assert response.headers["location"] == "https://proxy.example.com/cache/abc/18?expires=1700000000&token=signed"


def test_playback_controller_redirects_to_signed_torrserver_url_when_cache_not_ready(tmp_path):
    controller = build_controller(tmp_path)

    response = asyncio.run(controller.play(link="magnet:?xt=urn:btih:abc", index=18))
    parsed = urlparse(response.headers["location"])
    params = parse_qs(parsed.query)

    assert response.status_code == 307
    assert parsed.path == "/stream"
    assert params["play"] == ["true"]


def test_playback_controller_resolves_missing_series_index(tmp_path):
    controller = build_controller(tmp_path)

    response = asyncio.run(
        controller.play(
            link="magnet:?xt=urn:btih:abc",
            content_type="series",
            content_id="tt7587890:1:2",
        )
    )

    assert response.status_code == 307
    parsed = urlparse(response.headers["location"])
    params = parse_qs(parsed.query)
    assert params["index"] == ["2"]


def test_playback_controller_handles_http_streams_immediately(tmp_path):
    controller = build_controller(tmp_path)
    http_link = "https://mediaflow.example.com/_token_123/proxy/hls/manifest.m3u8"

    async def main():
        response = await controller.play(
            link=http_link,
            title="Gotham S01E01",
            content_type="series",
            content_id="tt3749900:1:1",
        )

        # Immediately redirects to the live HTTP stream without touching TorrServer
        assert response.status_code == 307
        assert response.headers["location"] == http_link
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(controller.torrserver_client.added) == 0
        # And background download was enqueued
        assert len(controller.download_queue_service.calls) == 1
        assert controller.download_queue_service.calls[0][0][0] == http_link

    asyncio.run(main())


def test_clean_hls_manifest():
    raw_manifest = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080,AUDIO="audio",SUBTITLES="subs"
http://mediaflow.example.com/video_1080.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720,AUDIO="audio",SUBTITLES="subs"
video_720.m3u8
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Italian",URI="http://mediaflow.example.com/audio_it.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="ar",URI="http://mediaflow.example.com/sub_ar.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="en",URI="http://mediaflow.example.com/sub_en.m3u8"
"""
    base_url = "https://mediaflow.example.com/manifest.m3u8"
    cleaned = PlaybackController._clean_hls_manifest(raw_manifest, base_url)

    # Subtitles must be removed
    assert "TYPE=SUBTITLES" not in cleaned
    assert "sub_ar.m3u8" not in cleaned
    assert "sub_en.m3u8" not in cleaned

    # SUBTITLES attribute must be removed from EXT-X-STREAM-INF
    assert 'SUBTITLES="subs"' not in cleaned
    assert '#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080,AUDIO="audio"' in cleaned

    # http URLs must be upgraded to https
    assert "https://mediaflow.example.com/video_1080.m3u8" in cleaned
    assert "http://mediaflow.example.com/video_1080.m3u8" not in cleaned
    assert 'URI="https://mediaflow.example.com/audio_it.m3u8"' in cleaned

    # Relative URL must be resolved to absolute https URL
    assert "https://mediaflow.example.com/video_720.m3u8" in cleaned


def test_playback_controller_play_manifest_cleans_and_serves(tmp_path, monkeypatch):
    controller = build_controller(tmp_path)
    http_link = "https://mediaflow.example.com/_token_123/proxy/hls/manifest.m3u8"

    raw_manifest = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080,AUDIO="audio"
https://mediaflow.example.com/video.m3u8
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="ar",URI="https://mediaflow.example.com/sub.m3u8"
"""

    import respx
    import httpx

    with respx.mock:
        respx.get(http_link).respond(
            status_code=200,
            text=raw_manifest,
            headers={"content-type": "application/vnd.apple.mpegurl"},
        )
        respx.get("https://mediaflow.example.com/video.m3u8").respond(
            status_code=200,
            text="#EXTM3U\n#EXTINF:10.0,\nhttps://mediaflow.example.com/chunk_0.ts\n",
        )
        respx.get("https://mediaflow.example.com/chunk_0.ts").respond(
            status_code=200,
            content=b"CHUNK_DATA",
        )

        async def main():
            response = await controller.play_manifest(
                link=http_link,
                title="Ted Lasso",
                content_type="series",
                content_id="tt10986410:2:1",
            )
            assert response.status_code == 200
            assert response.media_type == "application/vnd.apple.mpegurl"
            body = response.body.decode("utf-8")
            assert "TYPE=SUBTITLES" not in body
            assert "https://mediaflow.example.com/video.m3u8" in body

        asyncio.run(main())


def test_playback_controller_master_manifest_rewrites_variant_with_cache_key(tmp_path):
    class FakeCacheMgr:
        base_dir = tmp_path

        def build_cache_key(self, link, index=None):
            return "key123:0"

    class FakeFullCacheService:
        cache_manager = FakeCacheMgr()
        public_base_url = "http://localhost:8691"

        def get_cached_route(self, link, index=None):
            return None

    controller = PlaybackController(
        FakeTorrServerClient(),
        FakeFullCacheService(),
        FakeDownloadQueueService(),
        FakeNextEpisodePrefetchService(),
        LoggerFactory(str(tmp_path)),
    )

    http_link = "https://mediaflow.example.com/manifest.m3u8"
    raw_manifest = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080
https://mediaflow.example.com/variant_1080.m3u8
"""

    import respx

    with respx.mock:
        respx.get(http_link).respond(
            status_code=200,
            text=raw_manifest,
            headers={"content-type": "application/vnd.apple.mpegurl"},
        )
        respx.get("https://mediaflow.example.com/variant_1080.m3u8").respond(
            status_code=200,
            text="#EXTM3U\n#EXTINF:10.0,\nhttps://mediaflow.example.com/chunk_1080_0.ts\n",
        )
        respx.get("https://mediaflow.example.com/chunk_1080_0.ts").respond(
            status_code=200,
            content=b"CHUNK_DATA",
        )

        async def main():
            response = await controller.play_manifest(link=http_link)
            assert response.status_code == 200
            body = response.body.decode("utf-8")
            assert "http://localhost:8691/play/variant.m3u8?key=key123%3A0&link=https%3A%2F%2Fmediaflow.example.com%2Fvariant_1080.m3u8" in body

        asyncio.run(main())


def test_playback_controller_play_manifest_fails_when_upstream_chunk_returns_403(tmp_path):
    controller = build_controller(tmp_path)
    http_link = "https://mediaflow.example.com/_token_bad/proxy/hls/manifest.m3u8"
    raw_manifest = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080
https://mediaflow.example.com/variant.m3u8
"""
    import respx

    with respx.mock:
        respx.get(http_link).respond(
            status_code=200,
            text=raw_manifest,
            headers={"content-type": "application/vnd.apple.mpegurl"},
        )
        respx.get("https://mediaflow.example.com/variant.m3u8").respond(
            status_code=200,
            text="#EXTM3U\n#EXTINF:10.0,\nhttps://mediaflow.example.com/chunk_0.ts\n",
        )
        respx.get("https://mediaflow.example.com/chunk_0.ts").respond(
            status_code=403,
            text="Access Denied",
        )

        async def main():
            response = await controller.play_manifest(link=http_link)
            assert response.status_code == 502
            assert "403" in response.body.decode("utf-8")
            # Ensure downloads were NOT scheduled
            assert len(controller.download_queue_service.calls) == 0

        asyncio.run(main())


def test_playback_controller_play_variant_rewrites_chunks_and_play_chunk_serves(tmp_path):
    class FakeCacheMgr:
        base_dir = tmp_path

        def build_cache_key(self, link, index=None):
            return "var_key:0"

    class FakeFullCacheService:
        cache_manager = FakeCacheMgr()
        public_base_url = "http://localhost:8691"

        def get_cached_route(self, link, index=None):
            return None

    controller = PlaybackController(
        FakeTorrServerClient(),
        FakeFullCacheService(),
        FakeDownloadQueueService(),
        FakeNextEpisodePrefetchService(),
        LoggerFactory(str(tmp_path)),
    )

    variant_link = "https://mediaflow.example.com/variant.m3u8"
    raw_variant = """#EXTM3U
#EXT-X-VERSION:3
#EXTINF:4.000000,
segment0.ts
#EXTINF:4.000000,
https://mediaflow.example.com/segment1.ts
"""

    import respx

    with respx.mock:
        respx.get(variant_link).respond(status_code=200, text=raw_variant)
        respx.get("https://mediaflow.example.com/segment0.ts").respond(
            status_code=200,
            content=b"SEGMENT_0_TS_DATA",
            headers={"content-type": "video/mp2t"},
        )

        async def main():
            # 1. Fetch variant playlist
            resp = await controller.play_variant(key="var_key:0", link=variant_link)
            assert resp.status_code == 200
            body = resp.body.decode("utf-8")
            assert "http://localhost:8691/play/chunk?key=var_key%3A0&seq=0&url=https%3A%2F%2Fmediaflow.example.com%2Fsegment0.ts" in body
            assert "http://localhost:8691/play/chunk?key=var_key%3A0&seq=1&url=https%3A%2F%2Fmediaflow.example.com%2Fsegment1.ts" in body

            # Check metadata was saved
            meta = controller.hls_chunk_manager.get_playlist_metadata("var_key:0")
            assert meta == [
                "https://mediaflow.example.com/segment0.ts",
                "https://mediaflow.example.com/segment1.ts",
            ]

            # 2. Fetch chunk 0
            chunk_resp = await controller.play_chunk(
                key="var_key:0",
                seq=0,
                url="https://mediaflow.example.com/segment0.ts",
            )
            assert chunk_resp.status_code == 200
            assert chunk_resp.media_type == "video/mp2t"
            assert controller.hls_chunk_manager.has_chunk("var_key:0", 0)

            # 3. Test fallback if chunk download errors
            respx.get("https://mediaflow.example.com/broken.ts").respond(status_code=500)
            err_resp = await controller.play_chunk(
                key="var_key:0",
                seq=99,
                url="https://mediaflow.example.com/broken.ts",
            )
            assert err_resp.status_code == 307
            assert err_resp.headers["location"] == "https://mediaflow.example.com/broken.ts"

        asyncio.run(main())


def test_playback_controller_http_stream_redirects_and_prefetches_without_caching_self(monkeypatch, tmp_path):
    controller = build_controller(tmp_path, http_streams_proxy_enabled=False)
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        return DummyTask()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    http_url = "https://easyproxy.example.com/dual/manifest.m3u8?d=123"
    response = asyncio.run(
        controller.play(
            link=http_url,
            title="Gotham S01E01",
            category="tv",
            content_type="series",
            content_id="tt3749900:1:1",
        )
    )

    # 1. Must redirect 307 directly to the original HTTP URL
    assert response.status_code == 307
    assert response.headers["location"] == http_url

    # 2. Execute background tasks scheduled
    assert len(scheduled) == 1
    asyncio.run(scheduled[0])

    # 3. Must NOT enqueue the HTTP stream itself into download queue
    assert len(controller.download_queue_service.calls) == 0

    # 4. Must trigger next episode prefetch for Gotham S01E02!
    assert len(controller.next_episode_prefetch_service.calls) == 1
    assert controller.next_episode_prefetch_service.calls[0] == ("series", "tt3749900:1:1", "tv")


