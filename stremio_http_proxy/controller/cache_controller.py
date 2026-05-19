from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from injector import inject

from stremio_http_proxy.service.cache_manager import CacheManager


class CacheController:
    @inject
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager
        self.router = APIRouter(tags=["Cache"])
        self.router.add_api_route("/cache/{infohash}/{index}", self.serve, methods=["GET"])

    async def serve(self, infohash: str, index: int) -> FileResponse:
        cache_key = self.cache_manager.build_cache_key_from_parts(infohash, index)
        entry = self.cache_manager.get_entry(cache_key)
        if entry.status != "ready":
            raise HTTPException(status_code=404, detail="Cached file not found")

        self.cache_manager.touch(cache_key)
        return FileResponse(entry.file_path)
