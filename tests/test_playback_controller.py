import asyncio

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

    def build_play_url(self, link: str, title=None, poster=None, category=None, index=None) -> str:
        return f"http://localhost:8090/stream?link={link}&play=true&index={index}"


class FakeCacheManager:
    def __init__(self, ready=False):
        self.ready = ready

    def build_cache_key(self, link: str, index: int | None = None) -> str:
        return f"abc:{index or 0}"

    def is_ready(self, cache_key: str) -> bool:
        return self.ready

    def parse_cache_key(self, cache_key: str) -> tuple[str, int]:
        return ("abc", 18)


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


def build_controller(tmp_path, ready=False):
    return PlaybackController(
        FakeTorrServerClient(),
        FakeCacheManager(ready=ready),
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
    assert response.headers["location"] == "/cache/abc/18"
