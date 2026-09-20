from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from stremio_http_proxy.entity.cache_entry import Base


class PlaybackHistory(Base):
    __tablename__ = "playback_history"
    __table_args__ = (
        Index("ix_playback_history_content_id", "content_id"),
        Index("ix_playback_history_played_at", "played_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[str] = mapped_column(String(128), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    infohash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    file_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    played_at: Mapped[float] = mapped_column(Float, nullable=False)
