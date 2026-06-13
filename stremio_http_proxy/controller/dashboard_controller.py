from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from injector import inject

from stremio_http_proxy.manager.jinja_manager import JinjaManager
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.dashboard_service import DashboardService


class DashboardController:
    @inject
    def __init__(self, dashboard_service: DashboardService, basic_auth_service: BasicAuthService, jinja_manager: JinjaManager):
        self.dashboard_service = dashboard_service
        self.basic_auth_service = basic_auth_service
        self.jinja_manager = jinja_manager
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
        self.router.add_api_route("/dashboard/cache-entry/{infohash}/{index}", self.cache_entry, methods=["GET"], include_in_schema=False, dependencies=dependencies)

    async def redirect_to_dashboard(self) -> RedirectResponse:
        return RedirectResponse(url="/dashboard/index")

    async def dashboard_index(self) -> HTMLResponse:
        context = self.dashboard_service.get_index_context()
        return HTMLResponse(self.jinja_manager.render("dashboard/pages/index.html", **context))

    async def cache_items(self) -> HTMLResponse:
        context = self.dashboard_service.get_cache_items_context()
        return HTMLResponse(self.jinja_manager.render("dashboard/pages/cache_items.html", **context))

    async def cache_entry(self, infohash: str, index: int) -> Response:
        context, status = self.dashboard_service.get_cache_entry_context(infohash, index)
        if context is None:
            return HTMLResponse("<h1>404 - Not Found</h1>", status_code=404)
        return HTMLResponse(self.jinja_manager.render("dashboard/pages/cache_entry.html", **context))
