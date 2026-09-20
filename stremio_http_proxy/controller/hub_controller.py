from typing import Any
from fastapi import APIRouter, Depends, Query
from injector import inject
from pydantic import BaseModel

from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.hub_service import HubService


class CacheSeasonRequest(BaseModel):
    content_id: str
    season: int
    total_episodes: int
    category: str = "tv"


class CacheEpisodeRequest(BaseModel):
    content_id: str
    season: int | None = None
    episode: int | None = None
    content_type: str = "series"
    category: str | None = None


class HubController:
    @inject
    def __init__(
        self,
        hub_service: HubService,
        basic_auth_service: BasicAuthService,
    ):
        self.hub_service = hub_service
        self.basic_auth_service = basic_auth_service
        self.router = APIRouter(tags=["Hub"])
        self._register_routes()

    def _register_routes(self) -> None:
        security = self.basic_auth_service.security

        def require_auth(credentials=Depends(security)) -> None:
            self.basic_auth_service.require_auth(credentials)

        auth = [Depends(require_auth)]

        self.router.add_api_route("/api/hub/recent", self.get_recent_media, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/hub/library", self.get_library, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/hub/library/{media_id:path}", self.delete_library_media, methods=["DELETE"], dependencies=auth)
        self.router.add_api_route("/api/hub/media-streams/{content_id:path}", self.get_media_streams, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/hub/season-cache/{content_id:path}/{season}", self.get_season_cache_status, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/browser/cache-season", self.cache_season, methods=["POST"], dependencies=auth)
        self.router.add_api_route("/api/browser/cache-episode", self.cache_episode, methods=["POST"], dependencies=auth)
        self.router.add_api_route("/api/hub/streams/{cache_key:path}", self.delete_stream, methods=["DELETE"], dependencies=auth)
        self.router.add_api_route("/api/hub/tasks", self.get_tasks, methods=["GET"], dependencies=auth)

    async def get_tasks(
        self,
        status: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        tasks = self.hub_service.get_tasks(status=status, limit=limit)
        return {"tasks": tasks, "count": len(tasks)}

    async def get_recent_media(self, limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
        items = self.hub_service.get_recent_media(limit=limit)
        return {"items": items, "count": len(items)}

    async def get_library(
        self,
        type: str | None = Query(default=None),
        cached_only: bool = Query(default=False),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return self.hub_service.get_library(
            media_type=type,
            cached_only=cached_only,
            limit=limit,
            offset=offset,
        )

    async def delete_library_media(self, media_id: str) -> dict[str, Any]:
        return self.hub_service.delete_media(media_id)

    async def get_media_streams(self, content_id: str) -> dict[str, Any]:
        streams = self.hub_service.get_media_streams(content_id)
        return {"content_id": content_id, "streams": streams}

    async def get_season_cache_status(self, content_id: str, season: int) -> dict[str, Any]:
        status_map = self.hub_service.get_season_cache_status(content_id, season)
        return {"content_id": content_id, "season": season, "episodes": status_map}

    async def cache_season(self, payload: CacheSeasonRequest) -> dict[str, Any]:
        return self.hub_service.cache_season(
            content_id=payload.content_id,
            season=payload.season,
            total_episodes=payload.total_episodes,
            category=payload.category,
        )

    async def cache_episode(self, payload: CacheEpisodeRequest) -> dict[str, Any]:
        return self.hub_service.cache_episode(
            content_id=payload.content_id,
            season=payload.season,
            episode=payload.episode,
            content_type=payload.content_type,
            category=payload.category,
        )

    async def delete_stream(self, cache_key: str) -> dict[str, Any]:
        return self.hub_service.delete_stream(cache_key)
