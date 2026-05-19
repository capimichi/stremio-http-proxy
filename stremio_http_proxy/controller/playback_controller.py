import asyncio

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.service.cache_manager import CacheManager
from stremio_http_proxy.service.download_queue_service import DownloadQueueService
from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService


class PlaybackController:
    @inject
    def __init__(
        self,
        torrserver_client: TorrServerClient,
        cache_manager: CacheManager,
        download_queue_service: DownloadQueueService,
        next_episode_prefetch_service: NextEpisodePrefetchService,
        logger_factory: LoggerFactory,
    ):
        self.logger = logger_factory.get_logger("stremio_http_proxy.api", "api.log")
        self.torrserver_client = torrserver_client
        self.cache_manager = cache_manager
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
        cache_key = self.cache_manager.build_cache_key(link, index)
        self._schedule_initialization(link, title, poster, category, index)
        self._schedule_downloads(link, title, poster, category, index, content_type, content_id)

        if cache_key and self.cache_manager.is_ready(cache_key):
            infohash, cache_index = self.cache_manager.parse_cache_key(cache_key)
            return RedirectResponse(url=f"/cache/{infohash}/{cache_index}", status_code=307)

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
