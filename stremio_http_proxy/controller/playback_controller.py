from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient


class PlaybackController:
    @inject
    def __init__(self, torrserver_client: TorrServerClient):
        self.torrserver_client = torrserver_client
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
        try:
            await self.torrserver_client.add_torrent(link, title, poster, category)
            await self.torrserver_client.preload(link, title, poster, category, index)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Unable to initialize TorrServer playback") from exc

        return RedirectResponse(
            url=self.torrserver_client.build_play_url(link, title, poster, category, index),
            status_code=307,
        )
