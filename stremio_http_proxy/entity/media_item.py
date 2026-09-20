from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stremio_http_proxy.entity.base import Base


class MediaItem(Base):
    __tablename__ = "media_items"
    __table_args__ = (
        Index("ix_media_items_media_id", "media_id"),
        Index("ix_media_items_last_accessed_at", "last_accessed_at"),
        UniqueConstraint("media_id", "season", "episode", name="uq_media_items_season_episode"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    media_id: Mapped[str] = mapped_column(String(128), ForeignKey("media.id", ondelete="CASCADE"), nullable=False)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    last_accessed_at: Mapped[float] = mapped_column(Float, nullable=False)
