import time

from injector import inject
from sqlalchemy import select

from stremio_http_proxy.entity.whitelist_entry import WhitelistEntry
from stremio_http_proxy.manager.db_manager import DbManager


class WhitelistRepository:
    @inject
    def __init__(self, db_manager: DbManager):
        self.db_manager = db_manager

    def add_entry(
        self,
        infohash: str,
        imdb_id: str,
        media_title: str | None = None,
        season: int | None = None,
        episode: int | None = None,
    ) -> WhitelistEntry:
        with self.db_manager.session() as session:
            entry = WhitelistEntry(
                infohash=infohash,
                imdb_id=imdb_id,
                media_title=media_title,
                season=season,
                episode=episode,
                created_at=time.time(),
            )
            session.add(entry)
            session.flush()
            session.refresh(entry)
            return entry

    def remove_entry(self, entry_id: int) -> bool:
        with self.db_manager.session() as session:
            entry = session.get(WhitelistEntry, entry_id)
            if entry is None:
                return False
            session.delete(entry)
            return True

    def list_entries(
        self,
        search: str | None = None,
        season: int | None = None,
        episode: int | None = None,
        infohash: str | None = None,
        imdb_id: str | None = None,
    ) -> list[WhitelistEntry]:
        with self.db_manager.session() as session:
            query = select(WhitelistEntry).order_by(WhitelistEntry.created_at.desc())
            if search is not None:
                like = f"%{search.lower()}%"
                query = query.where(
                    WhitelistEntry.imdb_id.ilike(like) |
                    WhitelistEntry.media_title.ilike(like)
                )
            if season is not None:
                query = query.where(WhitelistEntry.season == season)
            if episode is not None:
                query = query.where(WhitelistEntry.episode == episode)
            if infohash is not None:
                query = query.where(WhitelistEntry.infohash == infohash)
            if imdb_id is not None:
                query = query.where(WhitelistEntry.imdb_id == imdb_id)
            return list(session.scalars(query))

    def get_allowed_infohashes(
        self,
        imdb_id: str,
        season: int | None = None,
        episode: int | None = None,
    ) -> set[str]:
        with self.db_manager.session() as session:
            query = select(WhitelistEntry.infohash).where(
                WhitelistEntry.imdb_id == imdb_id,
            ).where(
                (WhitelistEntry.season.is_(None)) & (WhitelistEntry.episode.is_(None))
                | (WhitelistEntry.season == season) & (WhitelistEntry.episode.is_(None))
                | (WhitelistEntry.season == season) & (WhitelistEntry.episode == episode)
            )
            return set(session.scalars(query))
