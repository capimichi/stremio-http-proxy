import time
from pathlib import Path

from injector import inject
from sqlalchemy import or_, select, update

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.entity.cache_entry import CacheEntry as CacheEntryRecord
from stremio_http_proxy.helper.hash_helper import extract_infohash, normalize_infohash
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.model.cache_entry import CacheEntry as CacheEntryModel
from stremio_http_proxy.model.download_job import DownloadJob


class CacheManager:
    @inject
    def __init__(
        self,
        base_dir: str,
        db_manager: DbManager,
        max_age_days: int,
        max_size_gb: int,
        logger_factory: LoggerFactory,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_manager = db_manager
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

    def get_entry_by_link(self, link: str, index: int | None = None) -> CacheEntryModel | None:
        cache_key = self.build_cache_key(link, index)
        if cache_key is None:
            return None
        return self.get_entry(cache_key)

    def get_entry(self, cache_key: str) -> CacheEntryModel:
        infohash, index = self.parse_cache_key(cache_key)
        media_path = self._media_path(infohash, index)
        tmp_path = self._tmp_path(infohash, index)
        with self.db_manager.session() as session:
            record = session.get(CacheEntryRecord, cache_key)
        if record is None:
            return CacheEntryModel(file_path=str(media_path), tmp_path=str(tmp_path))
        return self._to_model(record)

    def get_min_cache_size(self) -> int:
        return 10 * 1024 * 1024

    def is_ready(self, cache_key: str) -> bool:
        entry = self.get_entry(cache_key)

        if entry.status != CacheEntryStatusEnum.READY:
            return False

        min_size_bytes = self.get_min_cache_size()
        if entry.size_bytes is None or entry.size_bytes < min_size_bytes:
            return False

        return Path(entry.file_path).exists()

    def mark_downloading(self, cache_key: str, attempt: int = 0) -> CacheEntryModel:
        entry = self.get_entry(cache_key)
        now = time.time()
        updated = entry.model_copy(
            update={
                "status": CacheEntryStatusEnum.DOWNLOADING,
                "created_at": entry.created_at or now,
                "last_accessed_at": now,
                "downloaded_bytes": 0,
                "expected_bytes": None,
                "progress_percent": None,
                "download_speed_bytes_per_second": None,
                "last_progress_at": now,
                "claimed_at": now,
                "processing_expires_at": now + 180,
                "attempt": attempt,
                "last_error": None,
            }
        )
        self._write_entry(cache_key, updated)
        return updated

    def mark_ready(self, cache_key: str, size_bytes: int) -> CacheEntryModel:
        entry = self.get_entry(cache_key)
        now = time.time()
        updated = entry.model_copy(
            update={
                "status": CacheEntryStatusEnum.READY,
                "completed_at": now,
                "last_accessed_at": now,
                "size_bytes": size_bytes,
                "downloaded_bytes": size_bytes,
                "progress_percent": 100.0,
                "download_speed_bytes_per_second": None,
                "last_progress_at": now,
                "claimed_at": None,
                "claimed_by": None,
                "processing_expires_at": None,
                "available_at": None,
                "last_error": None,
            }
        )
        self._write_entry(cache_key, updated)
        return updated

    def mark_failed(self, cache_key: str, error: str, attempt: int) -> CacheEntryModel:
        entry = self.get_entry(cache_key)
        updated = entry.model_copy(
            update={
                "status": CacheEntryStatusEnum.FAILED,
                "attempt": attempt,
                "claimed_at": None,
                "claimed_by": None,
                "processing_expires_at": None,
                "last_error": error,
            }
        )
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
    ) -> CacheEntryModel:
        entry = self.get_entry(cache_key)
        now = time.time()
        updated = entry.model_copy(
            update={
                "status": CacheEntryStatusEnum.DOWNLOADING,
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

    def list_entries_by_status(self, status: str) -> list[tuple[str, CacheEntryModel]]:
        with self.db_manager.session() as session:
            records = session.scalars(
                select(CacheEntryRecord)
                .where(CacheEntryRecord.status == status)
                .order_by(CacheEntryRecord.last_progress_at.desc(), CacheEntryRecord.created_at.desc())
            ).all()
        return [(record.cache_key, self._to_model(record)) for record in records]

    def list_entries(self) -> list[tuple[str, CacheEntryModel]]:
        with self.db_manager.session() as session:
            records = session.scalars(
                select(CacheEntryRecord)
                .order_by(CacheEntryRecord.created_at.desc(), CacheEntryRecord.last_accessed_at.desc())
            ).all()
        return [(record.cache_key, self._to_model(record)) for record in records]

    async def enqueue_download(self, job: DownloadJob) -> bool:
        entry = self.get_entry(job.cache_key)
        if entry.status in {
            CacheEntryStatusEnum.QUEUED,
            CacheEntryStatusEnum.PROCESSING,
            CacheEntryStatusEnum.DOWNLOADING,
        }:
            return False

        now = time.time()
        updated = entry.model_copy(
            update={
                "status": CacheEntryStatusEnum.QUEUED,
                "title": job.title,
                "source_link": job.link,
                "poster": job.poster,
                "category": job.category,
                "created_at": now,
                "completed_at": None,
                "downloaded_bytes": 0,
                "expected_bytes": None,
                "progress_percent": None,
                "download_speed_bytes_per_second": None,
                "last_progress_at": None,
                "priority": job.priority,
                "attempt": 0,
                "max_attempts": job.max_attempts,
                "trigger": job.trigger,
                "content_type": job.content_type,
                "content_id": job.content_id,
                "available_at": job.available_at,
                "claimed_at": None,
                "claimed_by": None,
                "processing_expires_at": None,
                "last_error": None,
            }
        )
        self._write_entry(job.cache_key, updated)
        self.logger.info("Enqueued job %s for %s", job.job_id, job.cache_key)
        return True

    async def claim_next_download(self, worker_id: str, lease_seconds: int = 180) -> DownloadJob | None:
        now = time.time()
        with self.db_manager.session() as session:
            expired_records = session.scalars(
                select(CacheEntryRecord).where(
                    CacheEntryRecord.status.in_([CacheEntryStatusEnum.PROCESSING, CacheEntryStatusEnum.DOWNLOADING]),
                    CacheEntryRecord.processing_expires_at.is_not(None),
                    CacheEntryRecord.processing_expires_at <= now,
                )
            ).all()
            for record in expired_records:
                record.status = CacheEntryStatusEnum.QUEUED
                record.claimed_at = None
                record.claimed_by = None
                record.processing_expires_at = None
                record.available_at = now
                self.logger.warning("Requeued expired processing job %s", record.cache_key)

            candidates = session.scalars(
                select(CacheEntryRecord)
                .where(
                    CacheEntryRecord.status == CacheEntryStatusEnum.QUEUED,
                    or_(CacheEntryRecord.available_at.is_(None), CacheEntryRecord.available_at <= now),
                )
                .order_by(CacheEntryRecord.available_at.asc(), CacheEntryRecord.priority.desc(), CacheEntryRecord.created_at.desc())
            ).all()
            for record in candidates:
                claimed = session.execute(
                    update(CacheEntryRecord)
                    .where(
                        CacheEntryRecord.cache_key == record.cache_key,
                        CacheEntryRecord.status == CacheEntryStatusEnum.QUEUED,
                    )
                    .values(
                        status=CacheEntryStatusEnum.PROCESSING,
                        claimed_at=now,
                        claimed_by=worker_id,
                        processing_expires_at=now + lease_seconds,
                        last_accessed_at=now,
                    )
                )
                if claimed.rowcount != 1:
                    continue
                claimed_record = session.get(CacheEntryRecord, record.cache_key)
                return self._to_job(claimed_record)
        return None

    async def acknowledge_download(self, job: DownloadJob) -> None:
        entry = self.get_entry(job.cache_key)
        updated = entry.model_copy(
            update={
                "claimed_at": None,
                "claimed_by": None,
                "processing_expires_at": None,
                "available_at": None if entry.status == CacheEntryStatusEnum.READY else entry.available_at,
            }
        )
        self._write_entry(job.cache_key, updated)

    async def retry_download(self, job: DownloadJob, delay_seconds: int, error: str) -> None:
        entry = self.get_entry(job.cache_key)
        updated = entry.model_copy(
            update={
                "status": CacheEntryStatusEnum.QUEUED,
                "attempt": job.attempt + 1,
                "available_at": time.time() + delay_seconds,
                "claimed_at": None,
                "claimed_by": None,
                "processing_expires_at": None,
                "last_error": error,
            }
        )
        self._write_entry(job.cache_key, updated)
        self.logger.warning("Retrying job %s in %ss: %s", job.job_id, delay_seconds, error)

    async def move_to_dead_letter(self, job: DownloadJob, error: str) -> None:
        self.mark_failed(job.cache_key, error, job.attempt + 1)

    def touch_processing_lease(self, cache_key: str, worker_id: str, lease_seconds: int = 180) -> None:
        entry = self.get_entry(cache_key)
        if entry.claimed_by != worker_id:
            return
        now = time.time()
        updated = entry.model_copy(
            update={
                "claimed_at": now,
                "processing_expires_at": now + lease_seconds,
                "last_accessed_at": now,
            }
        )
        self._write_entry(cache_key, updated)

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

    def _write_entry(self, cache_key: str, entry: CacheEntryModel) -> None:
        infohash, index = self.parse_cache_key(cache_key)
        with self.db_manager.session() as session:
            record = session.get(CacheEntryRecord, cache_key)
            if record is None:
                record = CacheEntryRecord(cache_key=cache_key, infohash=infohash, cache_index=index)
                session.add(record)
            self._update_record(record, entry)

    def _media_path(self, infohash: str, index: int) -> Path:
        return self.base_dir / infohash / f"{index}.media"

    def _tmp_path(self, infohash: str, index: int) -> Path:
        return self.base_dir / infohash / f"{index}.part"

    def _prune_by_age(self) -> None:
        if self.max_age_days <= 0:
            return
        cutoff = time.time() - (self.max_age_days * 86400)
        with self.db_manager.session() as session:
            records = session.scalars(select(CacheEntryRecord)).all()
        for record in records:
            entry = self._to_model(record)
            timestamp = entry.last_accessed_at or entry.completed_at or entry.created_at
            if timestamp and timestamp < cutoff:
                cache_key = self.build_cache_key_from_parts(record.infohash, record.cache_index)
                self._delete_entry(cache_key, "expired")

    def _prune_by_size(self) -> None:
        if self.max_size_bytes <= 0:
            return
        entries: list[tuple[str, CacheEntryModel]] = []
        total_size = 0
        with self.db_manager.session() as session:
            records = session.scalars(select(CacheEntryRecord)).all()
        for record in records:
            entry = self._to_model(record)
            if entry.status != CacheEntryStatusEnum.READY:
                continue
            cache_key = self.build_cache_key_from_parts(record.infohash, record.cache_index)
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
        with self.db_manager.session() as session:
            record = session.get(CacheEntryRecord, cache_key)
            if record is not None:
                session.delete(record)
        for path in (self._media_path(infohash, index), self._tmp_path(infohash, index)):
            if path.exists():
                path.unlink()
        parent = self.base_dir / infohash
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
        self.logger.info("Deleted cache entry %s (%s)", cache_key, reason)

    def _to_model(self, record: CacheEntryRecord) -> CacheEntryModel:
        return CacheEntryModel(
            status=record.status,
            title=record.title,
            source_link=record.source_link,
            poster=record.poster,
            category=record.category,
            file_path=record.file_path,
            tmp_path=record.tmp_path,
            created_at=record.created_at,
            last_accessed_at=record.last_accessed_at,
            completed_at=record.completed_at,
            size_bytes=record.size_bytes,
            downloaded_bytes=record.downloaded_bytes,
            expected_bytes=record.expected_bytes,
            progress_percent=record.progress_percent,
            download_speed_bytes_per_second=record.download_speed_bytes_per_second,
            last_progress_at=record.last_progress_at,
            priority=record.priority or 100,
            attempt=record.attempt,
            max_attempts=record.max_attempts or 3,
            trigger=record.trigger,
            content_type=record.content_type,
            content_id=record.content_id,
            available_at=record.available_at,
            claimed_at=record.claimed_at,
            claimed_by=record.claimed_by,
            processing_expires_at=record.processing_expires_at,
            last_error=record.last_error,
        )

    def _to_job(self, record: CacheEntryRecord) -> DownloadJob:
        return DownloadJob(
            job_id=record.cache_key,
            cache_key=record.cache_key,
            link=record.source_link or "",
            title=record.title,
            poster=record.poster,
            category=record.category,
            index=record.cache_index,
            priority=record.priority or 100,
            attempt=record.attempt,
            max_attempts=record.max_attempts or 3,
            trigger=record.trigger or "playback",
            content_type=record.content_type,
            content_id=record.content_id,
            enqueued_at=record.created_at or time.time(),
            available_at=record.available_at or time.time(),
            last_error=record.last_error,
        )

    def _update_record(self, record: CacheEntryRecord, entry: CacheEntryModel) -> None:
        record.status = entry.status
        record.title = entry.title
        record.source_link = entry.source_link
        record.poster = entry.poster
        record.category = entry.category
        record.file_path = entry.file_path
        record.tmp_path = entry.tmp_path
        record.created_at = entry.created_at
        record.last_accessed_at = entry.last_accessed_at
        record.completed_at = entry.completed_at
        record.size_bytes = entry.size_bytes
        record.downloaded_bytes = entry.downloaded_bytes
        record.expected_bytes = entry.expected_bytes
        record.progress_percent = entry.progress_percent
        record.download_speed_bytes_per_second = entry.download_speed_bytes_per_second
        record.last_progress_at = entry.last_progress_at
        record.priority = entry.priority
        record.attempt = entry.attempt
        record.max_attempts = entry.max_attempts
        record.trigger = entry.trigger
        record.content_type = entry.content_type
        record.content_id = entry.content_id
        record.available_at = entry.available_at
        record.claimed_at = entry.claimed_at
        record.claimed_by = entry.claimed_by
        record.processing_expires_at = entry.processing_expires_at
        record.last_error = entry.last_error
