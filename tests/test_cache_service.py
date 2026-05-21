from urllib.parse import parse_qs, urlparse

from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.cache_token_service import CacheTokenService
from stremio_http_proxy.manager.cache_manager import CacheManager


def build_manager(tmp_path):
    return CacheManager(
        str(tmp_path),
        DbManager(str(tmp_path / "cache.sqlite")),
        7,
        20,
        LoggerFactory(str(tmp_path / "logs")),
    )


def test_cache_service_returns_cached_route_for_ready_entry(tmp_path):
    manager = build_manager(tmp_path)
    cache_key = manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 2)
    media_path = manager.prepare_download_path(cache_key)
    media_path.write_bytes(b"demo")
    manager.finalize_download(cache_key)
    manager.mark_ready(cache_key, 4)
    service = CacheService(manager, "https://proxy.example.com", CacheTokenService("secret", 259200))

    route = service.get_cached_route("magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12", 2)

    parsed = urlparse(route)

    assert parsed.scheme == "https"
    assert parsed.netloc == "proxy.example.com"
    assert parsed.path == "/cache/abcdef1234567890abcdef1234567890abcdef12/2"
    assert set(parse_qs(parsed.query)) == {"expires", "token"}


def test_cache_service_returns_cached_file_path_and_touches_entry(tmp_path):
    manager = build_manager(tmp_path)
    cache_key = manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 3)
    media_path = manager.prepare_download_path(cache_key)
    media_path.write_bytes(b"demo")
    manager.finalize_download(cache_key)
    ready_entry = manager.mark_ready(cache_key, 4)
    service = CacheService(manager, "https://proxy.example.com", CacheTokenService("secret", 259200))

    file_path = service.get_cached_file_path("abcdef1234567890abcdef1234567890abcdef12", 3)
    touched_entry = manager.get_entry(cache_key)

    assert file_path == ready_entry.file_path
    assert touched_entry.last_accessed_at is not None
    assert touched_entry.last_accessed_at >= ready_entry.last_accessed_at
