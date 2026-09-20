import time
from injector import inject
from sqlalchemy import select

from stremio_http_proxy.entity.media_item import MediaItem
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.helper.content_id_helper import parse_content_id


class MediaItemRepository:
    @inject
    def __init__(self, db_manager: DbManager):
        self.db_manager = db_manager

    def get_by_content_id(
        self, content_id: str | None, content_type: str | None = None
    ) -> MediaItem | None:
        if not content_id:
            return None
        media_id, item_id, season, episode, _ = parse_content_id(content_id, content_type)
        with self.db_manager.session() as session:
            # 1. Direct lookup by item_id
            item = session.get(MediaItem, item_id)
            if item is not None:
                return item

            # 2. If series with season & episode, lookup by (media_id, season, episode)
            if season is not None and episode is not None:
                query = select(MediaItem).where(
                    MediaItem.media_id == media_id,
                    MediaItem.season == season,
                    MediaItem.episode == episode,
                )
                item = session.scalars(query).first()
                if item is not None:
                    return item

            # 3. For movie / single ID, lookup by media_id where season and episode are null
            if media_id:
                query = select(MediaItem).where(
                    MediaItem.media_id == media_id,
                    MediaItem.season.is_(None),
                    MediaItem.episode.is_(None),
                )
                item = session.scalars(query).first()
                if item is not None:
                    return item

                # 4. Fallback: any item for this media_id
                query = select(MediaItem).where(MediaItem.media_id == media_id).limit(1)
                return session.scalars(query).first()

            return None

    def get_media_item(self, item_id: str) -> MediaItem | None:
        with self.db_manager.session() as session:
            return session.get(MediaItem, item_id)

    def get_media_item_by_season_episode(
        self, media_id: str, season: int | None, episode: int | None
    ) -> MediaItem | None:
        with self.db_manager.session() as session:
            query = select(MediaItem).where(
                MediaItem.media_id == media_id,
                MediaItem.season == season,
                MediaItem.episode == episode,
            )
            return session.scalars(query).first()

    def get_items_for_media(self, media_id: str) -> list[MediaItem]:
        with self.db_manager.session() as session:
            query = (
                select(MediaItem)
                .where(MediaItem.media_id == media_id)
                .order_by(MediaItem.season, MediaItem.episode)
            )
            return list(session.scalars(query))

    def upsert_media_item(
        self,
        item_id: str,
        media_id: str,
        season: int | None = None,
        episode: int | None = None,
        title: str | None = None,
    ) -> MediaItem:
        now = time.time()
        with self.db_manager.session() as session:
            item = session.get(MediaItem, item_id)
            if item is None:
                # Also check by (media_id, season, episode) to prevent duplicate key constraint
                if season is not None and episode is not None:
                    existing = session.scalars(
                        select(MediaItem).where(
                            MediaItem.media_id == media_id,
                            MediaItem.season == season,
                            MediaItem.episode == episode,
                        )
                    ).first()
                    if existing is not None:
                        item = existing

            if item is None:
                item = MediaItem(
                    id=item_id,
                    media_id=media_id,
                    season=season,
                    episode=episode,
                    title=title,
                    created_at=now,
                    last_accessed_at=now,
                )
                session.add(item)
            else:
                if title:
                    item.title = title
                item.last_accessed_at = now

            session.flush()
            session.refresh(item)
            return item
