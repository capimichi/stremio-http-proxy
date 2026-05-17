import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient


class PlaybackController:
    @inject
    def __init__(self, torrserver_client: TorrServerClient):
        self.logger = logging.getLogger(__name__)
        self.torrserver_client = torrserver_client
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
    ) -> RedirectResponse:
        self._schedule_initialization(link, title, poster, category, index)

        return RedirectResponse(
            url=self.torrserver_client.build_play_url(link, title, poster, category, index),
            status_code=307,
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
