import asyncio
import os
from typing import Any
import urllib.parse

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.helper.hash_helper import extract_infohash
from stremio_http_proxy.repository.playback_history_repository import PlaybackHistoryRepository
from stremio_http_proxy.service.download_queue_service import DownloadQueueService
from stremio_http_proxy.service.media_metadata_service import MediaMetadataService
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
        playback_history_repository: PlaybackHistoryRepository | None = None,
        media_metadata_service: MediaMetadataService | None = None,
    ):
        self.logger = logger_factory.get_logger("stremio_http_proxy.api", "api.log")
        self.torrserver_client = torrserver_client
        self.cache_service = cache_service
        self.download_queue_service = download_queue_service
        self.next_episode_prefetch_service = next_episode_prefetch_service
        self.playback_history_repository = playback_history_repository
        self.media_metadata_service = media_metadata_service
        self._in_flight_requests: set[tuple[str, int | None]] = set()
        self.router = APIRouter(tags=["Playback"])
        self.router.add_api_route("/play", self.play, methods=["GET", "HEAD"])



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
        self._record_playback(link, title, poster, category, index, content_type, content_id)
        cached_route = self._get_cached_route(link, index, content_id=content_id)
        if cached_route is not None:
            self._schedule_prefetch(content_type, content_id, category)
            return RedirectResponse(url=cached_route, status_code=307)

        # Non-torrent direct HTTP / HLS streams
        if link.startswith(("http://", "https://")):
            self._schedule_prefetch(content_type, content_id, category)
            self._schedule_downloads(link, title, poster, category, index, content_type, content_id)
            return RedirectResponse(url=link, status_code=307)

        if hasattr(self.torrserver_client, "resolve_file_index"):
            index = await self.torrserver_client.resolve_file_index(
                link,
                index=index,
                content_id=content_id,
                content_type=content_type,
                title=title,
                poster=poster,
                category=category,
            )
        elif index is None or index <= 0:
            index = 1

        self._schedule_prefetch(content_type, content_id, category)
        self._schedule_initialization(link, title, poster, category, index)
        self._schedule_downloads(link, title, poster, category, index, content_type, content_id)

        return RedirectResponse(
            url=self.torrserver_client.build_play_url(link, title, poster, category, index),
            status_code=307,
        )

    def _record_playback(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
        content_type: str | None,
        content_id: str | None,
    ) -> None:
        if not self.playback_history_repository:
            return
        try:
            infohash = extract_infohash(link)
            media_item_id = None
            media_id = None
            if self.media_metadata_service and content_id:
                try:
                    media, item = self.media_metadata_service.ensure_media_and_item(
                        content_id=content_id,
                        content_type=content_type,
                        fallback_title=title,
                        fallback_poster=poster,
                    )
                    media_item_id = item.id
                    media_id = media.id
                    if media.poster:
                        poster = media.poster
                except Exception as ex:
                    self.logger.warning("Error resolving media metadata for playback: %s", ex)

            self.playback_history_repository.record_playback(
                media_item_id=media_item_id,
                media_id=media_id,
                content_id=content_id,
                content_type=content_type,
                title=title,
                poster=poster,
                category=category,
                source_link=link,
                infohash=infohash,
                file_index=index,
            )
        except Exception as e:
            self.logger.warning("Failed to record playback history: %s", e)


    def _schedule_prefetch(
        self,
        content_type: str | None,
        content_id: str | None,
        category: str | None,
    ) -> None:
        if not content_type or not content_id:
            return
        if hasattr(self.next_episode_prefetch_service, "schedule_prefetch"):
            self.next_episode_prefetch_service.schedule_prefetch(content_type, content_id, category)
        elif hasattr(self.next_episode_prefetch_service, "enqueue_next_episode"):
            asyncio.create_task(self.next_episode_prefetch_service.enqueue_next_episode(content_type, content_id, category))

    def _get_cached_route(self, link: str, index: int | None = None, content_id: str | None = None) -> str | None:
        try:
            return self.cache_service.get_cached_route(link, index, content_id=content_id)
        except TypeError:
            return self.cache_service.get_cached_route(link, index)

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
        except Exception:
            self.logger.exception("Unable to enqueue cache download work")
