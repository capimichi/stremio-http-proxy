from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CacheEntry(Base):
    __tablename__ = "cache_entries"
    __table_args__ = (
        Index("ix_cache_entries_status", "status"),
        Index("ix_cache_entries_last_accessed_at", "last_accessed_at"),
        Index("ix_cache_entries_infohash_cache_index", "infohash", "cache_index", unique=True),
    )

    cache_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    infohash: Mapped[str] = mapped_column(String(40), nullable=False)
    cache_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    tmp_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_accessed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    downloaded_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    download_speed_bytes_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_progress_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
