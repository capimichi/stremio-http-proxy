import time
from typing import Any
from injector import inject

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.repository.playback_history_repository import PlaybackHistoryRepository
from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService
from stremio_http_proxy.service.task_service import TaskService


class HubService:
    @inject
    def __init__(
        self,
        playback_history_repository: PlaybackHistoryRepository,
        cache_manager: CacheManager,
        next_episode_prefetch_service: NextEpisodePrefetchService,
        task_service: TaskService | None = None,
    ):
        self.playback_history_repository = playback_history_repository
        self.cache_manager = cache_manager
        self.prefetch_service = next_episode_prefetch_service
        self.task_service = task_service

    def get_recent_media(self, limit: int = 10) -> list[dict[str, Any]]:
        recent_records = self.playback_history_repository.list_recent(limit=limit)
        results = []

        for record in recent_records:
            entries = self.cache_manager.get_entries_for_content(record.content_id)

            # If no direct match by content_id, also check if source_link has an entry
            if not entries and record.source_link:
                link_entry = self.cache_manager.get_entry_by_link(record.source_link, record.file_index)
                if link_entry and link_entry.status != CacheEntryStatusEnum.MISSING:
                    entries = [(link_entry.cache_key, link_entry)]

            streams = []
            has_ready = False
            has_downloading = False
            has_queued = False
            active_stream = None

            for cache_key, entry in entries:
                infohash, index = self.cache_manager.parse_cache_key(cache_key)
                st_data = {
                    "cache_key": cache_key,
                    "infohash": infohash,
                    "index": index,
                    "status": entry.status,
                    "title": entry.title or record.title,
                    "size_bytes": entry.size_bytes if entry.status == CacheEntryStatusEnum.READY else entry.downloaded_bytes,
                    "expected_bytes": entry.expected_bytes,
                    "progress_percent": entry.progress_percent,
                    "speed_bps": entry.download_speed_bytes_per_second,
                    "last_error": entry.last_error,
                }
                streams.append(st_data)

                if entry.status == CacheEntryStatusEnum.READY:
                    has_ready = True
                elif entry.status in {CacheEntryStatusEnum.DOWNLOADING, CacheEntryStatusEnum.PROCESSING}:
                    has_downloading = True
                    if active_stream is None or (entry.progress_percent or 0) > (active_stream.get("progress_percent") or 0):
                        active_stream = st_data
                elif entry.status == CacheEntryStatusEnum.QUEUED:
                    has_queued = True
                    if active_stream is None:
                        active_stream = st_data

            if has_ready:
                agg_status = "ready"
            elif has_downloading:
                agg_status = "downloading"
            elif has_queued:
                agg_status = "queued"
            elif entries:
                agg_status = entries[0][1].status
            else:
                agg_status = "not_cached"

            # Parse season / episode from content_id if available (e.g. tt1234567:1:3)
            season = None
            episode = None
            imdb_id = record.content_id
            if ":" in record.content_id:
                parts = record.content_id.split(":")
                imdb_id = parts[0]
                if len(parts) >= 3:
                    try:
                        season = int(parts[1])
                        episode = int(parts[2])
                    except (ValueError, TypeError):
                        pass

            # Build stremio url
            if record.content_type == "movie":
                stremio_url = f"stremio://detail/movie/{imdb_id}"
            elif season is not None and episode is not None:
                stremio_url = f"stremio://detail/series/{imdb_id}/{season}/{episode}"
            else:
                stremio_url = f"stremio://detail/series/{imdb_id}"

            results.append({
                "id": record.id,
                "content_id": record.content_id,
                "imdb_id": imdb_id,
                "season": season,
                "episode": episode,
                "content_type": record.content_type or ("series" if season is not None else "movie"),
                "title": record.title or "Senza titolo",
                "poster": record.poster,
                "category": record.category,
                "played_at": record.played_at,
                "played_at_str": time.strftime("%d/%m/%Y %H:%M", time.localtime(record.played_at)),
                "status": agg_status,
                "streams_count": len(streams),
                "streams": streams,
                "active_stream": active_stream,
                "stremio_url": stremio_url,
            })

        return results

    def get_media_streams(self, content_id: str) -> list[dict[str, Any]]:
        entries = self.cache_manager.get_entries_for_content(content_id)
        results = []
        for cache_key, entry in entries:
            infohash, index = self.cache_manager.parse_cache_key(cache_key)
            results.append({
                "cache_key": cache_key,
                "infohash": infohash,
                "index": index,
                "title": entry.title,
                "status": entry.status,
                "size_bytes": entry.size_bytes if entry.status == CacheEntryStatusEnum.READY else entry.downloaded_bytes,
                "expected_bytes": entry.expected_bytes,
                "progress_percent": entry.progress_percent,
                "download_speed": entry.download_speed_bytes_per_second,
                "created_at": entry.created_at,
                "completed_at": entry.completed_at,
                "last_error": entry.last_error,
            })
        return results

    def cache_season(
        self,
        content_id: str,
        season: int,
        total_episodes: int,
        category: str = "tv",
    ) -> dict[str, Any]:
        enqueued_count = 0
        clean_id = content_id.split(":")[0]

        for ep in range(1, total_episodes + 1):
            ep_content_id = f"{clean_id}:{season}:{ep}"
            if self.task_service and hasattr(self.task_service, "enqueue_task"):
                self.task_service.enqueue_task(
                    name="fetch_media",
                    arguments={
                        "content_type": "series",
                        "content_id": ep_content_id,
                        "category": category,
                    },
                    delay_seconds=0,
                )
                enqueued_count += 1
            else:
                self.prefetch_service.schedule_prefetch(
                    content_type="series",
                    content_id=ep_content_id,
                    category=category,
                    delay_seconds=0,
                )
                enqueued_count += 1

        return {
            "success": True,
            "content_id": clean_id,
            "season": season,
            "total_episodes": total_episodes,
            "enqueued_count": enqueued_count,
        }

    def cache_episode(
        self,
        content_id: str,
        season: int | None = None,
        episode: int | None = None,
        content_type: str = "series",
        category: str | None = None,
    ) -> dict[str, Any]:
        clean_id = content_id.split(":")[0]
        if content_type == "series" and season is not None and episode is not None:
            full_content_id = f"{clean_id}:{season}:{episode}"
            cat = category or "tv"
        else:
            full_content_id = clean_id
            cat = category or ("movie" if content_type == "movie" else "tv")

        if self.task_service and hasattr(self.task_service, "enqueue_task"):
            job_id = self.task_service.enqueue_task(
                name="fetch_media",
                arguments={
                    "content_type": content_type,
                    "content_id": full_content_id,
                    "category": cat,
                },
                delay_seconds=0,
            )
        else:
            job_id = self.prefetch_service.schedule_prefetch(
                content_type=content_type,
                content_id=full_content_id,
                category=cat,
                delay_seconds=0,
            )

        return {
            "success": True,
            "content_id": full_content_id,
            "job_id": job_id,
        }

    def delete_stream(self, cache_key: str) -> dict[str, Any]:
        self.cache_manager.delete_entry(cache_key, reason="manual_user_request")
        return {"success": True, "cache_key": cache_key}
