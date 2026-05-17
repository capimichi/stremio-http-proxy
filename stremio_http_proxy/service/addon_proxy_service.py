from injector import inject

from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class AddonProxyService:
    @inject
    def __init__(self, upstream_client: UpstreamClient, stream_rewrite_service: StreamRewriteService):
        self.upstream_client = upstream_client
        self.stream_rewrite_service = stream_rewrite_service

    async def proxy_json(self, path: str, query_params: dict[str, str] | None = None) -> dict:
        payload = await self.upstream_client.get_json(path, query_params=query_params)
        if path.startswith("/stream/"):
            return await self.stream_rewrite_service.rewrite(payload, self._resolve_category(path))
        return payload

    def _resolve_category(self, path: str) -> str:
        stream_type = path.split("/", 3)[2]
        return {
            "movie": "movie",
            "series": "tv",
            "tv": "tv",
            "channel": "tv",
            "music": "music",
        }.get(stream_type, "other")
