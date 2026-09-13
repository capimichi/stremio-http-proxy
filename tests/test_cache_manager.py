from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.manager.db_manager import DbManager
import stremio_http_proxy.entity.whitelist_entry  # noqa: F401


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

    assert entry.status == CacheEntryStatusEnum.DOWNLOADING
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


def test_build_cache_key_supports_http_urls(tmp_path):
    import stremio_http_proxy.entity.whitelist_entry  # noqa: F401
    manager = build_manager(tmp_path)
    url = "https://toastflix.invalid/clone/manifest.m3u8?d=123"
    key = manager.build_cache_key(url)
    assert key is not None
    assert ":" in key
    prefix, idx = key.split(":", 1)
    assert len(prefix) == 40
    # Deterministic
    assert manager.build_cache_key(url) == key


def test_count_and_candidate_attempted(tmp_path):
    manager = build_manager(tmp_path)
    content_id = "series:tt12345:1:2"
    key1 = "1111111111111111111111111111111111111111:0"
    key2 = "2222222222222222222222222222222222222222:0"

    assert not manager.is_candidate_attempted(key1)
    assert manager.count_active_or_ready_for_content(content_id) == 0
    assert manager.count_ready_for_content(content_id) == 0

    entry1 = manager.get_entry(key1).model_copy(
        update={"status": CacheEntryStatusEnum.QUEUED, "content_id": content_id}
    )
    manager._write_entry(key1, entry1)
    assert manager.is_candidate_attempted(key1)
    assert manager.count_active_or_ready_for_content(content_id) == 1
    assert manager.count_ready_for_content(content_id) == 0

    entry1_ready = entry1.model_copy(update={"status": CacheEntryStatusEnum.READY})
    manager._write_entry(key1, entry1_ready)
    assert manager.count_active_or_ready_for_content(content_id) == 1
    assert manager.count_ready_for_content(content_id) == 1

    entry2 = manager.get_entry(key2).model_copy(
        update={"status": CacheEntryStatusEnum.DOWNLOADING, "content_id": content_id}
    )
    manager._write_entry(key2, entry2)
    assert manager.count_active_or_ready_for_content(content_id) == 2
    assert manager.count_ready_for_content(content_id) == 1

