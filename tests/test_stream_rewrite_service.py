import asyncio

from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class FakeTorrServerClient:
    def __init__(self, fail_on_link: str | None = None):
        self.fail_on_link = fail_on_link
        self.added: list[tuple[str, str | None, str | None, str | None]] = []
        self.preloaded: list[tuple[str, str | None, str | None, str | None]] = []

    async def add_torrent(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
    ) -> dict:
        if link == self.fail_on_link:
            raise RuntimeError("boom")
        self.added.append((link, title, poster, category))
        return {}

    async def preload(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
    ) -> None:
        self.preloaded.append((link, title, poster, category))

    def build_play_url(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
    ) -> str:
        return f"http://localhost:8090/stream?link={link}&play=true&category={category}"


def test_stream_rewrite_uses_torrserver_url_for_torrent_streams():
    client = FakeTorrServerClient()
    service = StreamRewriteService(client)
    payload = {
        "streams": [
            {
                "title": "demo",
                "magnet": "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
                "url": "https://upstream.invalid/old",
            }
        ]
    }

    rewritten = asyncio.run(service.rewrite(payload, category="movie"))

    assert rewritten["streams"][0]["url"].startswith("http://localhost:8090/stream?")
    assert client.added == [
        (
            "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
            "demo",
            None,
            "movie",
        )
    ]
    assert client.preloaded == [
        (
            "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
            "demo",
            None,
            "movie",
        )
    ]


def test_stream_rewrite_leaves_non_torrent_streams_unchanged():
    service = StreamRewriteService(FakeTorrServerClient())
    payload = {"streams": [{"title": "demo", "url": "https://upstream.invalid/video.mp4"}]}

    rewritten = asyncio.run(service.rewrite(payload, category="movie"))

    assert rewritten == payload


def test_stream_rewrite_keeps_original_stream_when_torrserver_fails():
    service = StreamRewriteService(FakeTorrServerClient(fail_on_link="abc123"))
    payload = {"streams": [{"title": "demo", "infoHash": "abc123", "url": "https://upstream.invalid/old"}]}

    rewritten = asyncio.run(service.rewrite(payload, category="movie"))

    assert rewritten["streams"][0]["url"] == "https://upstream.invalid/old"
