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

    def get_media(self, media_id: int) -> Media | None:
        with self.db_manager.session() as session:
            return session.get(Media, media_id)

    def get_by_imdb_id(self, imdb_id: str | None) -> Media | None:
        if not imdb_id:
            return None
        with self.db_manager.session() as session:
            query = select(Media).where(Media.imdb_id == imdb_id)
            return session.scalars(query).first()

    def get_by_tmdb_id(self, tmdb_id: str | None) -> Media | None:
        if not tmdb_id:
            return None
        with self.db_manager.session() as session:
            query = select(Media).where(Media.tmdb_id == tmdb_id)
            return session.scalars(query).first()

    def upsert_media(
        self,
        media_type: str,
        title: str,
        imdb_id: str | None = None,
        tmdb_id: str | None = None,
        year: str | None = None,
        poster: str | None = None,
        backdrop: str | None = None,
        overview: str | None = None,
        media_id: int | None = None,
    ) -> Media:
        now = time.time()
        with self.db_manager.session() as session:
            media = None
            if media_id is not None:
                media = session.get(Media, media_id)
            if media is None and imdb_id:
                media = session.scalars(select(Media).where(Media.imdb_id == imdb_id)).first()
            if media is None and tmdb_id:
                media = session.scalars(select(Media).where(Media.tmdb_id == tmdb_id)).first()

            if media is None:
                media = Media(
                    imdb_id=imdb_id,
                    tmdb_id=tmdb_id,
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
                if imdb_id and not media.imdb_id:
                    media.imdb_id = imdb_id
                if tmdb_id and not media.tmdb_id:
                    media.tmdb_id = tmdb_id
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

    def delete_media(self, media_id: int) -> bool:
        with self.db_manager.session() as session:
            session.execute(delete(MediaItem).where(MediaItem.media_id == media_id))
            result = session.execute(delete(Media).where(Media.id == media_id))
            return result.rowcount > 0
