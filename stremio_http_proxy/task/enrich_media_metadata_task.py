import asyncio
from typing import Any
from celery import shared_task
from injector import inject

from stremio_http_proxy.service.media_metadata_service import MediaMetadataService
from stremio_http_proxy.task.abstract_task import AbstractTask


class EnrichMediaMetadataTask(AbstractTask):
    task_name = "stremio_http_proxy.task.enrich_media_metadata_task"
    name = "enrich_media_metadata"

    @inject
    def __init__(self, media_metadata_service: MediaMetadataService):
        self.media_metadata_service = media_metadata_service

    async def run(self, arguments: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> bool:
        params = dict(arguments or {})
        params.update(kwargs)
        media_id = params.get("media_id")
        media_type = params.get("media_type", "movie")
        season = params.get("season")
        imdb_id = params.get("imdb_id")
        if not media_id and not imdb_id:
            return False
        return await self.media_metadata_service.enrich_from_tmdb(media_id or imdb_id, media_type, season=season, imdb_id=imdb_id)


@shared_task(name="stremio_http_proxy.task.enrich_media_metadata_task", bind=True, max_retries=2)
def enrich_media_metadata_task(self, media_id: int | None = None, media_type: str = "movie", season: int | None = None, imdb_id: str | None = None):
    from stremio_http_proxy.container.default_container import DefaultContainer

    container = DefaultContainer.getInstance()
    try:
        task: EnrichMediaMetadataTask = container.get(EnrichMediaMetadataTask)
        return asyncio.run(task.run({"media_id": media_id, "media_type": media_type, "season": season, "imdb_id": imdb_id}))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
