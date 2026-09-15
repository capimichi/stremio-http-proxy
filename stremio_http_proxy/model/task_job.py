from typing import Any
from pydantic import BaseModel, Field


class TaskJob(BaseModel):
    id: int
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
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
