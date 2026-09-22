import time
from injector import inject
from sqlalchemy import select

from stremio_http_proxy.entity.media import Media
from stremio_http_proxy.entity.media_item import MediaItem
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.helper.content_id_helper import parse_content_id


class MediaItemRepository:
    @inject
    def __init__(self, db_manager: DbManager):
        self.db_manager = db_manager

    def get_media_item(self, item_id: int) -> MediaItem | None:
        with self.db_manager.session() as session:
            return session.get(MediaItem, item_id)

    def get_by_content_id(
        self, content_id: str | None, content_type: str | None = None
    ) -> MediaItem | None:
        if not content_id:
            return None
        media_imdb_id, _, season, episode, _ = parse_content_id(content_id, content_type)
        with self.db_manager.session() as session:
            if season is not None and episode is not None:
                query = (
                    select(MediaItem)
                    .join(Media, MediaItem.media_id == Media.id)
                    .where(
                        Media.imdb_id == media_imdb_id,
                        MediaItem.season == season,
                        MediaItem.episode == episode,
                    )
                )
                item = session.scalars(query).first()
                if item is not None:
                    return item

            # Movie or fallback lookup
            query = (
                select(MediaItem)
                .join(Media, MediaItem.media_id == Media.id)
                .where(Media.imdb_id == media_imdb_id)
            )
            return session.scalars(query).first()

    def get_media_item_by_season_episode(
        self, media_id: int, season: int | None, episode: int | None
    ) -> MediaItem | None:
        with self.db_manager.session() as session:
            query = select(MediaItem).where(
                MediaItem.media_id == media_id,
                MediaItem.season == season,
                MediaItem.episode == episode,
            )
            return session.scalars(query).first()

    def get_items_for_media(self, media_id: int) -> list[MediaItem]:
        with self.db_manager.session() as session:
            query = (
                select(MediaItem)
                .where(MediaItem.media_id == media_id)
                .order_by(MediaItem.season, MediaItem.episode)
            )
            return list(session.scalars(query))

    def upsert_media_item(
        self,
        media_id: int,
        season: int | None = None,
        episode: int | None = None,
        title: str | None = None,
        overview: str | None = None,
        thumbnail: str | None = None,
        release_date: str | None = None,
        item_id: int | None = None,
    ) -> MediaItem:
        now = time.time()
        with self.db_manager.session() as session:
            item = None
            if item_id is not None:
                item = session.get(MediaItem, item_id)

            if item is None:
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
                    media_id=media_id,
                    season=season,
                    episode=episode,
                    title=title,
                    overview=overview,
                    thumbnail=thumbnail,
                    release_date=release_date,
                    created_at=now,
                    last_accessed_at=now,
                )
                session.add(item)
            else:
                if title:
                    item.title = title
                if overview:
                    item.overview = overview
                if thumbnail:
                    item.thumbnail = thumbnail
                if release_date:
                    item.release_date = release_date
                item.last_accessed_at = now

            session.flush()
            session.refresh(item)
            return item
