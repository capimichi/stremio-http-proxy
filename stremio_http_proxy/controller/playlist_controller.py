from fastapi import APIRouter, HTTPException, Response
from injector import inject

from stremio_http_proxy.service.playlist_service import PlaylistService


class PlaylistController:
    @inject
    def __init__(self, playlist_service: PlaylistService):
        self.playlist_service = playlist_service
        self.router = APIRouter(tags=["Playlist"])
        self.router.add_api_route(
            "/streams/{infohash}/playlist.m3u8",
            self.get_playlist,
            methods=["GET"],
        )

    async def get_playlist(self, infohash: str) -> Response:
        try:
            playlist = self.playlist_service.build_for_infohash(infohash)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(content=playlist, media_type="application/vnd.apple.mpegurl")
