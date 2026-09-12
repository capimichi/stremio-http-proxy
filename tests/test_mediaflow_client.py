import pytest
import respx
import httpx
from stremio_http_proxy.client.mediaflow_client import MediaflowClient


def test_mediaflow_client_resolve_endpoint():
    client = MediaflowClient("https://mediaflow.example.com", "secret", timeout_seconds=10)
    assert client.resolve_endpoint("https://toastflix.invalid/manifest.m3u8?d=abc") == "/proxy/hls/manifest.m3u8"
    assert client.resolve_endpoint("https://toastflix.invalid/video.mp4") == "/proxy/stream"
    assert client.resolve_endpoint("https://toastflix.invalid/manifest.m3u8?d=abc#video.mp4") == "/proxy/hls/manifest.m3u8"


def test_mediaflow_client_fix_mediaflow_url():
    client = MediaflowClient("https://mediaflow.example.com", "secret", timeout_seconds=10)
    original = "https://mediaflow.example.com/_token_12345/proxy/stream/Gotham%20S01E01.mp4"
    fixed = client.fix_mediaflow_url(original, destination_hint="https://toastflix.invalid/manifest.m3u8?d=abc")
    assert fixed == "https://mediaflow.example.com/_token_12345/proxy/hls/manifest.m3u8"


@pytest.mark.asyncio
@respx.mock
async def test_mediaflow_client_generate_proxy_url():
    client = MediaflowClient("https://mediaflow.example.com", "secret", timeout_seconds=10)
    respx.post("https://mediaflow.example.com/generate_urls").respond(
        status_code=200,
        json={"urls": ["https://mediaflow.example.com/_token_abcde/proxy/hls/manifest.m3u8"]},
    )
    url = await client.generate_proxy_url(
        "https://toastflix.invalid/clone/manifest.m3u8?d=123",
        request_headers={"Referer": "https://v.vidxgo.co/"},
    )
    assert url == "https://mediaflow.example.com/_token_abcde/proxy/hls/manifest.m3u8"
