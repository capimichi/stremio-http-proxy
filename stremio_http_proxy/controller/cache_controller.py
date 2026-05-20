from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from injector import inject

from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.cache_service import CacheService


class CacheController:
    @inject
    def __init__(self, cache_service: CacheService, basic_auth_service: BasicAuthService):
        self.cache_service = cache_service
        self.basic_auth_service = basic_auth_service
        self.router = APIRouter(tags=["Cache"])
        security = self.basic_auth_service.security

        def require_auth(credentials=Depends(security)) -> None:
            self.basic_auth_service.require_auth(credentials)

        dependencies = [Depends(require_auth)]
        self.router.add_api_route("/cache/{infohash}/{index}", self.serve, methods=["GET"], dependencies=dependencies)

    async def serve(self, infohash: str, index: int) -> FileResponse:
        file_path = self.cache_service.get_cached_file_path(infohash, index)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Cached file not found")

        return FileResponse(file_path)
