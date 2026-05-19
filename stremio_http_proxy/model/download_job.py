from pydantic import BaseModel


class DownloadJob(BaseModel):
    job_id: str
    cache_key: str
    link: str
    title: str | None = None
    poster: str | None = None
    category: str | None = None
    index: int | None = None
    priority: int = 100
    attempt: int = 0
    max_attempts: int = 3
    trigger: str = "playback"
    content_type: str | None = None
    content_id: str | None = None
    enqueued_at: float
    available_at: float
    last_error: str | None = None
