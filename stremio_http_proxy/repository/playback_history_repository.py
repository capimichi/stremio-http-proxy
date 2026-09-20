import time
from injector import inject
from sqlalchemy import desc, select

from stremio_http_proxy.entity.playback_history import PlaybackHistory
from stremio_http_proxy.manager.db_manager import DbManager


class PlaybackHistoryRepository:
    @inject
    def __init__(self, db_manager: DbManager):
        self.db_manager = db_manager

    def record_playback(
        self,
        media_item_id: str | None = None,
        media_id: str | None = None,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        source_link: str | None = None,
        infohash: str | None = None,
        file_index: int | None = None,
        duration_seconds: float | None = None,
        progress_seconds: float | None = None,
        # Backward compatibility if content_id keyword arg is passed
        content_id: str | None = None,
        content_type: str | None = None,
    ) -> PlaybackHistory:
        item_id = media_item_id or content_id or ""
        resolved_media_id = media_id or (item_id.split(":")[0] if item_id else "")
        with self.db_manager.session() as session:
            entry = PlaybackHistory(
                media_item_id=item_id,
                media_id=resolved_media_id,
                title=title,
                poster=poster,
                category=category,
                source_link=source_link,
                infohash=infohash,
                file_index=file_index,
                played_at=time.time(),
                duration_seconds=duration_seconds,
                progress_seconds=progress_seconds,
            )
            session.add(entry)
            session.flush()
            session.refresh(entry)
            return entry

    def list_recent(self, limit: int = 20) -> list[PlaybackHistory]:
        with self.db_manager.session() as session:
            query = (
                select(PlaybackHistory)
                .order_by(desc(PlaybackHistory.played_at))
                .limit(limit * 3)
            )
            all_records = list(session.scalars(query))

            # Deduplicate by media_item_id preserving order (most recent first)
            seen_item_ids = set()
            unique_recent = []
            for record in all_records:
                if record.media_item_id not in seen_item_ids:
                    seen_item_ids.add(record.media_item_id)
                    unique_recent.append(record)
                    if len(unique_recent) >= limit:
                        break
            return unique_recent

    def get_latest_playback(self) -> PlaybackHistory | None:
        with self.db_manager.session() as session:
            query = select(PlaybackHistory).order_by(desc(PlaybackHistory.played_at)).limit(1)
            return session.scalar(query)
