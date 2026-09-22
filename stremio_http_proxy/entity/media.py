from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from stremio_http_proxy.entity.base import Base


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        Index("ix_media_type", "type"),
        Index("ix_media_last_accessed_at", "last_accessed_at"),
        Index("ix_media_imdb_id", "imdb_id", unique=True),
        Index("ix_media_tmdb_id", "tmdb_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    imdb_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    tmdb_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # "series" or "movie"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    poster: Mapped[str | None] = mapped_column(Text, nullable=True)
    backdrop: Mapped[str | None] = mapped_column(Text, nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    last_accessed_at: Mapped[float] = mapped_column(Float, nullable=False)
