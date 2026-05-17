import asyncio

from stremio_http_proxy.controller.playback_controller import PlaybackController


class FakeTorrServerClient:
    def __init__(self):
        self.added = []
        self.preloaded = []

    async def add_torrent(self, link: str, title=None, poster=None, category=None) -> dict:
        self.added.append((link, title, poster, category))
        return {}

    async def preload(self, link: str, title=None, poster=None, category=None) -> None:
        self.preloaded.append((link, title, poster, category))

    def build_play_url(self, link: str, title=None, poster=None, category=None) -> str:
        return f"http://localhost:8090/stream?link={link}&play=true"


def test_playback_controller_adds_preloads_and_redirects():
    client = FakeTorrServerClient()
    controller = PlaybackController(client)

    response = asyncio.run(
        controller.play(
            link="magnet:?xt=urn:btih:abc",
            title="demo",
            category="movie",
        )
    )

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:8090/stream?link=magnet:?xt=urn:btih:abc&play=true"
    assert client.added == [("magnet:?xt=urn:btih:abc", "demo", None, "movie")]
    assert client.preloaded == [("magnet:?xt=urn:btih:abc", "demo", None, "movie")]
