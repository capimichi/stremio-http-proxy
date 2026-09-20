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
        content_id: str,
        content_type: str | None = None,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        source_link: str | None = None,
        infohash: str | None = None,
        file_index: int | None = None,
    ) -> PlaybackHistory:
        with self.db_manager.session() as session:
            entry = PlaybackHistory(
                content_id=content_id,
                content_type=content_type,
                title=title,
                poster=poster,
                category=category,
                source_link=source_link,
                infohash=infohash,
                file_index=file_index,
                played_at=time.time(),
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

            # Deduplicate by content_id preserving order (most recent first)
            seen_content_ids = set()
            unique_recent = []
            for record in all_records:
                if record.content_id not in seen_content_ids:
                    seen_content_ids.add(record.content_id)
                    unique_recent.append(record)
                    if len(unique_recent) >= limit:
                        break
            return unique_recent

    def get_latest_playback(self) -> PlaybackHistory | None:
        with self.db_manager.session() as session:
            query = select(PlaybackHistory).order_by(desc(PlaybackHistory.played_at)).limit(1)
            return session.scalar(query)
