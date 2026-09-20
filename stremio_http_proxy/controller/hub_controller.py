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
        self.router.add_api_route("/api/hub/media-streams/{content_id:path}", self.get_media_streams, methods=["GET"], dependencies=auth)
        self.router.add_api_route("/api/browser/cache-season", self.cache_season, methods=["POST"], dependencies=auth)
        self.router.add_api_route("/api/browser/cache-episode", self.cache_episode, methods=["POST"], dependencies=auth)
        self.router.add_api_route("/api/hub/streams/{cache_key:path}", self.delete_stream, methods=["DELETE"], dependencies=auth)

    async def get_recent_media(self, limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
        items = self.hub_service.get_recent_media(limit=limit)
        return {"items": items, "count": len(items)}

    async def get_media_streams(self, content_id: str) -> dict[str, Any]:
        streams = self.hub_service.get_media_streams(content_id)
        return {"content_id": content_id, "streams": streams}

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
