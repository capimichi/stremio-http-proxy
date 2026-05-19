import time
from pathlib import Path

from injector import inject

from stremio_http_proxy.helper.hash_helper import extract_infohash, normalize_infohash
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.model.cache_entry import CacheEntry


class CacheManager:
    @inject
    def __init__(
        self,
        base_dir: str,
        max_age_days: int,
        max_size_gb: int,
        logger_factory: LoggerFactory,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_days = max_age_days
        self.max_size_bytes = max_size_gb * 1024 * 1024 * 1024
        self.logger = logger_factory.get_logger("stremio_http_proxy.cache", "cache.log")

    def build_cache_key(self, link: str, index: int | None = None) -> str | None:
        infohash = extract_infohash(link)
        if infohash is None:
            return None
        normalized = normalize_infohash(infohash)
        return f"{normalized}:{index or 0}"

    def build_cache_key_from_parts(self, infohash: str, index: int | None = None) -> str:
        return f"{normalize_infohash(infohash)}:{index or 0}"

    def parse_cache_key(self, cache_key: str) -> tuple[str, int]:
        infohash, raw_index = cache_key.split(":", 1)
        return infohash, int(raw_index)

    def get_entry_by_link(self, link: str, index: int | None = None) -> CacheEntry | None:
        cache_key = self.build_cache_key(link, index)
        if cache_key is None:
            return None
        return self.get_entry(cache_key)

    def get_entry(self, cache_key: str) -> CacheEntry:
        infohash, index = self.parse_cache_key(cache_key)
        metadata_path = self._metadata_path(infohash, index)
        media_path = self._media_path(infohash, index)
        tmp_path = self._tmp_path(infohash, index)
        if not metadata_path.exists():
            return CacheEntry(file_path=str(media_path), tmp_path=str(tmp_path))

        return CacheEntry.model_validate_json(metadata_path.read_text())

    def is_ready(self, cache_key: str) -> bool:
        entry = self.get_entry(cache_key)
        return entry.status == "ready" and Path(entry.file_path).exists()

    def mark_downloading(self, cache_key: str, attempt: int = 0) -> CacheEntry:
        entry = self.get_entry(cache_key)
        now = time.time()
        updated = entry.model_copy(
            update={
                "status": "downloading",
                "created_at": entry.created_at or now,
                "last_accessed_at": now,
                "downloaded_bytes": 0,
                "expected_bytes": None,
                "progress_percent": None,
                "download_speed_bytes_per_second": None,
                "last_progress_at": now,
                "attempt": attempt,
                "last_error": None,
            }
        )
        self._write_entry(cache_key, updated)
        return updated

    def mark_ready(self, cache_key: str, size_bytes: int) -> CacheEntry:
        entry = self.get_entry(cache_key)
        now = time.time()
        updated = entry.model_copy(
            update={
                "status": "ready",
                "completed_at": now,
                "last_accessed_at": now,
                "size_bytes": size_bytes,
                "downloaded_bytes": size_bytes,
                "progress_percent": 100.0,
                "download_speed_bytes_per_second": None,
                "last_progress_at": now,
                "last_error": None,
            }
        )
        self._write_entry(cache_key, updated)
        return updated

    def mark_failed(self, cache_key: str, error: str, attempt: int) -> CacheEntry:
        entry = self.get_entry(cache_key)
        updated = entry.model_copy(update={"status": "failed", "attempt": attempt, "last_error": error})
        self._write_entry(cache_key, updated)
        self.logger.warning("Cache entry %s failed: %s", cache_key, error)
        return updated

    def touch(self, cache_key: str) -> None:
        entry = self.get_entry(cache_key)
        updated = entry.model_copy(update={"last_accessed_at": time.time()})
        self._write_entry(cache_key, updated)

    def mark_progress(
        self,
        cache_key: str,
        downloaded_bytes: int,
        expected_bytes: int | None,
        progress_percent: float | None,
        download_speed_bytes_per_second: float,
    ) -> CacheEntry:
        entry = self.get_entry(cache_key)
        now = time.time()
        updated = entry.model_copy(
            update={
                "status": "downloading",
                "downloaded_bytes": downloaded_bytes,
                "expected_bytes": expected_bytes,
                "progress_percent": progress_percent,
                "download_speed_bytes_per_second": download_speed_bytes_per_second,
                "last_progress_at": now,
                "last_accessed_at": now,
            }
        )
        self._write_entry(cache_key, updated)
        return updated

    def prune(self) -> None:
        self._prune_by_age()
        self._prune_by_size()

    def cleanup_partial(self, cache_key: str) -> None:
        infohash, index = self.parse_cache_key(cache_key)
        tmp_path = self._tmp_path(infohash, index)
        if tmp_path.exists():
            tmp_path.unlink()

    def prepare_download_path(self, cache_key: str) -> Path:
        infohash, index = self.parse_cache_key(cache_key)
        media_path = self._media_path(infohash, index)
        media_path.parent.mkdir(parents=True, exist_ok=True)
        return self._tmp_path(infohash, index)

    def finalize_download(self, cache_key: str) -> int:
        infohash, index = self.parse_cache_key(cache_key)
        tmp_path = self._tmp_path(infohash, index)
        media_path = self._media_path(infohash, index)
        tmp_path.replace(media_path)
        return media_path.stat().st_size

    def _write_entry(self, cache_key: str, entry: CacheEntry) -> None:
        infohash, index = self.parse_cache_key(cache_key)
        metadata_path = self._metadata_path(infohash, index)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(entry.model_dump_json(indent=2))

    def _metadata_path(self, infohash: str, index: int) -> Path:
        return self.base_dir / infohash / f"{index}.json"

    def _media_path(self, infohash: str, index: int) -> Path:
        return self.base_dir / infohash / f"{index}.media"

    def _tmp_path(self, infohash: str, index: int) -> Path:
        return self.base_dir / infohash / f"{index}.part"

    def _prune_by_age(self) -> None:
        if self.max_age_days <= 0:
            return
        cutoff = time.time() - (self.max_age_days * 86400)
        for metadata_path in self.base_dir.glob("*/*.json"):
            entry = CacheEntry.model_validate_json(metadata_path.read_text())
            timestamp = entry.last_accessed_at or entry.completed_at or entry.created_at
            if timestamp and timestamp < cutoff:
                cache_key = self.build_cache_key_from_parts(metadata_path.parent.name, int(metadata_path.stem))
                self._delete_entry(cache_key, "expired")

    def _prune_by_size(self) -> None:
        if self.max_size_bytes <= 0:
            return
        entries: list[tuple[str, CacheEntry]] = []
        total_size = 0
        for metadata_path in self.base_dir.glob("*/*.json"):
            entry = CacheEntry.model_validate_json(metadata_path.read_text())
            if entry.status != "ready":
                continue
            cache_key = self.build_cache_key_from_parts(metadata_path.parent.name, int(metadata_path.stem))
            total_size += entry.size_bytes
            entries.append((cache_key, entry))

        if total_size <= self.max_size_bytes:
            return

        for cache_key, entry in sorted(entries, key=lambda item: item[1].last_accessed_at or 0):
            self._delete_entry(cache_key, "max_size")
            total_size -= entry.size_bytes
            if total_size <= self.max_size_bytes:
                return

    def _delete_entry(self, cache_key: str, reason: str) -> None:
        infohash, index = self.parse_cache_key(cache_key)
        for path in (self._metadata_path(infohash, index), self._media_path(infohash, index), self._tmp_path(infohash, index)):
            if path.exists():
                path.unlink()
        parent = self.base_dir / infohash
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
        self.logger.info("Deleted cache entry %s (%s)", cache_key, reason)
