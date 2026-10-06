from urllib.parse import urlencode

from injector import inject

from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.manager.redis_cache_manager import RedisCacheManager


class UpstreamCachedClient(UpstreamClient):
    @inject
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int,
        cache_manager: RedisCacheManager,
        cache_ttl_seconds: int = 172800,
    ):
        super().__init__(base_url=base_url, timeout_seconds=timeout_seconds)
        self.cache_manager = cache_manager
        self.cache_ttl_seconds = cache_ttl_seconds

    def _should_cache(self, path: str) -> bool:
        return path.startswith("/stream/")

    def _build_cache_key(self, path: str, query_params: dict[str, str] | None = None) -> str:
        clean_path = path.strip("/")
        if query_params:
            sorted_qs = urlencode(sorted(query_params.items()))
            return f"upstream:{clean_path}?{sorted_qs}"
        return f"upstream:{clean_path}"

    async def get_json(self, path: str, query_params: dict[str, str] | None = None) -> dict:
        should_cache = self._should_cache(path)
        cache_key = self._build_cache_key(path, query_params) if should_cache else None

        if should_cache and cache_key is not None:
            cached_payload = await self.cache_manager.get(cache_key)
            if cached_payload is not None and isinstance(cached_payload, dict):
                return cached_payload

        payload = await super().get_json(path, query_params=query_params)

        if should_cache and cache_key is not None and isinstance(payload, dict):
            await self.cache_manager.set(cache_key, payload, ttl_seconds=self.cache_ttl_seconds)

        return payload
