from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from injector import inject

from stremio_http_proxy.manager.jinja_manager import JinjaManager
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.content_browser_service import ContentBrowserService
from stremio_http_proxy.service.whitelist_service import WhitelistService


class BrowserController:
    @inject
    def __init__(
        self,
        content_browser_service: ContentBrowserService,
        whitelist_service: WhitelistService,
        basic_auth_service: BasicAuthService,
        jinja_manager: JinjaManager,
    ):
        self.content_browser_service = content_browser_service
        self.whitelist_service = whitelist_service
        self.basic_auth_service = basic_auth_service
        self.jinja_manager = jinja_manager
        self.router = APIRouter(tags=["Browser"])
        self._register_routes()

    def _register_routes(self) -> None:
        security = self.basic_auth_service.security

        def require_auth(credentials=Depends(security)) -> None:
            self.basic_auth_service.require_auth(credentials)

        auth = [Depends(require_auth)]

        self.router.add_api_route("/dashboard/browser", self.browser_page, methods=["GET"], include_in_schema=False, dependencies=auth)
        self.router.add_api_route("/dashboard/browser/{media_type}/{imdb_id}", self.browser_detail_page, methods=["GET"], include_in_schema=False, dependencies=auth)
        self.router.add_api_route("/api/browser/search", self.search_content, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/browser/resolve", self.resolve_content, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/browser/content", self.browse_content, methods=["GET"], dependencies=auth)

    async def browser_page(self) -> HTMLResponse:
        return HTMLResponse(self.jinja_manager.render("dashboard/pages/browser.html"))

    async def browser_detail_page(self, media_type: str, imdb_id: str) -> HTMLResponse:
        return HTMLResponse(self.jinja_manager.render("dashboard/pages/browser_detail.html", media_type=media_type, imdb_id=imdb_id))

    async def search_content(self, q: str, type: str = "movie", page: int = 1) -> dict:
        return await self.content_browser_service.search_content(q, type, page)

    async def resolve_content(self, tmdb_id: int, type: str = "movie") -> dict:
        imdb_id = await self.content_browser_service.resolve_content(tmdb_id, type)
        return {"imdb_id": imdb_id}

    async def browse_content(self, type: str, id: str, season: int | None = None, episode: int | None = None) -> dict:
        data = await self.content_browser_service.browse_content(type, id, season, episode)
        whitelist = self.whitelist_service.get_whitelist_for_content(id)
        data["whitelist"] = whitelist
        return data
