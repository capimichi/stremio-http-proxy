from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from stremio_http_proxy.entity.base import Base


class PlaybackHistory(Base):
    __tablename__ = "playback_history"
    __table_args__ = (
        Index("ix_playback_history_media_item_id", "media_item_id"),
        Index("ix_playback_history_media_id", "media_id"),
        Index("ix_playback_history_played_at", "played_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_item_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    infohash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    file_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    played_at: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    progress_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    @property
    def content_id(self) -> str:
        return self.media_item_id

    @property
    def content_type(self) -> str:
        if self.category == "movie":
            return "movie"
        if ":" in (self.media_item_id or ""):
            return "series"
        return "movie"

