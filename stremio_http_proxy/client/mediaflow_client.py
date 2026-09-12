import re
from urllib.parse import urlparse
import httpx
from injector import inject


class MediaflowClient:
    @inject
    def __init__(
        self,
        base_url: str | None = None,
        api_password: str | None = None,
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

        is_hls = False
        if destination_hint and self.resolve_endpoint(destination_hint) == "/proxy/hls/manifest.m3u8":
            is_hls = True
        elif ".m3u8" in url:
            is_hls = True

        if is_hls and "/proxy/stream" in url:
            return re.sub(r"/proxy/stream/?[^?#]*", "/proxy/hls/manifest.m3u8", url)
        if "/proxy/hls/manifest.m3u8/" in url:
            return re.sub(r"/proxy/hls/manifest\.m3u8/?[^?#]*", "/proxy/hls/manifest.m3u8", url)
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
        # MediaFlow appends /<filename> to endpoint. For /proxy/hls/manifest.m3u8 this results in 404.
        clean_filename = filename if endpoint != "/proxy/hls/manifest.m3u8" else None
        payload = {
            "mediaflow_proxy_url": self.base_url,
            "api_password": self.api_password,
            "urls": [
                {
                    "endpoint": endpoint,
                    "destination_url": destination_url,
                    "request_headers": request_headers or {},
                    "response_headers": response_headers or {},
                    "filename": clean_filename,
                }
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            res = await client.post(f"{self.base_url}/generate_urls", json=payload)
            res.raise_for_status()
            data = res.json()
            urls = data.get("urls", [])
            if urls:
                return self.fix_mediaflow_url(urls[0])
            return destination_url
