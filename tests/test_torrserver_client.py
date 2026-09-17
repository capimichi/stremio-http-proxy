import asyncio
import base64

import httpx

from stremio_http_proxy.client.torrserver_client import TorrServerClient


async def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "POST" and request.url.path == "/torrents":
        payload = await request.aread()
        return httpx.Response(200, content=payload, request=request)
    if request.method == "GET" and request.url.path == "/stream":
        return httpx.Response(200, request=request)
    return httpx.Response(404, request=request)


def test_add_and_get_status_returns_none_on_http_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient("http://localhost:8090", 20, transport=transport)

    result = asyncio.run(client.add_and_get_status("magnet:?xt=urn:btih:abc", timeout=15))

    assert result is None


def test_add_and_get_status_returns_none_on_connection_error():
    client = TorrServerClient("http://localhost:1", 5)

    result = asyncio.run(client.add_and_get_status("magnet:?xt=urn:btih:abc", timeout=2))

    assert result is None


def test_add_torrent_posts_expected_payload():
    transport = httpx.MockTransport(_handler)
    client = TorrServerClient("http://localhost:8090", 20, transport=transport)

    response = asyncio.run(
        client.add_torrent(
            "magnet:?xt=urn:btih:abc",
            title="Demo",
            poster="https://image.invalid/poster.jpg",
            category="movie",
        )
    )

    assert response["action"] == "add"
    assert response["link"] == "magnet:?xt=urn:btih:abc"
    assert response["title"] == "Demo"
    assert response["poster"] == "https://image.invalid/poster.jpg"
    assert response["category"] == "movie"
    assert response["save_to_db"] is False


def test_preload_hits_stream_endpoint_with_preload_flag():
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient("http://localhost:8090", 20, transport=transport)

    asyncio.run(client.preload("abc123", title="Demo", category="tv", index=18))

    assert captured["link"] == "abc123"
    assert captured["preload"] == "true"
    assert captured["title"] == "Demo"
    assert captured["category"] == "tv"
    assert captured["index"] == "18"


def test_build_play_url_uses_torrserver_stream_endpoint():
    client = TorrServerClient("http://localhost:8090", 20)

    url = client.build_play_url("magnet:?xt=urn:btih:abc", title="Demo", category="movie", index=18)

    assert url.startswith("http://localhost:8090/stream?")
    assert "play=true" in url
    assert "title=Demo" in url
    assert "category=movie" in url
    assert "index=18" in url


def test_add_torrent_uses_basic_auth_when_configured():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={}, request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient(
        "http://localhost:8090",
        20,
        basic_auth_user="demo",
        basic_auth_password="secret",
        transport=transport,
    )

    asyncio.run(client.add_torrent("magnet:?xt=urn:btih:abc"))

    expected = "Basic " + base64.b64encode(b"demo:secret").decode()
    assert captured["authorization"] == expected


def test_torrserver_client_uses_internal_base_url_for_api_and_download_url():
    captured_requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(str(request.url))
        return httpx.Response(200, json={}, request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient(
        "https://torrserver.example.com",
        20,
        transport=transport,
        internal_base_url="http://torrserver:8090",
    )

    # Public play URL uses base_url
    play_url = client.build_play_url("magnet:?xt=urn:btih:abc", title="Demo", index=1)
    assert play_url.startswith("https://torrserver.example.com/stream?")

    # Internal download URL uses internal_base_url
    download_url = client.build_download_url("magnet:?xt=urn:btih:abc", title="Demo", index=1)
    assert download_url.startswith("http://torrserver:8090/stream?")

    # API calls use internal_base_url
    asyncio.run(client.add_torrent("magnet:?xt=urn:btih:abc"))
    asyncio.run(client.preload("magnet:?xt=urn:btih:abc", index=1))
    asyncio.run(client.add_and_get_status("magnet:?xt=urn:btih:abc"))

    assert captured_requests[0].startswith("http://torrserver:8090/torrents")
    assert captured_requests[1].startswith("http://torrserver:8090/stream")
    assert captured_requests[2].startswith("http://torrserver:8090/torrents")


def test_build_stream_url_ignores_zero_or_negative_index():
    client = TorrServerClient("http://localhost:8090", 20)

    url_zero = client.build_play_url("magnet:?xt=urn:btih:abc", index=0)
    assert "index=" not in url_zero

    url_positive = client.build_play_url("magnet:?xt=urn:btih:abc", index=5)
    assert "index=5" in url_positive


def test_resolve_file_index_matches_series_episode():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "file_stats": [
                        {"id": 1, "path": "Season 1/Gotham.S01E01.mkv"},
                        {"id": 6, "path": "Season 1/Gotham.S01E06.Lo.Spirito.mkv"},
                        {"id": 7, "path": "Season 1/Gotham.S01E06.srt"},
                    ]
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient("http://localhost:8090", 20, transport=transport)

    idx = asyncio.run(
        client.resolve_file_index(
            "magnet:?xt=urn:btih:abc",
            content_id="tt3749900:1:6",
            content_type="series",
        )
    )
    assert idx == 6


def test_resolve_file_index_single_video_file():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "file_stats": [
                        {"id": 1, "path": "SingleMovie.mkv"},
                        {"id": 2, "path": "Subtitles.srt"},
                    ]
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient("http://localhost:8090", 20, transport=transport)

    idx = asyncio.run(client.resolve_file_index("magnet:?xt=urn:btih:abc"))
    assert idx == 1

