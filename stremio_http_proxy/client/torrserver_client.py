import asyncio
import os
import re
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
        internal_base_url: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.internal_base_url = (internal_base_url or base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.auth = httpx.BasicAuth(basic_auth_user, basic_auth_password or "") if basic_auth_user else None
        self.transport = transport

    async def add_and_get_status(self, link: str, timeout: float | None = None) -> dict | None:
        payload = {"action": "add", "link": link, "save_to_db": False}
        try:
            async with httpx.AsyncClient(
                base_url=self.internal_base_url,
                timeout=timeout or self.timeout_seconds,
                auth=self.auth,
                transport=self.transport,
            ) as client:
                response = await client.post("/torrents", json=payload)
                if response.status_code >= 400:
                    return None
                return response.json() if response.content else {}
        except Exception:
            return None

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
            base_url=self.internal_base_url,
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
        if index is not None and index > 0:
            params["index"] = str(index)
        async with httpx.AsyncClient(
            base_url=self.internal_base_url,
            timeout=self.timeout_seconds,
            auth=self.auth,
            transport=self.transport,
        ) as client:
            response = await client.get("/stream", params=params)
            response.raise_for_status()

    def build_download_url(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        index: int | None = None,
    ) -> str:
        return self._build_stream_url(self.internal_base_url, link, title, poster, category, index)

    def build_play_url(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        index: int | None = None,
    ) -> str:
        return self._build_stream_url(self.base_url, link, title, poster, category, index)

    def _build_stream_url(
        self,
        base_url: str,
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
        if index is not None and index > 0:
            params["index"] = str(index)
        return f"{base_url}/stream?{urlencode(params)}"

    async def resolve_file_index(
        self,
        link: str,
        content_id: str | None = None,
        content_type: str | None = None,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        max_attempts: int = 6,
        poll_interval: float = 0.5,
    ) -> int:
        try:
            await self.add_torrent(link, title, poster, category)
        except Exception:
            pass

        file_stats = None
        for _ in range(max_attempts):
            try:
                res = await self.add_and_get_status(link)
                if res and "file_stats" in res:
                    file_stats = res["file_stats"]
                    if file_stats:
                        break
            except Exception:
                pass
            await asyncio.sleep(poll_interval)

        if not file_stats:
            return 1

        video_extensions = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".mpg", ".mpeg", ".ts", ".webm", ".flv"}
        video_files = [
            f for f in file_stats
            if os.path.splitext(f.get("path", "").lower())[1] in video_extensions
        ]
        if not video_files:
            return 1

        if len(video_files) == 1:
            return int(video_files[0].get("id", 1))

        season = None
        episode = None
        if content_id and (content_type == "series" or ":" in content_id):
            parts = content_id.split(":")
            if len(parts) >= 3:
                try:
                    season = int(parts[1])
                    episode = int(parts[2])
                except (ValueError, IndexError):
                    pass

            pattern1 = re.compile(rf"[sS]0*{season}[^a-zA-Z0-9]*[eE]0*{episode}(?![0-9])")
            pattern2 = re.compile(rf"\b0*{season}[xX]0*{episode}(?![0-9])")
            pattern3 = re.compile(rf"\b(?:[eE]p?(?:isode)?[^a-zA-Z0-9]*|#\s*)0*{episode}(?![0-9])", re.IGNORECASE)
            pattern_ep_start = re.compile(rf"^0*{episode}(?![0-9])")
            pattern4 = re.compile(rf"\b0*{episode}(?![0-9])")
            season_folder_pattern = re.compile(
                rf"\b(?:season|stagion[ei]|saison|staffel|temporada|series)[\s._]*0*{season}(?!\s*[-~–—/]\s*[sS]?\d+)\b|\b[sS]0*{season}(?!\s*[-~–—/]\s*[sS]?\d+)\b",
                re.IGNORECASE,
            )

            # 1. Match S01E02 or 1x02 on filename
            for f in video_files:
                path = f.get("path", "")
                filename = path.split("/")[-1]
                if pattern1.search(filename) or pattern2.search(filename):
                    return int(f.get("id", 1))

            # 2. Match season folder in path + episode in filename
            for f in video_files:
                path = f.get("path", "")
                filename = path.split("/")[-1]
                dir_parts = path.split("/")[:-1]
                if any(season_folder_pattern.search(d) for d in dir_parts):
                    if pattern3.search(filename) or pattern_ep_start.search(filename):
                        return int(f.get("id", 1))

            for f in video_files:
                path = f.get("path", "")
                filename = path.split("/")[-1]
                dir_parts = path.split("/")[:-1]
                if any(season_folder_pattern.search(d) for d in dir_parts):
                    if pattern4.search(filename):
                        return int(f.get("id", 1))

            # 3. Match S01E02 on entire path
            for f in video_files:
                path = f.get("path", "")
                if pattern1.search(path) or pattern2.search(path):
                    return int(f.get("id", 1))

        return int(video_files[0].get("id", 1))

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
