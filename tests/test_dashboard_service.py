from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
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
    older_entry = cache_manager.get_entry(older_key).model_copy(update={"title": "Older Episode", "status": CacheEntryStatusEnum.DOWNLOADING, "created_at": 1})
    cache_manager._write_entry(older_key, older_entry)
    cache_manager.mark_progress(older_key, 512, 4096, 12.5, 64.0)
    newer_entry = cache_manager.get_entry(newer_key).model_copy(update={"title": "Newer Episode", "status": CacheEntryStatusEnum.DOWNLOADING, "created_at": 2, "attempt": 1})
    cache_manager._write_entry(newer_key, newer_entry)
    cache_manager.mark_progress(newer_key, 1024, 4096, 25.0, 128.0)

    service = DashboardService(cache_manager, "https://proxy.example.com")

    payload = service.get_download_status()

    assert payload.manifest_url == "https://proxy.example.com/manifest.json"
    assert payload.page == 1
    assert payload.limit == 10
    assert payload.total_items == 2
    assert payload.total_pages == 1
    assert payload.total_cache_bytes == 1536
    assert payload.status_counts == {"downloading": 2}
    assert payload.active_downloads == 2
    assert len(payload.downloads) == 2
    assert payload.downloads[0].cache_key == newer_key
    assert payload.downloads[0].title == "Newer Episode"
    assert payload.downloads[1].cache_key == older_key
    assert payload.downloads[0].infohash == "abcdef1234567890abcdef1234567890abcdef12"
    assert payload.downloads[0].index == 3
    assert payload.downloads[0].progress_percent == 25.0
    assert payload.downloads[0].created_at is not None


def test_dashboard_service_includes_completed_entries(tmp_path):
    cache_manager = build_cache_manager(tmp_path)
    ready_key = cache_manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 1)
    ready_entry = cache_manager.get_entry(ready_key).model_copy(update={"title": "Completed Episode", "status": CacheEntryStatusEnum.DOWNLOADING, "created_at": 1})
    cache_manager._write_entry(ready_key, ready_entry)
    cache_manager.mark_ready(ready_key, 2048)

    service = DashboardService(cache_manager, "https://proxy.example.com")

    payload = service.get_download_status()

    assert payload.total_cache_bytes == 2048
    assert payload.status_counts == {"ready": 1}
    assert payload.active_downloads == 0
    assert len(payload.downloads) == 1
    assert payload.downloads[0].cache_key == ready_key
    assert payload.downloads[0].title == "Completed Episode"
    assert payload.downloads[0].status == CacheEntryStatusEnum.READY
    assert payload.downloads[0].completed_at is not None


def test_dashboard_service_paginates_results(tmp_path):
    cache_manager = build_cache_manager(tmp_path)
    keys = []
    for index in range(12):
        cache_key = cache_manager.build_cache_key_from_parts(f"{index:040x}"[-40:], index)
        entry = cache_manager.get_entry(cache_key).model_copy(update={"status": CacheEntryStatusEnum.QUEUED, "created_at": index})
        cache_manager._write_entry(cache_key, entry)
        keys.append(cache_key)

    service = DashboardService(cache_manager, "https://proxy.example.com")

    payload = service.get_download_status(page=2, limit=10)

    assert payload.page == 2
    assert payload.limit == 10
    assert payload.total_items == 12
    assert payload.total_pages == 2
    assert payload.total_cache_bytes == 0
    assert payload.status_counts == {"queued": 12}
    assert payload.active_downloads == 0
    assert len(payload.downloads) == 2
