from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from injector import inject

from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.cache_token_service import CacheTokenService


class CacheController:
    @inject
    def __init__(self, cache_service: CacheService, cache_token_service: CacheTokenService):
        self.cache_service = cache_service
        self.cache_token_service = cache_token_service
        self.router = APIRouter(tags=["Cache"])
        self.router.add_api_route("/cache/{infohash}/{index}", self.serve, methods=["GET"])

    async def serve(self, infohash: str, index: int, expires: int = Query(), token: str = Query()) -> FileResponse:
        if not self.cache_token_service.is_valid(infohash, index, expires, token):
            raise HTTPException(status_code=403, detail="Invalid cache token")

        file_path = self.cache_service.get_cached_file_path(infohash, index)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Cached file not found")

        return FileResponse(file_path)
