from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class FakeCacheManager:
    def __init__(self, ready_cache_keys: set[str] | None = None):
        self.ready_cache_keys = ready_cache_keys or set()

    def build_cache_key(self, link: str, index: int | None = None) -> str:
        return f"{link}:{index or 0}"

    def is_ready(self, cache_key: str) -> bool:
        return cache_key in self.ready_cache_keys


def test_stream_rewrite_uses_local_playback_url_for_torrent_streams():
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

    rewritten = service.rewrite(payload, category="movie")

    assert rewritten["streams"][0]["url"] == (
        "http://localhost:8691/play?"
        "link=magnet%3A%3Fxt%3Durn%3Abtih%3AABCDEF1234567890ABCDEF1234567890ABCDEF12"
        "&title=demo&category=movie&index=18"
    )


def test_stream_rewrite_leaves_non_torrent_streams_unchanged():
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager())
    payload = {"streams": [{"title": "demo", "url": "https://upstream.invalid/video.mp4"}]}

    rewritten = service.rewrite(payload, category="movie")

    assert rewritten == payload


def test_stream_rewrite_includes_content_context_for_episode_prefetch():
    service = StreamRewriteService("http://localhost:8691", FakeCacheManager())
    payload = {
        "streams": [
            {
                "title": "demo",
                "magnet": "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
            }
        ]
    }

    rewritten = service.rewrite(payload, category="tv", content_type="series", content_id="tt123:1:2")

    assert "content_type=series" in rewritten["streams"][0]["url"]
    assert "content_id=tt123%3A1%3A2" in rewritten["streams"][0]["url"]


def test_stream_rewrite_marks_cached_streams_when_local_cache_is_ready():
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

    rewritten = service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["_meta"]["cached"] is True
    assert rewritten["streams"][0]["name"] == "🔥 Torrentio 1080p"


def test_stream_rewrite_does_not_duplicate_cached_name_prefix():
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

    rewritten = service.rewrite(payload, category="tv")

    assert rewritten["streams"][0]["name"] == "🔥 Torrentio 1080p"
