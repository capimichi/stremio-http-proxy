import time
from typing import Any
from injector import inject

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.repository.media_repository import MediaRepository
from stremio_http_proxy.repository.media_item_repository import MediaItemRepository
from stremio_http_proxy.repository.playback_history_repository import PlaybackHistoryRepository
from stremio_http_proxy.service.media_metadata_service import MediaMetadataService
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
        media_repository: MediaRepository | None = None,
        media_item_repository: MediaItemRepository | None = None,
        media_metadata_service: MediaMetadataService | None = None,
    ):
        self.playback_history_repository = playback_history_repository
        self.cache_manager = cache_manager
        self.prefetch_service = next_episode_prefetch_service
        self.task_service = task_service
        self.media_repository = media_repository
        self.media_item_repository = media_item_repository
        self.media_metadata_service = media_metadata_service

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

            # Resolve clean title and poster from Media/MediaItem
            media = None
            media_item = None
            if self.media_repository:
                if getattr(record, "media_item_id", None):
                    if self.media_item_repository: media_item = self.media_item_repository.get_media_item(record.media_item_id)
                if not media_item and record.content_id:
                    if self.media_item_repository: media_item = self.media_item_repository.get_by_content_id(record.content_id)
                if media_item:
                    media = self.media_repository.get_media(media_item.media_id)
                elif imdb_id:
                    media = self.media_repository.get_media(imdb_id)

            clean_title = media.title if (media and media.title) else (record.title or "Senza titolo")
            clean_poster = (media.poster if (media and media.poster) else record.poster) or None

            if season is not None and episode is not None:
                formatted_title = f"{clean_title} - S{season:02d}E{episode:02d}"
                subtitle = f"Stagione {season} • Episodio {episode}"
            else:
                formatted_title = clean_title
                subtitle = (media.year if (media and media.year) else (record.content_type or "Film"))

            results.append({
                "id": record.id,
                "content_id": record.content_id,
                "imdb_id": imdb_id,
                "season": season,
                "episode": episode,
                "content_type": record.content_type or ("series" if season is not None else "movie"),
                "title": formatted_title,
                "clean_title": clean_title,
                "show_title": clean_title,
                "subtitle": subtitle,
                "raw_title": record.title,
                "poster": clean_poster,
                "backdrop": media.backdrop if media else None,
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

    def get_season_cache_status(self, content_id: str, season: int) -> dict[int, dict[str, Any]]:
        clean_id = content_id.split(":")[0]
        prefix = f"{clean_id}:{season}:"
        entries = self.cache_manager.get_entries_for_content_prefix(prefix)
        status_map: dict[int, dict[str, Any]] = {}
        for cache_key, entry in entries:
            parts = (entry.content_id or "").split(":")
            if len(parts) >= 3 and parts[1] == str(season):
                try:
                    ep_num = int(parts[2])
                    status_val = entry.status.value if hasattr(entry.status, "value") else str(entry.status)
                    current = status_map.get(ep_num)
                    if not current or (current.get("status") != "ready" and status_val == "ready"):
                        status_map[ep_num] = {
                            "status": status_val,
                            "progress_percent": entry.progress_percent,
                            "cache_key": cache_key,
                        }
                    elif not current:
                        status_map[ep_num] = {
                            "status": status_val,
                            "progress_percent": entry.progress_percent,
                            "cache_key": cache_key,
                        }
                except ValueError:
                    pass
        return status_map

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

    def get_library(
        self,
        media_type: str | None = None,
        cached_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not self.media_repository:
            return {"items": [], "total": 0}

        all_media = self.media_repository.list_media(media_type=media_type, limit=limit, offset=offset)
        total_count = self.media_repository.count_media(media_type=media_type)
        items = []

        for m in all_media:
            media_items = self.media_item_repository.get_items_for_media(m.id) if self.media_item_repository else []
            cached_episodes = 0
            ready_streams = 0
            downloading_streams = 0

            for mi in media_items:
                entries = self.cache_manager.get_entries_for_content(mi.id)
                has_ready = False
                for _, e in entries:
                    if e.status == CacheEntryStatusEnum.READY:
                        ready_streams += 1
                        has_ready = True
                    elif e.status in (CacheEntryStatusEnum.DOWNLOADING, CacheEntryStatusEnum.PROCESSING):
                        downloading_streams += 1
                if has_ready:
                    cached_episodes += 1

            # If movie or media_items was empty, also check directly by m.id
            if not media_items:
                entries = self.cache_manager.get_entries_for_content(m.id)
                for _, e in entries:
                    if e.status == CacheEntryStatusEnum.READY:
                        ready_streams += 1
                        cached_episodes = 1
                    elif e.status in (CacheEntryStatusEnum.DOWNLOADING, CacheEntryStatusEnum.PROCESSING):
                        downloading_streams += 1

            is_cached = ready_streams > 0
            is_downloading = downloading_streams > 0

            if cached_only and not is_cached and not is_downloading:
                continue

            # Stremio direct url
            stremio_url = f"stremio://detail/{m.type}/{m.id}"

            items.append({
                "id": m.id,
                "type": m.type,
                "title": m.title,
                "year": m.year,
                "poster": m.poster,
                "backdrop": m.backdrop,
                "overview": m.overview,
                "last_accessed_at": m.last_accessed_at,
                "last_accessed_str": time.strftime("%d/%m/%Y %H:%M", time.localtime(m.last_accessed_at)),
                "cached_episodes_count": cached_episodes,
                "total_episodes_count": len(media_items),
                "ready_streams_count": ready_streams,
                "downloading_streams_count": downloading_streams,
                "is_cached": is_cached,
                "is_downloading": is_downloading,
                "stremio_url": stremio_url,
            })

        return {
            "items": items,
            "total": len(items) if cached_only else total_count,
        }

    def delete_media(self, media_id: str) -> dict[str, Any]:
        success = False
        if self.media_repository:
            success = self.media_repository.delete_media(media_id)
        return {"success": success, "media_id": media_id}

    def get_tasks(self, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if not self.task_service:
            return []
        raw_tasks = self.task_service.list_tasks(status=status, limit=limit)
        results = []
        now = time.time()
        for t in raw_tasks:
            args = t.get("arguments") or {}
            content_id = args.get("content_id")
            media_title = None
            season = None
            episode = None

            if content_id:
                parts = content_id.split(":")
                media_id = parts[0]
                if len(parts) >= 3:
                    try:
                        season = int(parts[1])
                        episode = int(parts[2])
                    except ValueError:
                        pass
                if self.media_repository:
                    try:
                        media = self.media_repository.get_media(media_id)
                        if media:
                            media_title = media.title
                    except Exception:
                        pass

            display_name = {
                "fetch_next_episode": "Smart Prefetch Episodio",
                "fetch_media": "Recupero Flussi Media",
                "enrich_media_metadata": "Arricchimento Metadati",
                "optimize_media": "Ottimizzazione Media (MKV/MP4)",
            }.get(t["name"], t["name"])

            results.append({
                "id": t["id"],
                "name": t["name"],
                "display_name": display_name,
                "status": t["status"],
                "arguments": args,
                "content_id": content_id,
                "media_title": media_title,
                "season": season,
                "episode": episode,
                "scheduled_at": t["scheduled_at"],
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
                "remaining_seconds": max(0, int(t["scheduled_at"] - now)) if t["status"] == "pending" and t["scheduled_at"] > now else 0,
                "attempt": t["attempt"],
                "max_attempts": t["max_attempts"],
                "last_error": t["last_error"],
                "claimed_by": t["claimed_by"],
            })
        return results

