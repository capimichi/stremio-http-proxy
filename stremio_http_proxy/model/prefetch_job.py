from pydantic import BaseModel


class PrefetchJob(BaseModel):
    id: int
    content_type: str
    content_id: str
    category: str | None = None
    status: str = "pending"
    scheduled_at: float
    created_at: float
    updated_at: float
    claimed_by: str | None = None
    claimed_at: float | None = None
    processing_expires_at: float | None = None
    attempt: int = 0
    max_attempts: int = 3
    last_error: str | None = None
