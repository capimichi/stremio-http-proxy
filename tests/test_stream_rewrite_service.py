import urllib.parse
from unittest.mock import MagicMock
import pytest

from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class FakeCacheManager:
    def __init__(self, ready_cache_keys: set[str] | None = None, ready_contents: set[tuple[str, str]] | None = None):
        self.ready_cache_keys = ready_cache_keys or set()
        self.ready_contents = ready_contents or set()

    def build_cache_key(self, link: str, index: int | None = None) -> str:
        return f"{link}:{index or 0}"

    def is_ready(self, cache_key: str) -> bool:
        return cache_key in self.ready_cache_keys

    def is_content_ready(self, infohash: str, content_id: str | None) -> bool:
        return (infohash.lower(), content_id) in self.ready_contents


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
async def test_stream_rewrite_leaves_non_torrent_non_http_streams_unchanged():
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager())
    payload = {"streams": [{"title": "demo", "url": "custom://unknown/stream"}]}

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


def test_extract_download_candidates_filters_non_video_streams():
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager())
    payload = {
        "streams": [
            {
                "name": "Stream 1",
                "title": "Episode 1.mp4",
                "magnet": "magnet:?xt=urn:btih:ABC",
            },
            {
                "name": "Stream 2",
                "behaviorHints": {"filename": "Episode 1.srt"},
                "magnet": "magnet:?xt=urn:btih:DEF",
            },
            {
                "name": "Stream 3",
                "title": "Episode 1.avi",
                "magnet": "magnet:?xt=urn:btih:GHI",
            },
            {
                "name": "Stream 4",
                "description": "Episode 1.txt\nSome size info",
                "magnet": "magnet:?xt=urn:btih:JKL",
            },
        ]
    }

    candidates = service.extract_download_candidates(payload)

    # Stream 2 (.srt) and Stream 4 (.txt) should be filtered out
    assert len(candidates) == 2
    assert candidates[0]["link"] == "magnet:?xt=urn:btih:ABC"
    assert candidates[1]["link"] == "magnet:?xt=urn:btih:GHI"


@pytest.mark.asyncio
async def test_stream_rewrite_marks_cached_stream_using_content_id_fallback_when_index_is_none():
    infohash = "abcdef1234567890abcdef1234567890abcdef12"
    magnet = f"magnet:?xt=urn:btih:{infohash}"
    fake_cache = FakeCacheManager(ready_contents={(infohash, "tt987:1:1")})
    service = StreamRewriteService("http://localhost:8691", fake_cache)
    payload = {
        "streams": [
            {
                "name": "Corsaro Viola 1080p",
                "title": "demo",
                "magnet": magnet,
                "fileIdx": None,
                "_meta": {"cached": False},
            }
        ]
    }

    rewritten = await service.rewrite(payload, category="tv", content_type="series", content_id="tt987:1:1")

    assert rewritten["streams"][0]["_meta"]["cached"] is True
    assert rewritten["streams"][0]["name"] == "🔥 Corsaro Viola 1080p"


@pytest.mark.asyncio
async def test_stream_rewrite_http_streams():
    service = StreamRewriteService(
        "http://localhost:8691",
        FakeCacheManager(),
    )
    http_video_url = "https://example.com/video.mp4"
    direct_hls_url = "https://example.com/manifest.m3u8"
    torrent_hash = "c" * 40

    payload = {
        "streams": [
            {
                "name": "Direct MP4",
                "url": http_video_url,
            },
            {
                "name": "Direct HLS",
                "url": direct_hls_url,
            },
            {
                "name": "Torrent Stream",
                "infoHash": torrent_hash,
            },
        ]
    }

    rewritten = await service.rewrite(payload, category="tv", content_id="tt3749900:1:1")

    assert rewritten["streams"][0]["url"].startswith("http://localhost:8691/play?")
    assert "link=" + urllib.parse.quote(http_video_url, safe="") in rewritten["streams"][0]["url"]

    assert rewritten["streams"][1]["url"].startswith("http://localhost:8691/play?")
    assert "link=" + urllib.parse.quote(direct_hls_url, safe="") in rewritten["streams"][1]["url"]

    assert "http://localhost:8691/play?" in rewritten["streams"][2]["url"]


@pytest.mark.asyncio
async def test_stream_rewrite_puts_cached_streams_at_the_top():
    cached_hash = "a" * 40
    other_hash = "b" * 40
    cache_manager = FakeCacheManager(ready_cache_keys={f"{cached_hash}:0"})

    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
    )

    payload = {
        "streams": [
            {"name": "Stream 1", "infoHash": other_hash, "title": "Other Torrent"},
            {"name": "Stream 2", "infoHash": cached_hash, "title": "Cached Torrent"},
            {"name": "Stream 3", "url": "https://example.com/stream.mp4", "title": "HTTP Stream"},
        ]
    }

    result = await service.rewrite(payload, category="tv", content_id="tt1234567:1:1")
    streams = result["streams"]

    # Stream 2 (the cached one) must now be at index 0
    assert "🔥" in streams[0]["name"]
    assert streams[0]["_meta"]["cached"] is True
    assert streams[0]["infoHash"] == cached_hash

    # Other streams retain their relative order
    assert streams[1]["infoHash"] == other_hash
    assert "link=https%3A%2F%2Fexample.com%2Fstream.mp4" in streams[2]["url"]
    assert streams[2]["url"].startswith("http://localhost:8691/play?")


def test_extract_download_candidates_extracts_seeders():
    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=FakeCacheManager(),
    )
    payload = {
        "streams": [
            {
                "name": "Stream 1",
                "description": "📄 File1.mkv\n💾 1.2 GB\n🌍 🇮🇹 | 👤 10 | ⏰",
                "infoHash": "a" * 40,
            },
            {
                "name": "Stream 2",
                "description": "📄 File2.mkv\n💾 500 MB\n🌍 🇮🇹 | 👤 0 | ⏰",
                "infoHash": "b" * 40,
            },
            {
                "name": "Stream 3",
                "description": "📄 File3.mkv\n💾 500 MB",
                "infoHash": "c" * 40,
            },
        ]
    }
    candidates = service.extract_download_candidates(payload)
    assert len(candidates) == 3
    assert candidates[0]["seeders"] == 10
    assert candidates[1]["seeders"] == 0
    assert candidates[2]["seeders"] is None


@pytest.mark.asyncio
async def test_rewrite_injects_cached_stream_when_missing_from_upstream():
    from stremio_http_proxy.model.cache_entry import CacheEntry as CacheEntryModel
    from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum

    hash1 = "a" * 40
    hash_other = "b" * 40
    cache_manager = MagicMock()
    cache_manager.build_cache_key.return_value = None
    cache_manager.get_ready_entry_by_content.return_value = None
    cache_manager.is_content_ready.return_value = False

    cached_entry = CacheEntryModel(
        cache_key=f"{hash1}:1",
        infohash=hash1,
        cache_index=1,
        status=CacheEntryStatusEnum.READY.value,
        title="Breaking.Bad.S01E01.1080p.mkv",
        source_link=f"magnet:?xt=urn:btih:{hash1}",
        file_path="/var/cache/hash1_1.mkv",
        tmp_path="/var/cache/hash1_1.tmp",
        size_bytes=2 * 1024 * 1024 * 1024,
    )
    cache_manager.get_ready_entries_by_content.return_value = [cached_entry]

    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
        cache_enabled=True,
    )

    upstream_payload = {
        "streams": [
            {
                "name": "Torrentio 720p",
                "title": "Breaking Bad S01E01 720p",
                "infoHash": hash_other,
                "fileIdx": 0,
            }
        ]
    }

    result = await service.rewrite(
        upstream_payload,
        category="tv",
        content_type="series",
        content_id="tt0903747:1:1",
    )

    streams = result.get("streams", [])
    assert len(streams) == 2
    first_stream = streams[0]
    assert first_stream["name"] == "🔥 [Cache Locale]"
    assert "Breaking.Bad.S01E01.1080p.mkv" in first_stream["title"]
    assert "2.00 GB" in first_stream["title"]
    assert first_stream["_meta"]["cached"] is True
    assert first_stream["_meta"]["infohash"] == hash1
    assert first_stream["_meta"]["cache_index"] == 1
    assert "link=magnet" in first_stream["url"]
    assert "index=1" in first_stream["url"]


@pytest.mark.asyncio
async def test_rewrite_does_not_duplicate_when_upstream_already_has_cached_stream():
    from stremio_http_proxy.model.cache_entry import CacheEntry as CacheEntryModel
    from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum

    hash1 = "a" * 40
    cache_manager = MagicMock()
    cache_manager.build_cache_key.return_value = f"{hash1}:1"
    cache_manager.is_ready.return_value = True
    cache_manager.parse_cache_key.return_value = (hash1, 1)

    cached_entry = CacheEntryModel(
        cache_key=f"{hash1}:1",
        infohash=hash1,
        cache_index=1,
        status=CacheEntryStatusEnum.READY.value,
        title="Breaking.Bad.S01E01.1080p.mkv",
        source_link=f"magnet:?xt=urn:btih:{hash1}",
        file_path="/var/cache/hash1_1.mkv",
        tmp_path="/var/cache/hash1_1.tmp",
        size_bytes=2 * 1024 * 1024 * 1024,
    )
    cache_manager.get_ready_entries_by_content.return_value = [cached_entry]

    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
        cache_enabled=True,
    )

    upstream_payload = {
        "streams": [
            {
                "name": "Torrentio 1080p",
                "title": "Breaking Bad S01E01 1080p",
                "infoHash": hash1,
                "fileIdx": 0,
            }
        ]
    }

    result = await service.rewrite(
        upstream_payload,
        category="tv",
        content_type="series",
        content_id="tt0903747:1:1",
    )

    streams = result.get("streams", [])
    assert len(streams) == 1
    assert streams[0]["name"] == "🔥 Torrentio 1080p"


@pytest.mark.asyncio
async def test_rewrite_empty_upstream_injects_cached_stream():
    from stremio_http_proxy.model.cache_entry import CacheEntry as CacheEntryModel
    from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum

    hash1 = "a" * 40
    cache_manager = MagicMock()
    cached_entry = CacheEntryModel(
        cache_key=f"{hash1}:0",
        infohash=hash1,
        cache_index=0,
        status=CacheEntryStatusEnum.READY.value,
        title="Movie.1080p.mkv",
        source_link=f"magnet:?xt=urn:btih:{hash1}",
        file_path="/var/cache/hash1_0.mkv",
        tmp_path="/var/cache/hash1_0.tmp",
        size_bytes=1024 * 1024 * 1024,
    )
    cache_manager.get_ready_entries_by_content.return_value = [cached_entry]

    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
        cache_enabled=True,
    )

    result = await service.rewrite(
        {"streams": []},
        category="movie",
        content_type="movie",
        content_id="tt0111161",
    )

    streams = result.get("streams", [])
    assert len(streams) == 1
    assert streams[0]["name"] == "🔥 [Cache Locale]"
    assert streams[0]["_meta"]["cached"] is True
    assert streams[0]["behaviorHints"]["notWebReady"] is False


@pytest.mark.asyncio
async def test_upstream_stream_marked_cached_updates_not_web_ready_to_false():
    cache_manager = MagicMock()
    torrent_hash = "d" * 40
    cache_manager.build_cache_key.return_value = f"{torrent_hash}:0"
    cache_manager.is_ready.return_value = True
    cache_manager.parse_cache_key.return_value = (torrent_hash, 0)

    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
        cache_enabled=True,
    )

    payload = {
        "streams": [
            {
                "name": "Corsaro 1080p",
                "infoHash": torrent_hash,
                "fileIdx": 0,
                "behaviorHints": {"notWebReady": True},
            }
        ]
    }

    result = await service.rewrite(payload, category="movie", content_type="movie", content_id="tt0111161")
    streams = result.get("streams", [])
    assert len(streams) == 1
    assert streams[0]["name"] == "🔥 Corsaro 1080p"
    assert streams[0]["_meta"]["cached"] is True
    assert streams[0]["behaviorHints"]["notWebReady"] is False


@pytest.mark.asyncio
async def test_upstream_stream_marked_cached_preserves_not_web_ready_when_target_is_mkv(tmp_path):
    cache_manager = MagicMock()
    torrent_hash = "d" * 40
    cache_manager.build_cache_key.return_value = f"{torrent_hash}:0"
    cache_manager.is_ready.return_value = True
    cache_manager.parse_cache_key.return_value = (torrent_hash, 0)

    # Simulate MKV file on disk
    mkv_file = tmp_path / "video.media"
    # Write MKV signature (EBML with matroska doctype)
    mkv_file.write_bytes(b"\x1a\x45\xdf\xa3\x93\x42\x82\x88matroska")
    cache_manager._media_path.return_value = mkv_file

    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
        cache_enabled=True,
        optimize_media_target="mkv",
    )

    payload = {
        "streams": [
            {
                "name": "Corsaro 1080p",
                "infoHash": torrent_hash,
                "fileIdx": 0,
                "behaviorHints": {"notWebReady": True},
            }
        ]
    }

    result = await service.rewrite(payload, category="movie", content_type="movie", content_id="tt0111161")
    streams = result.get("streams", [])
    assert len(streams) == 1
    assert streams[0]["name"] == "🔥 Corsaro 1080p"
    assert streams[0]["_meta"]["cached"] is True
    # For MKV under mkv target, notWebReady must stay True!
    assert streams[0]["behaviorHints"]["notWebReady"] is True


@pytest.mark.asyncio
async def test_synthetic_cached_stream_sets_not_web_ready_true_for_mkv_target(tmp_path):
    cache_manager = MagicMock()
    torrent_hash = "e" * 40

    mkv_file = tmp_path / "video.media"
    mkv_file.write_bytes(b"\x1a\x45\xdf\xa3\x93\x42\x82\x88matroska")
    cache_manager._media_path.return_value = mkv_file

    ready_entry = MagicMock()
    ready_entry.infohash = torrent_hash
    ready_entry.cache_index = 0
    ready_entry.title = "Matrix.mkv"
    ready_entry.poster = "http://example.com/poster.jpg"
    ready_entry.source_link = f"magnet:?xt=urn:btih:{torrent_hash}"
    ready_entry.size_bytes = 104857600
    cache_manager.get_ready_entries_by_content.return_value = [ready_entry]

    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
        cache_enabled=True,
        optimize_media_target="mkv",
    )

    payload = {"streams": []}
    result = await service.rewrite(
        payload,
        category="movie",
        content_type="movie",
        content_id="tt0133093",
    )

    streams = result.get("streams", [])
    assert len(streams) == 1
    assert streams[0]["name"] == "🔥 [Cache Locale]"
    assert streams[0]["_meta"]["cached"] is True
    assert streams[0]["behaviorHints"]["notWebReady"] is True



