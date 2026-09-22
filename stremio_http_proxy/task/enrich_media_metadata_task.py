from typing import Any
from injector import inject

from stremio_http_proxy.service.media_metadata_service import MediaMetadataService
from stremio_http_proxy.task.abstract_task import AbstractTask


class EnrichMediaMetadataTask(AbstractTask):
    name = "enrich_media_metadata"

    @inject
    def __init__(self, media_metadata_service: MediaMetadataService):
        self.media_metadata_service = media_metadata_service

    async def run(self, arguments: dict[str, Any]) -> bool:
        media_id = arguments.get("media_id")
        media_type = arguments.get("media_type", "movie")
        season = arguments.get("season")
        imdb_id = arguments.get("imdb_id")
        if not media_id and not imdb_id:
            return False
        return await self.media_metadata_service.enrich_from_tmdb(media_id or imdb_id, media_type, season=season, imdb_id=imdb_id)
