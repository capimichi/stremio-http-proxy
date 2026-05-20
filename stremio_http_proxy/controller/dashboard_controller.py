from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from injector import inject

from stremio_http_proxy.service.dashboard_service import DashboardService


class DashboardController:
    @inject
    def __init__(self, dashboard_service: DashboardService):
        self.dashboard_service = dashboard_service
        self.router = APIRouter(tags=["Dashboard"])
        self._register_routes()

    def _register_routes(self) -> None:
        self.router.add_api_route("/", self.index, methods=["GET"], include_in_schema=False)
        self.router.add_api_route("/downloads", self.downloads, methods=["GET"])

    async def index(self) -> FileResponse:
        return FileResponse("static/index.html")

    async def downloads(
        self,
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=10, ge=1, le=100),
    ) -> dict:
        return self.dashboard_service.get_download_status(page=page, limit=limit).model_dump()
