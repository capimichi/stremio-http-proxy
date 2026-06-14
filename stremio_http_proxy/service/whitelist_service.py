from injector import inject

from stremio_http_proxy.entity.whitelist_entry import WhitelistEntry
from stremio_http_proxy.repository.whitelist_repository import WhitelistRepository


class WhitelistService:
    @inject
    def __init__(
        self,
        whitelist_repository: WhitelistRepository,
    ):
        self.whitelist_repository = whitelist_repository

    def get_whitelist_for_content(self, imdb_id: str) -> list[dict]:
        rules = self.whitelist_repository.list_entries(imdb_id=imdb_id)
        return [
            {
                "id": r.id,
                "infohash": r.infohash,
                "media_title": r.media_title,
                "season": r.season,
                "episode": r.episode,
            }
            for r in rules
        ]

    def add_to_whitelist(
        self,
        infohash: str,
        imdb_id: str,
        media_title: str | None = None,
        season: int | None = None,
        episode: int | None = None,
    ) -> WhitelistEntry:
        return self.whitelist_repository.add_entry(
            infohash=infohash,
            imdb_id=imdb_id,
            media_title=media_title,
            season=season,
            episode=episode,
        )

    def remove_from_whitelist(self, entry_id: int) -> bool:
        return self.whitelist_repository.remove_entry(entry_id)

    def list_whitelist(
        self,
        search: str | None = None,
        season: int | None = None,
        episode: int | None = None,
        infohash: str | None = None,
        imdb_id: str | None = None,
    ) -> list[dict]:
        entries = self.whitelist_repository.list_entries(
            search=search,
            season=season,
            episode=episode,
            infohash=infohash,
            imdb_id=imdb_id,
        )
        return [
            {
                "id": e.id,
                "infohash": e.infohash,
                "imdb_id": e.imdb_id,
                "media_title": e.media_title,
                "season": e.season,
                "episode": e.episode,
                "created_at": e.created_at,
            }
            for e in entries
        ]
