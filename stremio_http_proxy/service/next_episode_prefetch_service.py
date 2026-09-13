import httpx

from injector import inject

from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.service.download_queue_service import DownloadQueueService
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


class NextEpisodePrefetchService:
    @inject
    def __init__(
        self,
        upstream_client: UpstreamClient,
        stream_rewrite_service: StreamRewriteService,
        download_queue_service: DownloadQueueService,
        cache_manager: CacheManager | None = None,
        enabled: bool = True,
        stream_limit: int = 3,
        target_completed_per_episode: int = 1,
        skip_zero_seeders: bool = True,
    ):
        self.upstream_client = upstream_client
        self.stream_rewrite_service = stream_rewrite_service
        self.download_queue_service = download_queue_service
        self.cache_manager = cache_manager
        self.enabled = enabled
        self.stream_limit = stream_limit
        self.target_completed_per_episode = target_completed_per_episode
        self.skip_zero_seeders = skip_zero_seeders

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
            if self.cache_manager and hasattr(self.cache_manager, "count_active_or_ready_for_content"):
                active_or_ready = self.cache_manager.count_active_or_ready_for_content(next_content_id)
                if active_or_ready >= self.target_completed_per_episode:
                    return

            try:
                stream_payload = await self.upstream_client.get_json(f"/stream/{content_type}/{next_content_id}.json")
            except httpx.HTTPStatusError:
                continue

            enqueued = await self.enqueue_candidate_for_content(
                content_type, next_content_id, category, stream_payload=stream_payload
            )
            # If candidate enqueued or episode has streams, we found the right episode — don't fallback to next season
            if enqueued or stream_payload.get("streams"):
                return

    async def enqueue_candidate_for_content(
        self,
        content_type: str,
        content_id: str,
        category: str | None,
        stream_payload: dict | None = None,
    ) -> bool:
        if not self.enabled:
            return False

        if self.cache_manager and hasattr(self.cache_manager, "count_active_or_ready_for_content"):
            active_or_ready = self.cache_manager.count_active_or_ready_for_content(content_id)
            if active_or_ready >= self.target_completed_per_episode:
                return False
        else:
            active_or_ready = 0

        needed = max(1, self.target_completed_per_episode - active_or_ready)

        if stream_payload is None:
            try:
                stream_payload = await self.upstream_client.get_json(f"/stream/{content_type}/{content_id}.json")
            except httpx.HTTPStatusError:
                return False

        candidates = self.stream_rewrite_service.extract_download_candidates(stream_payload)
        if not candidates:
            return False

        # Filter out 0-seeder streams if skip_zero_seeders is True
        if self.skip_zero_seeders:
            candidates = [c for c in candidates if c.get("seeders") != 0]

        # Prioritize candidates with higher seeders (unknown seeders treated as lower than positive)
        candidates.sort(
            key=lambda c: (1 if c.get("seeders") is not None else 0, c.get("seeders") or 0),
            reverse=True,
        )

        enqueued_count = 0
        for candidate in candidates:
            if self.cache_manager and hasattr(self.cache_manager, "build_cache_key") and hasattr(self.cache_manager, "is_candidate_attempted"):
                cache_key = self.cache_manager.build_cache_key(candidate["link"], candidate.get("index"))
                if cache_key and self.cache_manager.is_candidate_attempted(cache_key):
                    continue

            await self.download_queue_service.enqueue_download(
                link=candidate["link"],
                title=candidate.get("title"),
                poster=candidate.get("poster"),
                category=category,
                index=candidate.get("index"),
                priority=20,
                trigger="next_episode_prefetch",
                content_type=content_type,
                content_id=content_id,
            )
            enqueued_count += 1
            if enqueued_count >= needed:
                break

        return enqueued_count > 0

    async def on_download_failed(
        self,
        content_type: str | None,
        content_id: str | None,
        category: str | None,
    ) -> None:
        if not content_type or not content_id:
            return
        await self.enqueue_candidate_for_content(content_type, content_id, category)

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
