from urllib.parse import parse_qs, urlparse

from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.cache_token_service import CacheTokenService
from stremio_http_proxy.manager.cache_manager import CacheManager


def build_manager(tmp_path):
    mgr = CacheManager(
        str(tmp_path),
        DbManager(str(tmp_path / "cache.sqlite")),
        7,
        20,
        LoggerFactory(str(tmp_path / "logs")),
    )
    mgr.get_min_cache_size = lambda: 1
    return mgr


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


def test_cache_service_returns_cached_route_by_content_id_fallback(tmp_path):
    manager = build_manager(tmp_path)
    from stremio_http_proxy.repository.media_repository import MediaRepository
    from stremio_http_proxy.repository.media_item_repository import MediaItemRepository

    media_repo = MediaRepository(manager.db_manager)
    media_item_repo = MediaItemRepository(manager.db_manager)
    media = media_repo.upsert_media(imdb_id="tt3749900", media_type="series", title="Test Series")
    item = media_item_repo.upsert_media_item(media_id=media.id, season=1, episode=2)

    # File is downloaded at index 9 for episode tt3749900:1:2
    cache_key = manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 9)
    media_path = manager.prepare_download_path(cache_key)
    media_path.write_bytes(b"demo video")
    manager.finalize_download(cache_key)
    ready_entry = manager.mark_ready(cache_key, 10)
    manager._write_entry(cache_key, ready_entry.model_copy(update={"media_item_id": item.id}))

    service = CacheService(manager, "https://proxy.example.com", CacheTokenService("secret", 259200))

    # Request with wrong index (e.g. 8) but matching content_id
    route = service.get_cached_route(
        "magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12",
        index=8,
        content_id="tt3749900:1:2",
    )

    assert route is not None
    parsed = urlparse(route)
    assert parsed.path == "/cache/abcdef1234567890abcdef1234567890abcdef12/9"


def test_cache_service_uses_cache_base_url_when_provided(tmp_path):
    manager = build_manager(tmp_path)
    cache_key = manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 2)
    media_path = manager.prepare_download_path(cache_key)
    media_path.write_bytes(b"demo")
    manager.finalize_download(cache_key)
    manager.mark_ready(cache_key, 4)

    service = CacheService(
        manager,
        "https://proxy.example.com",
        CacheTokenService("secret", 259200),
        cache_base_url="http://192.168.1.100:8691",
    )

    route = service.get_cached_route("magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12", 2)
    parsed = urlparse(route)

    assert parsed.scheme == "http"
    assert parsed.netloc == "192.168.1.100:8691"
    assert parsed.path == "/cache/abcdef1234567890abcdef1234567890abcdef12/2"
    assert set(parse_qs(parsed.query)) == {"expires", "token"}

