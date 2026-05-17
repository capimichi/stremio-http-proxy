from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


def test_stream_rewrite_uses_local_playback_url_for_torrent_streams():
    service = StreamRewriteService("http://localhost:8459")
    payload = {
        "streams": [
            {
                "title": "demo",
                "magnet": "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
                "url": "https://upstream.invalid/old",
            }
        ]
    }

    rewritten = service.rewrite(payload, category="movie")

    assert rewritten["streams"][0]["url"] == (
        "http://localhost:8459/play?"
        "link=magnet%3A%3Fxt%3Durn%3Abtih%3AABCDEF1234567890ABCDEF1234567890ABCDEF12"
        "&title=demo&category=movie"
    )


def test_stream_rewrite_leaves_non_torrent_streams_unchanged():
    service = StreamRewriteService("http://localhost:8459")
    payload = {"streams": [{"title": "demo", "url": "https://upstream.invalid/video.mp4"}]}

    rewritten = service.rewrite(payload, category="movie")

    assert rewritten == payload
