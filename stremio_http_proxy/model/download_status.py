from pydantic import BaseModel


class DownloadStatus(BaseModel):
    cache_key: str
    infohash: str
    index: int
    status: str
    created_at: float | None = None
    completed_at: float | None = None
    downloaded_bytes: int
    expected_bytes: int | None = None
    progress_percent: float | None = None
    download_speed_bytes_per_second: float | None = None
    attempt: int = 0
    last_error: str | None = None
    last_progress_at: float | None = None


class DownloadStatusResponse(BaseModel):
    manifest_url: str
    downloads: list[DownloadStatus]
