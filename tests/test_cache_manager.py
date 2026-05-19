from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.manager.db_manager import DbManager


def build_manager(tmp_path):
    return CacheManager(
        str(tmp_path),
        DbManager(str(tmp_path / "cache.sqlite")),
        7,
        20,
        LoggerFactory(str(tmp_path / "logs")),
    )


def test_cache_manager_persists_progress_fields(tmp_path):
    manager = build_manager(tmp_path)
    cache_key = manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 1)

    manager.mark_downloading(cache_key)
    manager.mark_progress(cache_key, 52428800, 104857600, 50.0, 2097152.0)

    entry = manager.get_entry(cache_key)

    assert entry.status == "downloading"
    assert entry.downloaded_bytes == 52428800
    assert entry.expected_bytes == 104857600
    assert entry.progress_percent == 50.0
    assert entry.download_speed_bytes_per_second == 2097152.0
    assert entry.last_progress_at is not None


def test_cache_manager_uses_sqlite_instead_of_json_files(tmp_path):
    manager = build_manager(tmp_path)
    cache_key = manager.build_cache_key_from_parts("abcdef1234567890abcdef1234567890abcdef12", 1)

    manager.mark_downloading(cache_key)

    assert (tmp_path / "cache.sqlite").exists()
    assert list(tmp_path.glob("*/*.json")) == []
