from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
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
        self.router.add_api_route("/", self.redirect_to_dashboard, methods=["GET"], include_in_schema=False, dependencies=dependencies)
        self.router.add_api_route("/dashboard/index", self.dashboard_index, methods=["GET"], include_in_schema=False, dependencies=dependencies)
        self.router.add_api_route("/dashboard/cache-items", self.cache_items, methods=["GET"], include_in_schema=False, dependencies=dependencies)

    async def redirect_to_dashboard(self) -> RedirectResponse:
        return RedirectResponse(url="/dashboard/index")

    async def dashboard_index(self) -> HTMLResponse:
        return HTMLResponse(self.dashboard_service.get_index_html())

    async def cache_items(self) -> HTMLResponse:
        return HTMLResponse(self.dashboard_service.get_cache_items_html())
