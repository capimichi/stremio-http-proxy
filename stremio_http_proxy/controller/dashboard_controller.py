from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from injector import inject

from stremio_http_proxy.service.basic_auth_service import BasicAuthService


class DashboardController:
    @inject
    def __init__(self, basic_auth_service: BasicAuthService):
        self.basic_auth_service = basic_auth_service
        self.templates = Jinja2Templates(directory="templates")
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

    async def dashboard_index(self, request: Request):
        return self.templates.TemplateResponse("dashboard/pages/index.html", {"request": request})

    async def cache_items(self, request: Request):
        return self.templates.TemplateResponse("dashboard/pages/cache_items.html", {"request": request})
