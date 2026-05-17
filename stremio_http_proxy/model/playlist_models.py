from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TorrentJob(BaseModel):
    infohash: str
    magnet: str
    name: str
    status: str = "registered"
    added_at: str = Field(default_factory=utc_now)
    last_access_at: str = Field(default_factory=utc_now)
    segments: list[str] = Field(default_factory=list)
    storage_path: str | None = None


class PlaylistResponse(BaseModel):
    infohash: str
    segment_count: int
    playlist_url: str
