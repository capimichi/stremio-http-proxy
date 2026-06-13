from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from injector import inject

from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.cache_token_service import CacheTokenService
from stremio_http_proxy.service.dashboard_service import DashboardService


class CacheController:
    @inject
    def __init__(self, cache_service: CacheService, cache_token_service: CacheTokenService, dashboard_service: DashboardService, basic_auth_service: BasicAuthService):
        self.cache_service = cache_service
        self.cache_token_service = cache_token_service
        self.dashboard_service = dashboard_service
        self.basic_auth_service = basic_auth_service
        self.router = APIRouter(tags=["Cache"])
        self._register_routes()

    def _register_routes(self) -> None:
        self.router.add_api_route("/cache/{infohash}/{index}", self.serve, methods=["GET"])

        security = self.basic_auth_service.security
        def require_auth(credentials=Depends(security)) -> None:
            self.basic_auth_service.require_auth(credentials)
        dependencies = [Depends(require_auth)]
        self.router.add_api_route("/downloads", self.downloads, methods=["GET"], dependencies=dependencies)

    async def serve(self, infohash: str, index: int, expires: int = Query(), token: str = Query()) -> FileResponse:
        if not self.cache_token_service.is_valid(infohash, index, expires, token):
            raise HTTPException(status_code=403, detail="Invalid cache token")

        file_path = self.cache_service.get_cached_file_path(infohash, index)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Cached file not found")

        return FileResponse(file_path)

    async def downloads(
        self,
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=10, ge=1, le=100),
        search: str | None = Query(default=None),
    ) -> dict:
        return self.dashboard_service.get_download_status(page=page, limit=limit, search=search).model_dump()
