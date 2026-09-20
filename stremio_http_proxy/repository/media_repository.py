import time
from injector import inject
from sqlalchemy import delete, desc, func, select

from stremio_http_proxy.entity.media import Media
from stremio_http_proxy.entity.media_item import MediaItem
from stremio_http_proxy.manager.db_manager import DbManager


class MediaRepository:
    @inject
    def __init__(self, db_manager: DbManager):
        self.db_manager = db_manager

    def get_media(self, media_id: str) -> Media | None:
        with self.db_manager.session() as session:
            return session.get(Media, media_id)

    def upsert_media(
        self,
        media_id: str,
        media_type: str,
        title: str,
        year: str | None = None,
        poster: str | None = None,
        backdrop: str | None = None,
        overview: str | None = None,
    ) -> Media:
        now = time.time()
        with self.db_manager.session() as session:
            media = session.get(Media, media_id)
            if media is None:
                media = Media(
                    id=media_id,
                    type=media_type,
                    title=title,
                    year=year,
                    poster=poster,
                    backdrop=backdrop,
                    overview=overview,
                    created_at=now,
                    last_accessed_at=now,
                )
                session.add(media)
            else:
                if title and title != "Senza titolo":
                    media.title = title
                if year:
                    media.year = year
                if poster:
                    media.poster = poster
                if backdrop:
                    media.backdrop = backdrop
                if overview:
                    media.overview = overview
                media.last_accessed_at = now

            session.flush()
            session.refresh(media)
            return media

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

    def list_media(
        self,
        media_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Media]:
        with self.db_manager.session() as session:
            query = select(Media)
            if media_type:
                query = query.where(Media.type == media_type)
            query = query.order_by(desc(Media.last_accessed_at)).limit(limit).offset(offset)
            return list(session.scalars(query))

    def count_media(self, media_type: str | None = None) -> int:
        with self.db_manager.session() as session:
            query = select(func.count(Media.id))
            if media_type:
                query = query.where(Media.type == media_type)
            return session.scalar(query) or 0

    def get_items_for_media(self, media_id: str) -> list[MediaItem]:
        with self.db_manager.session() as session:
            query = (
                select(MediaItem)
                .where(MediaItem.media_id == media_id)
                .order_by(MediaItem.season, MediaItem.episode)
            )
            return list(session.scalars(query))

    def delete_media(self, media_id: str) -> bool:
        with self.db_manager.session() as session:
            # Delete child media_items first
            session.execute(delete(MediaItem).where(MediaItem.media_id == media_id))
            result = session.execute(delete(Media).where(Media.id == media_id))
            return result.rowcount > 0
