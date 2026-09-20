from sqlalchemy import Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from stremio_http_proxy.entity.cache_entry import Base


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        Index("ix_media_type", "type"),
        Index("ix_media_last_accessed_at", "last_accessed_at"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # "series" or "movie"
    title: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    poster: Mapped[str | None] = mapped_column(Text, nullable=True)
    backdrop: Mapped[str | None] = mapped_column(Text, nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    last_accessed_at: Mapped[float] = mapped_column(Float, nullable=False)
