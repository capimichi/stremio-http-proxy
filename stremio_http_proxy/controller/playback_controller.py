import asyncio
import os
import re

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.download_queue_service import DownloadQueueService
from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService


class PlaybackController:
    @inject
    def __init__(
        self,
        torrserver_client: TorrServerClient,
        cache_service: CacheService,
        download_queue_service: DownloadQueueService,
        next_episode_prefetch_service: NextEpisodePrefetchService,
        logger_factory: LoggerFactory,
    ):
        self.logger = logger_factory.get_logger("stremio_http_proxy.api", "api.log")
        self.torrserver_client = torrserver_client
        self.cache_service = cache_service
        self.download_queue_service = download_queue_service
        self.next_episode_prefetch_service = next_episode_prefetch_service
        self._in_flight_requests: set[tuple[str, int | None]] = set()
        self.router = APIRouter(tags=["Playback"])
        self.router.add_api_route("/play", self.play, methods=["GET"])

    async def play(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        index: int | None = None,
        content_type: str | None = None,
        content_id: str | None = None,
    ) -> RedirectResponse:
        if index is None and content_type == "series" and content_id:
            resolved_index = await self._resolve_series_index(link, content_id, title, poster, category)
            if resolved_index is not None:
                index = resolved_index
            else:
                index = 1

        self._schedule_initialization(link, title, poster, category, index)
        self._schedule_downloads(link, title, poster, category, index, content_type, content_id)

        cached_route = self.cache_service.get_cached_route(link, index)
        if cached_route is not None:
            return RedirectResponse(url=cached_route, status_code=307)

        return RedirectResponse(
            url=self.torrserver_client.build_play_url(link, title, poster, category, index),
            status_code=307,
        )

    def _schedule_downloads(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
        content_type: str | None,
        content_id: str | None,
    ) -> None:
        asyncio.create_task(
            self._enqueue_downloads_in_background(
                link,
                title,
                poster,
                category,
                index,
                content_type,
                content_id,
            )
        )

    def _schedule_initialization(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
    ) -> None:
        request_key = (link, index)
        if request_key in self._in_flight_requests:
            return

        self._in_flight_requests.add(request_key)
        task = asyncio.create_task(self._initialize_in_background(link, title, poster, category, index))
        task.add_done_callback(lambda _: self._in_flight_requests.discard(request_key))

    async def _initialize_in_background(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
    ) -> None:
        try:
            await self.torrserver_client.add_torrent(link, title, poster, category)
            await self.torrserver_client.preload(link, title, poster, category, index)
        except Exception:
            self.logger.exception("Unable to initialize TorrServer playback")

    async def _enqueue_downloads_in_background(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
        content_type: str | None,
        content_id: str | None,
    ) -> None:
        try:
            await self.download_queue_service.enqueue_download(
                link,
                title,
                poster,
                category,
                index,
                priority=100,
                trigger="playback",
                content_type=content_type,
                content_id=content_id,
            )
            await self.next_episode_prefetch_service.enqueue_next_episode(content_type, content_id, category)
        except Exception:
            self.logger.exception("Unable to enqueue cache download work")

    async def _resolve_series_index(
        self,
        link: str,
        content_id: str,
        title: str | None,
        poster: str | None,
        category: str | None,
    ) -> int | None:
        try:
            parts = content_id.split(":")
            if len(parts) < 3:
                return None
            season = int(parts[1])
            episode = int(parts[2])
        except (ValueError, IndexError):
            return None

        if not hasattr(self.torrserver_client, "add_and_get_status"):
            return None

        try:
            if hasattr(self.torrserver_client, "add_torrent"):
                await self.torrserver_client.add_torrent(link, title, poster, category)
        except Exception:
            pass

        file_stats = None
        for _ in range(6):
            try:
                res = await self.torrserver_client.add_and_get_status(link)
                if res and "file_stats" in res:
                    file_stats = res["file_stats"]
                    if file_stats:
                        break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if not file_stats:
            return None

        video_extensions = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".mpg", ".mpeg", ".ts", ".webm", ".flv"}
        video_files = [
            f for f in file_stats
            if os.path.splitext(f.get("path", "").lower())[1] in video_extensions
        ]
        if not video_files:
            return None

        pattern1 = re.compile(rf"[sS]0*{season}[^a-zA-Z0-9]*[eE]0*{episode}(?![0-9])")
        pattern2 = re.compile(rf"\b0*{season}[xX]0*{episode}(?![0-9])")
        pattern3 = re.compile(rf"\b(?:[eE]p?(?:isode)?[^a-zA-Z0-9]*|#\s*)0*{episode}(?![0-9])", re.IGNORECASE)
        pattern4 = re.compile(rf"\b0*{episode}(?![0-9])")
        season_pattern = re.compile(rf"\b[sS]eason[^0-9]*0*{season}\b|\b[sS]0*{season}\b", re.IGNORECASE)

        # 1. Match S01E02 or 1x02 on filename
        for f in video_files:
            path = f.get("path", "")
            filename = path.split("/")[-1]
            if pattern1.search(filename) or pattern2.search(filename):
                return f.get("id")

        # 2. Match Season 1/02.mkv or Season 1/Episode 2.mkv
        for f in video_files:
            path = f.get("path", "")
            filename = path.split("/")[-1]
            if season_pattern.search(path):
                if pattern3.search(filename) or pattern4.search(filename):
                    return f.get("id")

        # 3. Match S01E02 on entire path
        for f in video_files:
            path = f.get("path", "")
            if pattern1.search(path) or pattern2.search(path):
                return f.get("id")

        return None
