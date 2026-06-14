import time

from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stremio_http_proxy.entity.cache_entry import Base


class WhitelistEntry(Base):
    __tablename__ = "whitelist_entries"
    __table_args__ = (
        UniqueConstraint("infohash", "imdb_id", "season", "episode", name="uq_whitelist_entry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    infohash: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    imdb_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    media_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
