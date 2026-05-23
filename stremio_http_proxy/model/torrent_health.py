from pydantic import BaseModel


class TorrentHealth(BaseModel):
    stat: int | None = None
    stat_string: str | None = None
    connected_seeders: int | None = None
    total_peers: int | None = None
    download_speed: float | None = None
    progress_pct: float | None = None
