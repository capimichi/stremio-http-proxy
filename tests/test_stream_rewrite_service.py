import pytest

from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class FakeCacheManager:
    def __init__(self, ready_cache_keys: set[str] | None = None):
        self.ready_cache_keys = ready_cache_keys or set()

    def build_cache_key(self, link: str, index: int | None = None) -> str:
        return f"{link}:{index or 0}"

    def is_ready(self, cache_key: str) -> bool:
        return cache_key in self.ready_cache_keys


class FakeTorrentHealthService:
    def __init__(self, health_map: dict[str, tuple[bool, int | None]] | None = None):
        self.health_map = health_map or {}

    async def check_batch(self, links: list[str], timeout: float = 15.0) -> dict[str, tuple[bool, int | None]]:
        return {link: self.health_map.get(link, (False, None)) for link in links}


@pytest.mark.asyncio
async def test_stream_rewrite_uses_local_playback_url_for_torrent_streams():
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager())
    payload = {
        "streams": [
            {
                "title": "demo",
                "magnet": "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
                "fileIdx": 17,
                "url": "https://upstream.invalid/old",
            }
        ]
    }

    rewritten = await service.rewrite(payload, category="movie")

    assert rewritten["streams"][0]["url"] == (
        "http://localhost:8691/play?"
        "link=magnet%3A%3Fxt%3Durn%3Abtih%3AABCDEF1234567890ABCDEF1234567890ABCDEF12"
        "&title=demo&category=movie&index=18"
    )


@pytest.mark.asyncio
async def test_stream_rewrite_leaves_non_torrent_streams_unchanged():
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager())
    payload = {"streams": [{"title": "demo", "url": "https://upstream.invalid/video.mp4"}]}

    rewritten = await service.rewrite(payload, category="movie")

    assert rewritten == payload


@pytest.mark.asyncio
async def test_stream_rewrite_includes_content_context_for_episode_prefetch():
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager())
    payload = {
        "streams": [
            {
                "title": "demo",
                "magnet": "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
            }
        ]
    }

    rewritten = await service.rewrite(payload, category="tv", content_type="series", content_id="tt123:1:2")

    assert "content_type=series" in rewritten["streams"][0]["url"]
    assert "content_id=tt123%3A1%3A2" in rewritten["streams"][0]["url"]


@pytest.mark.asyncio
async def test_stream_rewrite_marks_cached_streams_when_local_cache_is_ready():
    magnet = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12"
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager({f"{magnet}:18"}))
    payload = {
        "streams": [
            {
                "name": "Torrentio 1080p",
                "title": "demo",
                "magnet": magnet,
                "fileIdx": 17,
                "_meta": {"cached": False},
            }
        ]
    }

    rewritten = await service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["_meta"]["cached"] is True
    assert rewritten["streams"][0]["name"] == "🔥 Torrentio 1080p"


@pytest.mark.asyncio
async def test_stream_rewrite_does_not_duplicate_cached_name_prefix():
    magnet = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12"
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager({f"{magnet}:18"}))
    payload = {
        "streams": [
            {
                "name": "🔥 Torrentio 1080p",
                "title": "demo",
                "magnet": magnet,
                "fileIdx": 17,
            }
        ]
    }

    rewritten = await service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["name"] == "🔥 Torrentio 1080p"


@pytest.mark.asyncio
async def test_health_check_prefixes_streams_with_stat_three():
    magnet1 = "magnet:?xt=urn:btih:A000000000000000000000000000000000000001"
    magnet2 = "magnet:?xt=urn:btih:A000000000000000000000000000000000000002"
    fake_health = FakeTorrentHealthService({magnet1: (True, 12), magnet2: (False, None)})
    service = StreamRewriteService(
        "http://localhost:8691",
        FakeCacheManager(),
        torrent_health_service=fake_health,
        torrserver_health_check_enabled=True,
    )
    payload = {
        "streams": [
            {"name": "Stream A", "title": "a", "magnet": magnet1, "fileIdx": 0},
            {"name": "Stream B", "title": "b", "magnet": magnet2, "fileIdx": 0},
        ]
    }

    rewritten = await service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["name"] == "✅ Stream A"
    assert rewritten["streams"][1]["name"] == "Stream B"


@pytest.mark.asyncio
async def test_health_check_sets_meta_seeders():
    magnet = "magnet:?xt=urn:btih:A000000000000000000000000000000000000001"
    fake_health = FakeTorrentHealthService({magnet: (True, 7)})
    service = StreamRewriteService(
        "http://localhost:8691",
        FakeCacheManager(),
        torrent_health_service=fake_health,
        torrserver_health_check_enabled=True,
    )
    payload = {
        "streams": [
            {"name": "Stream A", "title": "a", "magnet": magnet, "fileIdx": 0}
        ]
    }

    rewritten = await service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["_meta"]["seeders"] == 7


@pytest.mark.asyncio
async def test_health_check_sets_meta_seeders_even_when_not_playable():
    magnet = "magnet:?xt=urn:btih:A000000000000000000000000000000000000001"
    fake_health = FakeTorrentHealthService({magnet: (False, 3)})
    service = StreamRewriteService(
        "http://localhost:8691",
        FakeCacheManager(),
        torrent_health_service=fake_health,
        torrserver_health_check_enabled=True,
    )
    payload = {
        "streams": [
            {"name": "Stream A", "title": "a", "magnet": magnet, "fileIdx": 0}
        ]
    }

    rewritten = await service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["_meta"]["seeders"] == 3
    assert rewritten["streams"][0]["name"] == "Stream A"


@pytest.mark.asyncio
async def test_health_check_skips_cached_streams():
    magnet1 = "magnet:?xt=urn:btih:A000000000000000000000000000000000000001"
    magnet2 = "magnet:?xt=urn:btih:A000000000000000000000000000000000000002"
    fake_health = FakeTorrentHealthService({magnet1: (True, 5), magnet2: (True, 8)})
    service = StreamRewriteService(
        "http://localhost:8691",
        FakeCacheManager({f"{magnet1}:1"}),
        torrent_health_service=fake_health,
        torrserver_health_check_enabled=True,
    )
    payload = {
        "streams": [
            {"name": "Cached", "title": "c", "magnet": magnet1, "fileIdx": 0},
            {"name": "Uncached", "title": "u", "magnet": magnet2, "fileIdx": 0},
        ]
    }

    rewritten = await service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["name"] == "🔥 Cached"
    assert "seeders" not in rewritten["streams"][0].get("_meta", {})
    assert rewritten["streams"][1]["name"] == "✅ Uncached"
    assert rewritten["streams"][1]["_meta"]["seeders"] == 8


@pytest.mark.asyncio
async def test_health_check_skips_cached_when_all_cached():
    magnet = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12"
    fake_health = FakeTorrentHealthService({magnet: (True, 10)})
    service = StreamRewriteService(
        "http://localhost:8691",
        FakeCacheManager({f"{magnet}:18"}),
        torrent_health_service=fake_health,
        torrserver_health_check_enabled=True,
    )
    payload = {
        "streams": [
            {"name": "Torrentio 1080p", "title": "demo", "magnet": magnet, "fileIdx": 17}
        ]
    }

    rewritten = await service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["_meta"]["cached"] is True
    assert rewritten["streams"][0]["name"] == "🔥 Torrentio 1080p"


@pytest.mark.asyncio
async def test_health_check_skipped_when_disabled():
    magnet = "magnet:?xt=urn:btih:A000000000000000000000000000000000000001"
    fake_health = FakeTorrentHealthService({magnet: (True, 4)})
    service = StreamRewriteService(
        "http://localhost:8691",
        FakeCacheManager(),
        torrent_health_service=fake_health,
        torrserver_health_check_enabled=False,
    )
    payload = {
        "streams": [
            {"name": "Stream A", "title": "a", "magnet": magnet}
        ]
    }

    rewritten = await service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["name"] == "Stream A"
