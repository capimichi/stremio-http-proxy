import httpx

from injector import inject

from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.service.download_queue_service import DownloadQueueService
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class NextEpisodePrefetchService:
    @inject
    def __init__(
        self,
        upstream_client: UpstreamClient,
        stream_rewrite_service: StreamRewriteService,
        download_queue_service: DownloadQueueService,
        enabled: bool = True,
        stream_limit: int = 3,
    ):
        self.upstream_client = upstream_client
        self.stream_rewrite_service = stream_rewrite_service
        self.download_queue_service = download_queue_service
        self.enabled = enabled
        self.stream_limit = stream_limit

    async def enqueue_next_episode(
        self,
        content_type: str | None,
        content_id: str | None,
        category: str | None,
    ) -> None:
        if not self.enabled:
            return
        next_candidates = self._build_next_content_ids(content_id)
        if not content_type or not next_candidates:
            return

        for next_content_id in next_candidates:
            try:
                stream_payload = await self.upstream_client.get_json(f"/stream/{content_type}/{next_content_id}.json")
            except httpx.HTTPStatusError:
                continue
            candidates = self.stream_rewrite_service.extract_download_candidates(stream_payload)
            if not candidates:
                continue
            for candidate in candidates[: self.stream_limit]:
                await self.download_queue_service.enqueue_download(
                    link=candidate["link"],
                    title=candidate.get("title"),
                    poster=candidate.get("poster"),
                    category=category,
                    index=candidate.get("index"),
                    priority=20,
                    trigger="next_episode_prefetch",
                    content_type=content_type,
                    content_id=next_content_id,
                )
            return

    def _build_next_content_ids(self, content_id: str | None) -> list[str]:
        if not isinstance(content_id, str) or not content_id.strip():
            return []
        parts = content_id.split(":")
        if len(parts) < 3 or not parts[-1].isdigit() or not parts[-2].isdigit():
            return []
        base_id = ":".join(parts[:-2])
        season = int(parts[-2])
        episode = int(parts[-1])
        return [f"{base_id}:{season}:{episode + 1}", f"{base_id}:{season + 1}:1"]
