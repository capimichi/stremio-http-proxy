import asyncio

import httpx

from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class FakeCacheManager:
    def build_cache_key(self, link: str, index: int | None = None) -> str:
        return f"{link}:{index or 0}"

    def is_ready(self, cache_key: str) -> bool:
        return False


class FakeUpstreamClient:
    async def get_json(self, path: str, query_params=None) -> dict:
        if path == "/stream/series/tt123:1:2.json":
            return {
                "streams": [
                    {"title": "one", "magnet": "magnet:?xt=urn:btih:1111111111111111111111111111111111111111"},
                    {"title": "two", "magnet": "magnet:?xt=urn:btih:2222222222222222222222222222222222222222"},
                    {"title": "three", "magnet": "magnet:?xt=urn:btih:3333333333333333333333333333333333333333"},
                    {"title": "four", "magnet": "magnet:?xt=urn:btih:4444444444444444444444444444444444444444"},
                ]
            }
        if path == "/stream/series/tt123:2:1.json":
            return {"streams": []}
        raise AssertionError(path)


class FakeDownloadQueueService:
    def __init__(self):
        self.calls = []

    async def enqueue_download(self, **kwargs):
        self.calls.append(kwargs)
        return True


def test_next_episode_prefetch_enqueues_first_three_streams():
    queue = FakeDownloadQueueService()
    service = NextEpisodePrefetchService(
        FakeUpstreamClient(),
        StreamRewriteService("http://localhost:8691", FakeCacheManager()),
        queue,
        3,
    )

    asyncio.run(service.enqueue_next_episode("series", "tt123:1:1", "tv"))

    assert len(queue.calls) == 3
    assert [call["title"] for call in queue.calls] == ["one", "two", "three"]
    assert all(call["trigger"] == "next_episode_prefetch" for call in queue.calls)


def test_next_episode_prefetch_skips_when_id_is_not_episode_like():
    queue = FakeDownloadQueueService()
    service = NextEpisodePrefetchService(
        FakeUpstreamClient(),
        StreamRewriteService("http://localhost:8691", FakeCacheManager()),
        queue,
        3,
    )

    asyncio.run(service.enqueue_next_episode("series", "tt123", "tv"))

    assert queue.calls == []


class FallbackUpstreamClient:
    async def get_json(self, path: str, query_params=None) -> dict:
        if path == "/stream/series/tt123:1:2.json":
            request = httpx.Request("GET", "https://example.com" + path)
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        if path == "/stream/series/tt123:2:1.json":
            return {
                "streams": [
                    {"title": "season 2", "magnet": "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
                ]
            }
        raise AssertionError(path)


def test_next_episode_prefetch_tries_next_season_after_404():
    queue = FakeDownloadQueueService()
    service = NextEpisodePrefetchService(
        FallbackUpstreamClient(),
        StreamRewriteService("http://localhost:8691", FakeCacheManager()),
        queue,
        3,
    )

    asyncio.run(service.enqueue_next_episode("series", "tt123:1:1", "tv"))

    assert len(queue.calls) == 1
    assert queue.calls[0]["content_id"] == "tt123:2:1"
