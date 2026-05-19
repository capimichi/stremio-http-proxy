from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from injector import inject

from stremio_http_proxy.service.cache_service import CacheService


class CacheController:
    @inject
    def __init__(self, cache_service: CacheService):
        self.cache_service = cache_service
        self.router = APIRouter(tags=["Cache"])
        self.router.add_api_route("/cache/{infohash}/{index}", self.serve, methods=["GET"])

    async def serve(self, infohash: str, index: int) -> FileResponse:
        file_path = self.cache_service.get_cached_file_path(infohash, index)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Cached file not found")

        return FileResponse(file_path)
