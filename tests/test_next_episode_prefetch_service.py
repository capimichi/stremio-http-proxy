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
        target_completed_per_episode=3,
        skip_zero_seeders=False,
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
        enabled=True,
    )

    asyncio.run(service.enqueue_next_episode("series", "tt123:1:1", "tv"))

    assert len(queue.calls) == 1
    assert queue.calls[0]["content_id"] == "tt123:2:1"


class FakeDetailedCacheManager:
    def __init__(self, ready_counts=None, attempted_keys=None):
        self.ready_counts = ready_counts or {}
        self.attempted_keys = attempted_keys or set()

    def build_cache_key(self, link: str, index: int | None = None) -> str:
        return f"{link}:{index or 0}"

    def count_active_or_ready_for_content(self, content_id: str) -> int:
        return self.ready_counts.get(content_id, 0)

    def is_candidate_attempted(self, cache_key: str) -> bool:
        return cache_key in self.attempted_keys


class SeederUpstreamClient:
    async def get_json(self, path: str, query_params=None) -> dict:
        return {
            "streams": [
                {
                    "title": "zero seeds",
                    "description": "📄 file0.mkv\n💾 1GB\n🌍 🇮🇹 | 👤 0 | ⏰",
                    "infoHash": "0" * 40,
                },
                {
                    "title": "15 seeds",
                    "description": "📄 file1.mkv\n💾 1GB\n🌍 🇮🇹 | 👤 15 | ⏰",
                    "infoHash": "1" * 40,
                },
                {
                    "title": "5 seeds",
                    "description": "📄 file2.mkv\n💾 1GB\n🌍 🇮🇹 | 👤 5 | ⏰",
                    "infoHash": "2" * 40,
                },
            ]
        }


def test_prefetch_skips_zero_seeders_and_picks_single_highest_seeder():
    queue = FakeDownloadQueueService()
    cache_mgr = FakeDetailedCacheManager()
    service = NextEpisodePrefetchService(
        SeederUpstreamClient(),
        StreamRewriteService("http://localhost:8691", FakeCacheManager()),
        queue,
        cache_manager=cache_mgr,
        enabled=True,
        target_completed_per_episode=1,
        skip_zero_seeders=True,
    )

    asyncio.run(service.enqueue_next_episode("series", "tt123:1:1", "tv"))

    # Must only enqueue ONE candidate (target_completed_per_episode=1)
    assert len(queue.calls) == 1
    # Must have chosen candidate with 15 seeders ("1" * 40), skipping 0 seeders ("0" * 40)
    assert queue.calls[0]["link"] == "1" * 40
    assert queue.calls[0]["title"].startswith("15 seeds")


def test_prefetch_on_download_failed_cascades_to_next_candidate():
    queue = FakeDownloadQueueService()
    # Candidate 1 ("1" * 40) was already attempted and failed
    cache_mgr = FakeDetailedCacheManager(attempted_keys={f"{'1' * 40}:0"})
    service = NextEpisodePrefetchService(
        SeederUpstreamClient(),
        StreamRewriteService("http://localhost:8691", FakeCacheManager()),
        queue,
        cache_manager=cache_mgr,
        enabled=True,
        target_completed_per_episode=1,
        skip_zero_seeders=True,
    )

    asyncio.run(service.on_download_failed("series", "tt123:1:2", "tv"))

    # Must enqueue the next best candidate (5 seeders: "2" * 40)
    assert len(queue.calls) == 1
    assert queue.calls[0]["link"] == "2" * 40
    assert queue.calls[0]["title"].startswith("5 seeds")


def test_prefetch_skips_if_target_completed_already_reached():
    queue = FakeDownloadQueueService()
    # Target=1 and we already have 1 active/ready
    cache_mgr = FakeDetailedCacheManager(ready_counts={"tt123:1:2": 1})
    service = NextEpisodePrefetchService(
        SeederUpstreamClient(),
        StreamRewriteService("http://localhost:8691", FakeCacheManager()),
        queue,
        cache_manager=cache_mgr,
        enabled=True,
        target_completed_per_episode=1,
        skip_zero_seeders=True,
    )

    asyncio.run(service.enqueue_next_episode("series", "tt123:1:1", "tv"))

    assert len(queue.calls) == 0
