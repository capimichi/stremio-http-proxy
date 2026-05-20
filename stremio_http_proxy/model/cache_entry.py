from pydantic import BaseModel

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum


class CacheEntry(BaseModel):
    status: str = CacheEntryStatusEnum.MISSING
    title: str | None = None
    source_link: str | None = None
    poster: str | None = None
    category: str | None = None
    file_path: str
    tmp_path: str
    created_at: float | None = None
    last_accessed_at: float | None = None
    completed_at: float | None = None
    size_bytes: int = 0
    downloaded_bytes: int = 0
    expected_bytes: int | None = None
    progress_percent: float | None = None
    download_speed_bytes_per_second: float | None = None
    last_progress_at: float | None = None
    priority: int = 100
    attempt: int = 0
    max_attempts: int = 3
    trigger: str | None = None
    content_type: str | None = None
    content_id: str | None = None
    available_at: float | None = None
    claimed_at: float | None = None
    claimed_by: str | None = None
    processing_expires_at: float | None = None
    last_error: str | None = None
