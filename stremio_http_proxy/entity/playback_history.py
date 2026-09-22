from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from stremio_http_proxy.entity.base import Base


class PlaybackHistory(Base):
    __tablename__ = "playback_history"
    __table_args__ = (
        Index("ix_playback_history_media_item_id", "media_item_id"),
        Index("ix_playback_history_media_id", "media_id"),
        Index("ix_playback_history_played_at", "played_at"),
        Index("ix_playback_history_content_id", "content_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media_items.id", ondelete="CASCADE"), nullable=True
    )
    media_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=True
    )
    content_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    infohash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    file_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    played_at: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    progress_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
