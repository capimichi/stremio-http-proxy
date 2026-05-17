from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


def test_stream_rewrite_uses_local_playlist_url():
    service = StreamRewriteService("http://localhost:8459")
    payload = {
        "streams": [
            {
                "title": "demo",
                "infoHash": "ABCDEF1234567890ABCDEF1234567890ABCDEF12",
                "url": "https://upstream.invalid/old",
            }
        ]
    }

    rewritten = service.rewrite(payload)

    assert (
        rewritten["streams"][0]["url"]
        == "http://localhost:8459/streams/abcdef1234567890abcdef1234567890abcdef12/playlist.m3u8"
    )
