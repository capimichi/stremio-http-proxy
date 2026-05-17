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
            return self.stream_rewrite_service.rewrite(payload)
        return payload
