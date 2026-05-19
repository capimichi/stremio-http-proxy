from fastapi import APIRouter
from injector import inject

from stremio_http_proxy.service.addon_proxy_service import AddonProxyService


class AddonController:
    @inject
    def __init__(self, addon_proxy_service: AddonProxyService):
        self.addon_proxy_service = addon_proxy_service
        self.router = APIRouter(tags=["Addon"])
        self._register_routes()

    def _register_routes(self) -> None:
        self.router.add_api_route("/manifest.json", self.manifest, methods=["GET"])
        self.router.add_api_route("/catalog/{type}/{id}.json", self.catalog, methods=["GET"])
        self.router.add_api_route("/meta/{type}/{id}.json", self.meta, methods=["GET"])
        self.router.add_api_route("/stream/{type}/{id}.json", self.stream, methods=["GET"])
        self.router.add_api_route("/subtitles/{type}/{id}.json", self.subtitles, methods=["GET"])

    async def manifest(self) -> dict:
        return await self.addon_proxy_service.proxy_json("/manifest.json")

    async def catalog(self, type: str, id: str) -> dict:
        return await self.addon_proxy_service.proxy_json(f"/catalog/{type}/{id}.json")

    async def meta(self, type: str, id: str) -> dict:
        return await self.addon_proxy_service.proxy_json(f"/meta/{type}/{id}.json")

    async def stream(self, type: str, id: str) -> dict:
        return await self.addon_proxy_service.proxy_json(
            f"/stream/{type}/{id}.json",
            rewrite_context={
                "content_type": type,
                "content_id": id,
            },
        )

    async def subtitles(self, type: str, id: str) -> dict:
        return await self.addon_proxy_service.proxy_json(f"/subtitles/{type}/{id}.json")
