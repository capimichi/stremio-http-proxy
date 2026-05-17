from urllib.parse import urlencode

import httpx
from injector import inject


class TorrServerClient:
    @inject
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int,
        basic_auth_user: str | None = None,
        basic_auth_password: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.auth = httpx.BasicAuth(basic_auth_user, basic_auth_password or "") if basic_auth_user else None
        self.transport = transport

    async def add_torrent(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
    ) -> dict:
        payload = {
            "action": "add",
            "link": link,
            "save_to_db": False,
        }
        payload.update(self._metadata(title, poster, category))
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            auth=self.auth,
            transport=self.transport,
        ) as client:
            response = await client.post("/torrents", json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}

    async def preload(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        index: int | None = None,
    ) -> None:
        params = {
            "link": link,
            "preload": "true",
        }
        params.update(self._metadata(title, poster, category))
        if index is not None:
            params["index"] = str(index)
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            auth=self.auth,
            transport=self.transport,
        ) as client:
            response = await client.get("/stream", params=params)
            response.raise_for_status()

    def build_play_url(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        index: int | None = None,
    ) -> str:
        params = {
            "link": link,
            "play": "true",
        }
        params.update(self._metadata(title, poster, category))
        if index is not None:
            params["index"] = str(index)
        return f"{self.base_url}/stream?{urlencode(params)}"

    def _metadata(
        self,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
    ) -> dict[str, str]:
        metadata: dict[str, str] = {}
        if title:
            metadata["title"] = title
        if poster:
            metadata["poster"] = poster
        if category:
            metadata["category"] = category
        return metadata
