from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.service.dashboard_service import DashboardService


def build_cache_manager(tmp_path):
    return CacheManager(
        str(tmp_path / "cache"),
        DbManager(str(tmp_path / "cache.sqlite")),
        7,
        20,
        LoggerFactory(str(tmp_path / "logs")),
    )


def test_dashboard_service_returns_manifest_and_all_cache_entries(tmp_path):
    cache_manager = build_cache_manager(tmp_path)
    newer_key = cache_manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 3)
    older_key = cache_manager.build_cache_key_from_parts("fedcba1234567890abcdef1234567890abcdef12", 1)
    cache_manager.mark_downloading(older_key, attempt=0)
    cache_manager.mark_progress(older_key, 512, 4096, 12.5, 64.0)
    cache_manager.mark_downloading(newer_key, attempt=1)
    cache_manager.mark_progress(newer_key, 1024, 4096, 25.0, 128.0)

    service = DashboardService(cache_manager, "https://proxy.example.com")

    payload = service.get_download_status()

    assert payload.manifest_url == "https://proxy.example.com/manifest.json"
    assert len(payload.downloads) == 2
    assert payload.downloads[0].cache_key == newer_key
    assert payload.downloads[1].cache_key == older_key
    assert payload.downloads[0].infohash == "abcdef1234567890abcdef1234567890abcdef12"
    assert payload.downloads[0].index == 3
    assert payload.downloads[0].progress_percent == 25.0
    assert payload.downloads[0].created_at is not None


def test_dashboard_service_includes_completed_entries(tmp_path):
    cache_manager = build_cache_manager(tmp_path)
    ready_key = cache_manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 1)
    cache_manager.mark_downloading(ready_key)
    cache_manager.mark_ready(ready_key, 2048)

    service = DashboardService(cache_manager, "https://proxy.example.com")

    payload = service.get_download_status()

    assert len(payload.downloads) == 1
    assert payload.downloads[0].cache_key == ready_key
    assert payload.downloads[0].status == "ready"
    assert payload.downloads[0].completed_at is not None
