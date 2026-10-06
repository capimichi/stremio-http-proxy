import asyncio
from typing import Any
from celery import shared_task
from injector import inject

from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService
from stremio_http_proxy.task.abstract_task import AbstractTask


class FetchNextEpisodeTask(AbstractTask):
    task_name = "stremio_http_proxy.task.fetch_next_episode_task"
    name = "fetch_next_episode"

    @inject
    def __init__(self, prefetch_service: NextEpisodePrefetchService):
        self.prefetch_service = prefetch_service

    async def run(self, arguments: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> bool:
        params = dict(arguments or {})
        params.update(kwargs)
        content_type = params.get("content_type")
        content_id = params.get("content_id")
        category = params.get("category")

        # Skip if not series or missing content_id
        if content_type != "series" or not content_id:
            return True

        if not self.prefetch_service.enabled:
            return True

        return await self.prefetch_service.enqueue_next_episode(content_type, content_id, category)


@shared_task(name="stremio_http_proxy.task.fetch_next_episode_task", bind=True, max_retries=2)
def fetch_next_episode_task(self, content_type: str, content_id: str, category: str | None = None):
    from stremio_http_proxy.container.default_container import DefaultContainer

    container = DefaultContainer.getInstance()
    try:
        task: FetchNextEpisodeTask = container.get(FetchNextEpisodeTask)
        return asyncio.run(task.run({"content_type": content_type, "content_id": content_id, "category": category}))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
