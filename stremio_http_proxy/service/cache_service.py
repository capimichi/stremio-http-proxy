from injector import inject

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.manager.cache_manager import CacheManager


class CacheService:
    @inject
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager

    def get_cached_route(self, link: str, index: int | None = None) -> str | None:
        cache_key = self.cache_manager.build_cache_key(link, index)
        if cache_key is None or not self.cache_manager.is_ready(cache_key):
            return None

        infohash, cache_index = self.cache_manager.parse_cache_key(cache_key)
        return f"/cache/{infohash}/{cache_index}"

    def get_cached_file_path(self, infohash: str, index: int) -> str | None:
        cache_key = self.cache_manager.build_cache_key_from_parts(infohash, index)
        entry = self.cache_manager.get_entry(cache_key)
        if entry.status != CacheEntryStatusEnum.READY:
            return None

        self.cache_manager.touch(cache_key)
        return entry.file_path
