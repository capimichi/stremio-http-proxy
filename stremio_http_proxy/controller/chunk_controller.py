from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from injector import inject

from stremio_http_proxy.service.torrent_service import TorrentService


class ChunkController:
    @inject
    def __init__(self, torrent_service: TorrentService):
        self.torrent_service = torrent_service
        self.router = APIRouter(tags=["Segments"])
        self.router.add_api_route(
            "/streams/{infohash}/segments/{segment_name}.ts",
            self.get_segment,
            methods=["GET"],
        )

    async def get_segment(self, infohash: str, segment_name: str) -> FileResponse:
        try:
            path = self.torrent_service.ensure_segment(infohash, segment_name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path=path, media_type="video/mp2t", filename=f"{segment_name}.ts")
