from urllib.parse import urlencode

from injector import inject

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.service.cache_token_service import CacheTokenService


class CacheService:
    @inject
    def __init__(
        self,
        cache_manager: CacheManager,
        public_base_url: str,
        cache_token_service: CacheTokenService,
        cache_enabled: bool = True,
    ):
        self.cache_manager = cache_manager
        self.public_base_url = public_base_url.rstrip("/")
        self.cache_token_service = cache_token_service
        self.cache_enabled = cache_enabled

    def get_cached_route(self, link: str, index: int | None = None) -> str | None:
        if not self.cache_enabled:
            return None
        cache_key = self.cache_manager.build_cache_key(link, index)
        if cache_key is None or not self.cache_manager.is_ready(cache_key):
            return None

        infohash, cache_index = self.cache_manager.parse_cache_key(cache_key)
        expires = self.cache_token_service.build_expires_at()
        token = self.cache_token_service.build_token(infohash, cache_index, expires)
        params = urlencode({"expires": str(expires), "token": token})
        return f"{self.public_base_url}/cache/{infohash}/{cache_index}?{params}"

    def get_cached_file_path(self, infohash: str, index: int) -> str | None:
        if not self.cache_enabled:
            return None
        cache_key = self.cache_manager.build_cache_key_from_parts(infohash, index)
        entry = self.cache_manager.get_entry(cache_key)
        if entry.status != CacheEntryStatusEnum.READY:
            return None

        self.cache_manager.touch(cache_key)
        return entry.file_path
