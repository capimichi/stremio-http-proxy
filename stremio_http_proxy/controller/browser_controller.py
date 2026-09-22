from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from injector import inject
from pydantic import BaseModel

from stremio_http_proxy.manager.jinja_manager import JinjaManager
from stremio_http_proxy.repository.media_item_repository import MediaItemRepository
from stremio_http_proxy.repository.media_repository import MediaRepository
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.content_browser_service import ContentBrowserService


class ImportMediaRequest(BaseModel):
    tmdb_id: int
    type: str = "movie"


class BrowserController:
    @inject
    def __init__(
        self,
        content_browser_service: ContentBrowserService,
        basic_auth_service: BasicAuthService,
        jinja_manager: JinjaManager,
        media_repository: MediaRepository | None = None,
        media_item_repository: MediaItemRepository | None = None,
    ):
        self.content_browser_service = content_browser_service
        self.basic_auth_service = basic_auth_service
        self.jinja_manager = jinja_manager
        self.media_repository = media_repository
        self.media_item_repository = media_item_repository
        self.router = APIRouter(tags=["Browser"])
        self._register_routes()

    def _register_routes(self) -> None:
        security = self.basic_auth_service.security

        def require_auth(credentials=Depends(security)) -> None:
            self.basic_auth_service.require_auth(credentials)

        auth = [Depends(require_auth)]

        self.router.add_api_route("/dashboard/browser", self.browser_page, methods=["GET"], include_in_schema=False, dependencies=auth)
        self.router.add_api_route("/dashboard/browser/media/{media_id:int}", self.browser_detail_page, methods=["GET"], include_in_schema=False, dependencies=auth)
        self.router.add_api_route("/api/browser/search", self.search_content, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/browser/import", self.import_media, methods=["POST"], dependencies=auth)
        self.router.add_api_route("/api/browser/media/{media_id:int}/refresh", self.refresh_media, methods=["POST"], dependencies=auth)
        self.router.add_api_route("/api/browser/streams/{media_id:int}", self.get_media_streams, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/browser/resolve", self.resolve_content, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/browser/content", self.browse_content, methods=["GET"], dependencies=auth)

    async def browser_page(self) -> HTMLResponse:
        return HTMLResponse(self.jinja_manager.render("dashboard/pages/browser.html"))

    async def browser_detail_page(self, media_id: int) -> HTMLResponse:
        if not self.media_repository:
            raise HTTPException(status_code=500, detail="Media repository not configured")

        media = self.media_repository.get_media(media_id)
        if not media:
            raise HTTPException(status_code=404, detail="Media non trovato")

        items = self.media_item_repository.get_items_for_media(media_id) if self.media_item_repository else []

        seasons_map: dict[int, list[dict[str, Any]]] = {}
        for item in items:
            s = item.season or 1
            if s not in seasons_map:
                seasons_map[s] = []
            seasons_map[s].append({
                "id": item.id,
                "season": item.season,
                "episode": item.episode,
                "title": item.title or f"Episodio {item.episode}",
                "overview": item.overview or "",
                "thumbnail": item.thumbnail or "",
                "release_date": item.release_date or "",
            })

        return HTMLResponse(
            self.jinja_manager.render(
                "dashboard/pages/browser_detail.html",
                media=media,
                media_id=media.id,
                media_type=media.type,
                imdb_id=media.imdb_id or "",
                seasons=sorted(seasons_map.keys()),
                episodes_by_season=seasons_map,
                items=items,
            )
        )

    async def search_content(self, q: str, type: str = "movie", page: int = 1) -> dict:
        data = await self.content_browser_service.search_content(q, type, page)
        # Check if items already exist in local DB to inform frontend
        if self.media_repository and "results" in data:
            for r in data["results"]:
                tmdb_id = r.get("tmdb_id")
                imdb_id = r.get("imdb_id")
                existing = None
                if tmdb_id:
                    existing = self.media_repository.get_by_tmdb_id(str(tmdb_id))
                if not existing and imdb_id:
                    existing = self.media_repository.get_by_imdb_id(imdb_id)
                if existing:
                    r["local_media_id"] = existing.id
        return data

    async def import_media(self, payload: ImportMediaRequest) -> dict:
        return await self.content_browser_service.import_media(payload.tmdb_id, payload.type)

    async def refresh_media(self, media_id: int) -> dict:
        try:
            return await self.content_browser_service.refresh_media(media_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_media_streams(self, media_id: int, season: int | None = None, episode: int | None = None) -> dict:
        if not self.media_repository:
            return {"streams": []}
        media = self.media_repository.get_media(media_id)
        if not media or not media.imdb_id:
            return {"streams": []}
        return await self.content_browser_service.browse_content(media.type, media.imdb_id, season, episode)

    async def resolve_content(self, tmdb_id: int, type: str = "movie") -> dict:
        imdb_id = await self.content_browser_service.resolve_content(tmdb_id, type)
        return {"imdb_id": imdb_id}

    async def browse_content(self, type: str, id: str, season: int | None = None, episode: int | None = None) -> dict:
        return await self.content_browser_service.browse_content(type, id, season, episode)
