from typing import Any
from injector import inject

from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService
from stremio_http_proxy.task.abstract_task import AbstractTask


class FetchNextEpisodeTask(AbstractTask):
    name = "fetch_next_episode"

    @inject
    def __init__(self, prefetch_service: NextEpisodePrefetchService):
        self.prefetch_service = prefetch_service

    async def run(self, arguments: dict[str, Any]) -> bool:
        content_type = arguments.get("content_type")
        content_id = arguments.get("content_id")
        category = arguments.get("category")

        # Skip if not series or missing content_id
        if content_type != "series" or not content_id:
            return True

        if not self.prefetch_service.enabled:
            return True

        return await self.prefetch_service.enqueue_next_episode(content_type, content_id, category)
