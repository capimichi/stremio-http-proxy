from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from injector import inject
from pydantic import BaseModel

from stremio_http_proxy.manager.jinja_manager import JinjaManager
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.whitelist_service import WhitelistService


class AddWhitelistRequest(BaseModel):
    infohash: str
    imdb_id: str
    media_title: str | None = None
    season: int | None = None
    episode: int | None = None


class WhitelistController:
    @inject
    def __init__(
        self,
        whitelist_service: WhitelistService,
        basic_auth_service: BasicAuthService,
        jinja_manager: JinjaManager,
    ):
        self.whitelist_service = whitelist_service
        self.basic_auth_service = basic_auth_service
        self.jinja_manager = jinja_manager
        self.router = APIRouter(tags=["Whitelist"])
        self._register_routes()

    def _register_routes(self) -> None:
        security = self.basic_auth_service.security

        def require_auth(credentials=Depends(security)) -> None:
            self.basic_auth_service.require_auth(credentials)

        auth = [Depends(require_auth)]

        self.router.add_api_route("/dashboard/whitelist", self.whitelist_page, methods=["GET"], include_in_schema=False, dependencies=auth)
        self.router.add_api_route("/api/whitelist", self.list_whitelist, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/whitelist", self.add_whitelist, methods=["POST"], dependencies=auth)
        self.router.add_api_route("/api/whitelist/{entry_id}", self.remove_whitelist, methods=["DELETE"], dependencies=auth)

    async def whitelist_page(self) -> HTMLResponse:
        return HTMLResponse(self.jinja_manager.render("dashboard/pages/whitelist.html"))

    async def list_whitelist(
        self,
        search: str | None = None,
        season: int | None = None,
        episode: int | None = None,
        infohash: str | None = None,
        imdb_id: str | None = None,
    ) -> list[dict]:
        return self.whitelist_service.list_whitelist(
            search=search,
            season=season,
            episode=episode,
            infohash=infohash,
            imdb_id=imdb_id,
        )

    async def add_whitelist(self, body: AddWhitelistRequest) -> dict:
        entry = self.whitelist_service.add_to_whitelist(
            infohash=body.infohash,
            imdb_id=body.imdb_id,
            media_title=body.media_title,
            season=body.season,
            episode=body.episode,
        )
        return {"id": entry.id, "infohash": entry.infohash, "imdb_id": entry.imdb_id, "media_title": entry.media_title, "season": entry.season, "episode": entry.episode}

    async def remove_whitelist(self, entry_id: int) -> dict:
        ok = self.whitelist_service.remove_from_whitelist(entry_id)
        return {"ok": ok}
