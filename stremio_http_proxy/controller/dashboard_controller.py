from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from injector import inject

from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.dashboard_service import DashboardService


class DashboardController:
    @inject
    def __init__(self, dashboard_service: DashboardService, basic_auth_service: BasicAuthService):
        self.dashboard_service = dashboard_service
        self.basic_auth_service = basic_auth_service
        self.router = APIRouter(tags=["Dashboard"])
        self._register_routes()

    def _register_routes(self) -> None:
        security = self.basic_auth_service.security

        def require_auth(credentials=Depends(security)) -> None:
            self.basic_auth_service.require_auth(credentials)

        dependencies = [Depends(require_auth)]
        self.router.add_api_route("/", self.index, methods=["GET"], include_in_schema=False, dependencies=dependencies)
        self.router.add_api_route("/downloads", self.downloads, methods=["GET"], dependencies=dependencies)

    async def index(self) -> FileResponse:
        return FileResponse("static/index.html")

    async def downloads(
        self,
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=10, ge=1, le=100),
    ) -> dict:
        return self.dashboard_service.get_download_status(page=page, limit=limit).model_dump()
