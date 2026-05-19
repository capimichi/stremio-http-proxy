from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.manager.cache_manager import CacheManager


def test_cache_service_returns_cached_route_for_ready_entry(tmp_path):
    manager = CacheManager(str(tmp_path), 7, 20, LoggerFactory(str(tmp_path / "logs")))
    cache_key = manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 2)
    media_path = manager.prepare_download_path(cache_key)
    media_path.write_bytes(b"demo")
    manager.finalize_download(cache_key)
    manager.mark_ready(cache_key, 4)
    service = CacheService(manager)

    route = service.get_cached_route("magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12", 2)

    assert route == "/cache/abcdef1234567890abcdef1234567890abcdef12/2"


def test_cache_service_returns_cached_file_path_and_touches_entry(tmp_path):
    manager = CacheManager(str(tmp_path), 7, 20, LoggerFactory(str(tmp_path / "logs")))
    cache_key = manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 3)
    media_path = manager.prepare_download_path(cache_key)
    media_path.write_bytes(b"demo")
    manager.finalize_download(cache_key)
    ready_entry = manager.mark_ready(cache_key, 4)
    service = CacheService(manager)

    file_path = service.get_cached_file_path("abcdef1234567890abcdef1234567890abcdef12", 3)
    touched_entry = manager.get_entry(cache_key)

    assert file_path == ready_entry.file_path
    assert touched_entry.last_accessed_at is not None
    assert touched_entry.last_accessed_at >= ready_entry.last_accessed_at
