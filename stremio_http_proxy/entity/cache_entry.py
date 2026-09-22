from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from stremio_http_proxy.entity.base import Base


class CacheEntry(Base):
    __tablename__ = "cache_entries"
    __table_args__ = (
        Index("ix_cache_entries_status", "status"),
        Index("ix_cache_entries_last_accessed_at", "last_accessed_at"),
        Index("ix_cache_entries_infohash_cache_index", "infohash", "cache_index", unique=True),
        Index("ix_cache_entries_media_item_id", "media_item_id"),
    )

    cache_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    infohash: Mapped[str] = mapped_column(String(40), nullable=False)
    cache_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    tmp_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_accessed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    downloaded_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    expected_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    download_speed_bytes_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_progress_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True, default=100)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True, default=3)
    trigger: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    media_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True
    )
    available_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    claimed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    processing_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
