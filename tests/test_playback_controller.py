import asyncio
from urllib.parse import parse_qs, urlparse

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.controller.playback_controller import PlaybackController
from stremio_http_proxy.logger.logger_factory import LoggerFactory


class FakeTorrServerClient(TorrServerClient):
    def __init__(self):
        super().__init__("http://localhost:8090", 10)
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
                {"id": 4, "path": "Gotham S01E04.mkv"},
                {"id": 18, "path": "Movie.1080p.mkv"},
            ]
        }

    def build_play_url(self, link: str, title=None, poster=None, category=None, index=None) -> str:
        return f"http://localhost:8090/stream?link={link}&play=true&index={index}"


class FakeCacheService:
    def __init__(self, ready=False, ready_keys=None):
        self.ready = ready
        self.ready_keys = ready_keys or set()

    def get_cached_route(self, link: str, index: int | None = None, content_id: str | None = None) -> str | None:
        if (link, index) in self.ready_keys:
            return f"https://proxy.example.com/cache/ready/{index}"
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

    def schedule_prefetch(self, *args) -> None:
        self.calls.append(args)

    async def enqueue_next_episode(self, *args) -> None:
        self.calls.append(args)


class DummyTask:
    def __init__(self):
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)


def build_controller(tmp_path, ready=False, ready_keys=None):
    return PlaybackController(
        FakeTorrServerClient(),
        FakeCacheService(ready=ready, ready_keys=ready_keys),
        FakeDownloadQueueService(),
        FakeNextEpisodePrefetchService(),
        LoggerFactory(str(tmp_path)),
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


def test_playback_controller_redirects_to_cache_using_content_id_fallback(tmp_path):
    class FakeContentIdCacheService:
        def get_cached_route(self, link: str, index: int | None = None, content_id: str | None = None) -> str | None:
            if content_id == "tt3749900:1:2":
                return "https://proxy.example.com/cache/dd10bc/9?expires=1700000000&token=signed"
            return None

    controller = PlaybackController(
        FakeTorrServerClient(),
        FakeContentIdCacheService(),
        FakeDownloadQueueService(),
        FakeNextEpisodePrefetchService(),
        LoggerFactory(str(tmp_path)),
    )

    response = asyncio.run(
        controller.play(
            link="magnet:?xt=urn:btih:dd10bc",
            index=8,
            content_type="series",
            content_id="tt3749900:1:2",
        )
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://proxy.example.com/cache/dd10bc/9?expires=1700000000&token=signed"


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
    http_link = "https://example.com/stream/manifest.m3u8"

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














def test_playback_controller_enqueues_different_torrent_even_if_episode_cached_on_another_torrent(monkeypatch, tmp_path):
    # Torrent A is already ready in cache
    torrent_a = "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    torrent_b = "magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    ready_keys = {(torrent_a, 4)}

    controller = build_controller(tmp_path, ready_keys=ready_keys)
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        return DummyTask()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    # 1. User clicks Torrent B for episode Gotham S01E04 (tt3749900:1:4)
    resp_b = asyncio.run(
        controller.play(
            link=torrent_b,
            title="Gotham S01E04 1080p",
            category="tv",
            index=4,
            content_type="series",
            content_id="tt3749900:1:4",
        )
    )

    # Torrent B is not ready, so user is redirected to TorrServer
    assert resp_b.status_code == 307
    assert "stream?link=" in resp_b.headers["location"]

    # Background task MUST have been scheduled for Torrent B download
    for task in scheduled:
        asyncio.run(task)

    assert len(controller.download_queue_service.calls) == 1
    call_args, call_kwargs = controller.download_queue_service.calls[0]
    assert call_args[0] == torrent_b
    assert call_args[4] == 4
    assert call_kwargs["content_id"] == "tt3749900:1:4"
    assert call_kwargs["trigger"] == "playback"

    # 2. User clicks Torrent A for the same episode (which IS ready in cache)
    scheduled.clear()
    resp_a = asyncio.run(
        controller.play(
            link=torrent_a,
            title="Gotham S01E04 720p",
            category="tv",
            index=4,
            content_type="series",
            content_id="tt3749900:1:4",
        )
    )

    # Torrent A is ready, so user is redirected directly to cached file
    assert resp_a.status_code == 307
    assert resp_a.headers["location"] == "https://proxy.example.com/cache/ready/4"

    # No download should be enqueued for Torrent A
    assert len(controller.download_queue_service.calls) == 1


