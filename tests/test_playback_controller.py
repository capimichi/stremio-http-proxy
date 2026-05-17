import asyncio

from stremio_http_proxy.controller.playback_controller import PlaybackController


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


class DummyTask:
    def __init__(self):
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)


def test_playback_controller_redirects_immediately_and_schedules_initialization(monkeypatch):
    client = FakeTorrServerClient()
    controller = PlaybackController(client)
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
    assert len(scheduled) == 1
    assert client.added == []
    assert client.preloaded == []


def test_playback_controller_deduplicates_in_flight_initialization(monkeypatch):
    client = FakeTorrServerClient()
    controller = PlaybackController(client)
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


def test_playback_controller_background_task_adds_and_preloads():
    client = FakeTorrServerClient()
    controller = PlaybackController(client)

    async def main():
        response = await controller.play(
            link="magnet:?xt=urn:btih:abc",
            title="demo",
            category="movie",
            index=18,
        )
        assert response.status_code == 307
        assert client.added == []
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert client.added == [("magnet:?xt=urn:btih:abc", "demo", None, "movie")]
        assert client.preloaded == [("magnet:?xt=urn:btih:abc", "demo", None, "movie", 18)]

    asyncio.run(main())
