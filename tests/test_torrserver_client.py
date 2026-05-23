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


def test_check_stream_playable_returns_true_when_data_received():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/stream"
        assert request.url.params["link"] == "magnet:?xt=urn:btih:abc"
        assert request.url.params["play"] == "true"
        assert request.url.params["index"] == "3"
        return httpx.Response(200, content=b"\x00\x01\x02", request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient("http://localhost:8090", 20, transport=transport)

    result = asyncio.run(client.check_stream_playable("magnet:?xt=urn:btih:abc", index=3, timeout=15))

    assert result is True


def test_check_stream_playable_returns_false_on_http_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient("http://localhost:8090", 20, transport=transport)

    result = asyncio.run(client.check_stream_playable("magnet:?xt=urn:btih:abc", timeout=15))

    assert result is False


def test_check_stream_playable_returns_false_on_empty_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"", request=request)

    transport = httpx.MockTransport(handler)
    client = TorrServerClient("http://localhost:8090", 20, transport=transport)

    result = asyncio.run(client.check_stream_playable("magnet:?xt=urn:btih:abc", timeout=15))

    assert result is False


def test_check_stream_playable_returns_false_on_connection_error():
    client = TorrServerClient("http://localhost:1", 5)

    result = asyncio.run(client.check_stream_playable("magnet:?xt=urn:btih:abc", timeout=2))

    assert result is False


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
