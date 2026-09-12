# MediaFlow Proxy & HTTP Stream Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable `stremio-http-proxy` to configure MediaFlow Proxy credentials, dynamically generate and rewrite appropriate MediaFlow URLs (`/proxy/hls` for HLS manifests vs `/proxy/stream` for direct files) based on upstream stream types, serve streams immediately to Stremio, and seamlessly cache them locally on disk for future instant playback.

**Architecture:** A new `MediaflowClient` handles communication with MediaFlow Proxy (calling `/generate_urls` or formatting signed URLs with the correct endpoint). `StreamRewriteService` checks incoming streams from upstream (such as Toastflix): if it's an HLS or direct stream, it generates/fixes the MediaFlow URL with the proper endpoint. For playback and caching, `CacheManager` generates deterministic keys for HTTP streams, `PlaybackController` immediately redirects (307) un-cached streams to the live MediaFlow URL for instant streaming while enqueueing a background download, and `DownloadWorkerService` downloads the stream to disk and marks it ready. Subsequent playback requests serve the local file from disk with the `🔥` badge.

**Tech Stack:** Python 3.12, FastAPI, Injector (DI), HTTPX, Pydantic, SQLAlchemy, SQLite, FFmpeg / HLS parser.

## Global Constraints

- Never break existing TorrServer or torrent playback and caching functionality.
- Follow existing dependency injection patterns using `@inject` and `DefaultContainer`.
- All tests must use `pytest` with `pytest-asyncio` / `respx` where external HTTP calls are simulated.
- Maintain existing codebase style, type hints, and docstrings.

---

### Task 1: Environment Variables & Container Bindings for MediaFlow

**Files:**
- Modify: `stremio_http_proxy/container/default_container.py:53-176`
- Create: `tests/test_mediaflow_config.py`

**Interfaces:**
- Produces:
  - `DefaultContainer.mediaflow_base_url: str | None`
  - `DefaultContainer.mediaflow_api_password: str | None`
  - `DefaultContainer.mediaflow_enabled: bool`

- [x] **Step 1: Write the failing test for MediaFlow container settings**

```python
# tests/test_mediaflow_config.py
import os
import pytest
from unittest.mock import patch
from stremio_http_proxy.container.default_container import DefaultContainer


def test_default_container_initializes_mediaflow_env():
    env = {
        "APP_SECRET": "testsecret123",
        "MEDIAFLOW_BASE_URL": "https://mediaflow.example.com",
        "MEDIAFLOW_API_PASSWORD": "mypassword123",
        "MEDIAFLOW_ENABLED": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        DefaultContainer.instance = None
        container = DefaultContainer()
        assert container.get_var("mediaflow_base_url") == "https://mediaflow.example.com"
        assert container.get_var("mediaflow_api_password") == "mypassword123"
        assert container.get_var("mediaflow_enabled") is True
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mediaflow_config.py -v`
Expected: FAIL with AttributeError or missing attribute on `DefaultContainer`.

- [x] **Step 3: Add MediaFlow configuration to DefaultContainer**

In `stremio_http_proxy/container/default_container.py`:
In `_init_variables`:
```python
self.mediaflow_base_url = os.environ.get("MEDIAFLOW_BASE_URL", "").rstrip("/")
self.mediaflow_api_password = os.environ.get("MEDIAFLOW_API_PASSWORD")
self.mediaflow_enabled = (
    os.environ.get("MEDIAFLOW_ENABLED", "true").lower() == "true"
    and bool(self.mediaflow_base_url)
)
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mediaflow_config.py -v`
Expected: PASS

---

### Task 2: MediaflowClient Implementation

**Files:**
- Create: `stremio_http_proxy/client/mediaflow_client.py`
- Test: `tests/test_mediaflow_client.py`
- Modify: `stremio_http_proxy/container/default_container.py`

**Interfaces:**
- Produces:
  - `MediaflowClient.is_available() -> bool`
  - `MediaflowClient.resolve_endpoint(destination_url: str) -> str`: returns `"/proxy/hls/manifest.m3u8"` if destination is an HLS playlist (contains `.m3u8`), else `"/proxy/stream"`
  - `MediaflowClient.generate_proxy_url(destination_url: str, request_headers: dict | None = None, filename: str | None = None) -> str`
  - `MediaflowClient.fix_mediaflow_url(url: str, destination_hint: str | None = None) -> str`: if URL points to MediaFlow with `/proxy/stream/...` but the underlying stream is HLS (`.m3u8`), replaces the path with `/proxy/hls/manifest.m3u8`.

- [x] **Step 1: Write tests for MediaflowClient**

```python
# tests/test_mediaflow_client.py
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mediaflow_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stremio_http_proxy.client.mediaflow_client'`.

- [x] **Step 3: Implement MediaflowClient**

Create `stremio_http_proxy/client/mediaflow_client.py`:
```python
import re
from urllib.parse import urlparse
import httpx
from injector import inject


class MediaflowClient:
    @inject
    def __init__(
        self,
        base_url: str | None,
        api_password: str | None,
        timeout_seconds: int = 15,
        enabled: bool = True,
    ):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_password = api_password
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled and bool(self.base_url)

    def is_available(self) -> bool:
        return self.enabled and bool(self.base_url)

    def resolve_endpoint(self, destination_url: str) -> str:
        # If destination contains .m3u8 anywhere in the path or query, it is HLS
        parsed = urlparse(destination_url)
        if ".m3u8" in parsed.path or ".m3u8" in parsed.query:
            return "/proxy/hls/manifest.m3u8"
        return "/proxy/stream"

    def is_mediaflow_url(self, url: str) -> bool:
        if not url:
            return False
        if self.base_url and url.startswith(self.base_url):
            return True
        return "/proxy/stream" in url or "/proxy/hls" in url

    def fix_mediaflow_url(self, url: str, destination_hint: str | None = None) -> str:
        """Fixes MediaFlow URLs that mistakenly use /proxy/stream for HLS playlists."""
        if not self.is_mediaflow_url(url):
            return url
        # If destination_hint is provided and is HLS, or if the URL or hint has .m3u8
        is_hls = False
        if destination_hint and self.resolve_endpoint(destination_hint) == "/proxy/hls/manifest.m3u8":
            is_hls = True
        elif ".m3u8" in url:
            is_hls = True

        if is_hls and "/proxy/stream" in url:
            # Replace /proxy/stream/... with /proxy/hls/manifest.m3u8
            return re.sub(r"/proxy/stream/?[^?#]*", "/proxy/hls/manifest.m3u8", url)
        return url

    async def generate_proxy_url(
        self,
        destination_url: str,
        request_headers: dict[str, str] | None = None,
        response_headers: dict[str, str] | None = None,
        filename: str | None = None,
    ) -> str:
        if not self.is_available():
            return destination_url

        endpoint = self.resolve_endpoint(destination_url)
        payload = {
            "mediaflow_proxy_url": self.base_url,
            "api_password": self.api_password,
            "urls": [
                {
                    "endpoint": endpoint,
                    "destination_url": destination_url,
                    "request_headers": request_headers or {},
                    "response_headers": response_headers or {},
                    "filename": filename,
                }
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            res = await client.post(f"{self.base_url}/generate_urls", json=payload)
            res.raise_for_status()
            data = res.json()
            urls = data.get("urls", [])
            if urls:
                return urls[0]
            return destination_url
```

- [x] **Step 4: Bind MediaflowClient in DefaultContainer**

In `stremio_http_proxy/container/default_container.py`:
Bind `MediaflowClient` and pass it to `StreamRewriteService`.

- [x] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_mediaflow_client.py -v`
Expected: PASS

---

### Task 3: StreamRewriteService Smart MediaFlow & HTTP Proxying

**Files:**
- Modify: `stremio_http_proxy/service/stream_rewrite_service.py`
- Test: `tests/test_stream_rewrite_service.py`

**Interfaces:**
- Consumes: `MediaflowClient`
- Produces:
  - `StreamRewriteService.rewrite(payload, ...)`:
    - If a stream is a torrent: keeps existing `/play?link=...` behavior.
    - If a stream is already a MediaFlow stream: checks and fixes `/proxy/stream` $\rightarrow$ `/proxy/hls/manifest.m3u8` if it wraps an M3U8.
    - If a stream has a direct URL + `behaviorHints.proxyHeaders` (e.g. Toastflix direct) and MediaFlow is configured: wraps it via `mediaflow_client.generate_proxy_url(...)`.
    - Preserves streams even if whitelist is present (or checks HTTP whitelist).

- [x] **Step 1: Write tests for StreamRewriteService MediaFlow handling**

```python
# In tests/test_stream_rewrite_service.py
@pytest.mark.asyncio
async def test_stream_rewrite_fixes_misconfigured_mediaflow_hls_stream():
    mediaflow_client = MediaflowClient("https://mediaflow.example.com", "secret")
    service = StreamRewriteService(
        "http://localhost:8691",
        FakeCacheManager(),
        mediaflow_client=mediaflow_client,
    )
    payload = {
        "streams": [
            {
                "name": "Toastflix 720p",
                "url": "https://mediaflow.example.com/_token_123/proxy/stream/Gotham.mp4",
                "description": "manifest.m3u8 stream",
                "behaviorHints": {"filename": "Gotham.m3u8"},
            }
        ]
    }
    rewritten = await service.rewrite(payload, category="tv", content_id="tt3749900:1:1")
    assert rewritten["streams"][0]["url"] == "https://mediaflow.example.com/_token_123/proxy/hls/manifest.m3u8"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stream_rewrite_service.py -k test_stream_rewrite_fixes_misconfigured_mediaflow_hls_stream -v`
Expected: FAIL

- [x] **Step 3: Update StreamRewriteService with MediaflowClient**

Inject `mediaflow_client: MediaflowClient | None = None` into `StreamRewriteService.__init__`.
In `rewrite()`:
1. When iterating over streams:
   - If `stream.get("url")`:
     - Fix MediaFlow URLs if already proxied via MediaFlow.
     - If direct URL with `proxyHeaders` and MediaFlow is available, convert to MediaFlow URL.
     - Check if HTTP stream is cached locally (`cache_manager.is_ready(http_cache_key)`). If ready, mark with `🔥` and rewrite URL to local cached route.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stream_rewrite_service.py -v`
Expected: PASS

---

### Task 4: CacheManager Support for Deterministic HTTP Cache Keys

**Files:**
- Modify: `stremio_http_proxy/manager/cache_manager.py`
- Modify: `stremio_http_proxy/helper/hash_helper.py`
- Test: `tests/test_cache_manager.py`

**Interfaces:**
- Produces:
  - `build_http_cache_key(url: str, content_id: str | None = None) -> str`: produces a 40-char SHA-1 hash prefixed by `http_` or standard hex suitable for SQLite and disk filenames.
  - `CacheManager.build_cache_key(link: str, index: int | None = None, content_id: str | None = None) -> str | None`: returns torrent cache key if torrent, or HTTP cache key if HTTP URL.

- [x] **Step 1: Write tests for HTTP cache key generation in CacheManager**

```python
# In tests/test_cache_manager.py
def test_build_cache_key_supports_http_urls(tmp_path):
    manager = build_manager(tmp_path)
    url = "https://toastflix.invalid/clone/manifest.m3u8?d=123"
    key = manager.build_cache_key(url, content_id="tt3749900:1:1")
    assert key is not None
    assert ":" in key
    # Key must be alphanumeric with standard separator
    prefix, idx = key.split(":", 1)
    assert len(prefix) == 40
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cache_manager.py -k test_build_cache_key_supports_http_urls -v`
Expected: FAIL (currently returns None for HTTP URLs).

- [x] **Step 3: Implement HTTP cache key generation**

In `stremio_http_proxy/helper/hash_helper.py`:
Add helper `hash_url(url: str) -> str` using hashlib.sha1.
In `CacheManager.build_cache_key`:
```python
if link.startswith(("http://", "https://")):
    return f"{hash_url(link)}:{index or 0}"
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cache_manager.py -v`
Expected: PASS

---

### Task 5: PlaybackController & Background Enqueueing for HTTP Streams

**Files:**
- Modify: `stremio_http_proxy/controller/playback_controller.py`
- Test: `tests/test_playback_controller.py`

**Interfaces:**
- Produces:
  - `PlaybackController.play(link, ...)`:
    - If `link` is an HTTP/HTTPS stream (non-torrent):
      - If cached on disk: redirects (307) to cached file route.
      - If not cached: triggers background caching job (`download_queue_service.enqueue_download`) and immediately returns RedirectResponse (307) to the live HTTP stream (MediaFlow URL) so Stremio plays instantly!

- [x] **Step 1: Write test for PlaybackController HTTP live stream redirect**

```python
# In tests/test_playback_controller.py
@pytest.mark.asyncio
async def test_playback_controller_redirects_http_stream_immediately_and_enqueues(client, mock_services):
    http_link = "https://mediaflow.example.com/_token_123/proxy/hls/manifest.m3u8"
    response = await client.get(
        "/play",
        params={"link": http_link, "title": "Gotham S01E01", "content_type": "series", "content_id": "tt3749900:1:1"},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == http_link
    # Verify download was enqueued
    mock_services.download_queue_service.enqueue_download.assert_called_once()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playback_controller.py -k test_playback_controller_redirects_http_stream_immediately_and_enqueues -v`
Expected: FAIL

- [x] **Step 3: Update PlaybackController to handle HTTP streams**

In `PlaybackController.play`:
Check if `link.startswith(("http://", "https://"))`:
- If so, bypass TorrServer initialization.
- Enqueue download job in background.
- If cached: redirect to cached route.
- If not cached: redirect (307) directly to `link`!

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_playback_controller.py -v`
Expected: PASS

---

### Task 6: DownloadWorkerService HTTP & HLS Stream Downloader

**Files:**
- Modify: `stremio_http_proxy/service/download_worker_service.py`
- Modify: `Dockerfile` (install `ffmpeg`)
- Test: `tests/test_download_worker_service.py`

**Interfaces:**
- Produces:
  - `DownloadWorkerService._download(job)`:
    - If `job.link` is a torrent: uses TorrServer client (existing logic).
    - If `job.link` is an HTTP stream:
      - If HLS (`.m3u8` or MediaFlow HLS): invokes `ffmpeg -y -i <url> -c copy -bsf:a aac_adtstoasc <tmp_path>` asynchronously, logging progress and saving as a single `.mp4` file.
      - If direct MP4: streams via `httpx` and writes to disk.

- [x] **Step 1: Write test for DownloadWorkerService downloading HTTP stream**

```python
# In tests/test_download_worker_service.py
@pytest.mark.asyncio
async def test_worker_downloads_http_stream(worker_service, mock_cache_manager):
    job = DownloadJob(
        job_id="job123",
        cache_key="http_abc:0",
        link="https://mediaflow.example.com/stream.mp4",
        title="Test Video",
    )
    # Mock httpx download
    # Verify download succeeds and acknowledges job
```

- [x] **Step 2: Implement HTTP/HLS downloading in DownloadWorkerService**

Add `_download_http_stream` method supporting both direct MP4 downloads via HTTP and HLS downloads via `ffmpeg`.

- [x] **Step 3: Update Dockerfile to include ffmpeg**

In `Dockerfile`:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_download_worker_service.py -v`
Expected: PASS

---

### Task 7: Verification & End-to-End Test for Gotham S01E01

**Files:**
- Test: `tests/test_e2e_toastflix_mediaflow.py`

- [x] **Step 1: Write E2E test verifying Gotham S01E01 Toastflix flow**

Simulate upstream returning Toastflix stream:
1. Verify `StreamRewriteService` produces proper `/proxy/hls/manifest.m3u8` URL.
2. Verify `/play` immediately redirects to MediaFlow live stream and starts streaming.
3. Verify background worker marks the entry `READY`.
4. Verify subsequent request to `/stream` returns the `🔥` cached URL.

- [x] **Step 2: Run all tests**

Run: `pytest`
Expected: 100% tests passing.
