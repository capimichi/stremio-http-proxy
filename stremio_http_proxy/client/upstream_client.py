from urllib.parse import urljoin

import httpx
from injector import inject


class UpstreamClient:
    @inject
    def __init__(self, base_url: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_seconds = timeout_seconds

    async def get_json(self, path: str, query_params: dict[str, str] | None = None) -> dict:
        url = urljoin(self.base_url, path.lstrip("/"))
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=query_params)
            response.raise_for_status()
            return response.json()
