import re
import time
from typing import Any
from urllib.parse import urlencode

from injector import inject

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.model.cache_entry import CacheEntry
from stremio_http_proxy.model.download_status import DownloadStatus, DownloadStatusResponse
from stremio_http_proxy.repository.media_repository import MediaRepository
from stremio_http_proxy.repository.media_item_repository import MediaItemRepository


class DashboardService:
    @inject
    def __init__(
        self,
        cache_manager: CacheManager,
        public_base_url: str,
        media_repository: MediaRepository | None = None,
        media_item_repository: MediaItemRepository | None = None,
    ):
        self.cache_manager = cache_manager
        self.public_base_url = public_base_url.rstrip("/")
        self.media_repository = media_repository
        self.media_item_repository = media_item_repository

    def _resolve_media_info(self, entry: CacheEntry) -> dict[str, Any]:
        content_id = entry.content_id or entry.media_item_id
        title = entry.title
        media_title = None
        season = None
        episode = None
        episode_title = None
        content_type = entry.content_type
        media_id = None

        if content_id:
            clean_id = content_id
            if clean_id.startswith("series:"):
                clean_id = clean_id[len("series:"):]
                content_type = "series"
            elif clean_id.startswith("movie:"):
                clean_id = clean_id[len("movie:"):]
                content_type = "movie"

            parts = clean_id.split(":")
            if len(parts) >= 3:
                media_id = parts[0]
                try:
                    season = int(parts[1])
                    episode = int(parts[2])
                except ValueError:
                    pass
                content_type = "series"
            elif len(parts) == 1:
                media_id = parts[0]

        if season is None and title:
            match = re.search(r"(?i)\bS(\d{1,2})[EX](\d{1,3})\b", title)
            if match:
                try:
                    season = int(match.group(1))
                    episode = int(match.group(2))
                    content_type = "series"
                except ValueError:
                    pass

        if media_id and self.media_repository:
            try:
                media = self.media_repository.get_media(media_id)
                print('DEBUG GET_MEDIA', media_id, media)
                if media:
                    media_title = media.title
                    if not content_type:
                        content_type = media.type
                if season is not None and episode is not None:
                    item = self.media_item_repository.get_media_item_by_season_episode(media_id, season, episode) if self.media_item_repository else None
                    if item and item.title and item.title != f"Episodio {episode}":
                        episode_title = item.title
            except Exception:
                pass

        return {
            "media_title": media_title,
            "season": season,
            "episode": episode,
            "episode_title": episode_title,
            "content_type": content_type,
            "media_id": media_id,
        }

    def get_index_context(self) -> dict[str, object]:
        return {}

    def get_cache_items_context(self) -> dict[str, object]:
        return {}

    def get_tasks_context(self) -> dict[str, object]:
        return {}


    def get_cache_entry_context(self, infohash: str, index: int) -> tuple[dict | None, int]:
        cache_key = self.cache_manager.build_cache_key_from_parts(infohash, index)
        entry = self.cache_manager.get_entry(cache_key)
        if entry.status == CacheEntryStatusEnum.MISSING:
            return None, 404

        play_url = None
        if entry.source_link:
            params = {"link": entry.source_link, "index": str(index)}
            if entry.title:
                params["title"] = entry.title
            if entry.poster:
                params["poster"] = entry.poster
            if entry.category:
                params["category"] = entry.category
            if entry.content_type:
                params["content_type"] = entry.content_type
            if entry.content_id:
                params["content_id"] = entry.content_id
            play_url = f"{self.public_base_url}/play?{urlencode(params)}"

        def fmt_ts(ts: float | None) -> str:
            if ts is None:
                return "N/A"
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

        media_info = self._resolve_media_info(entry)
        return {
            "entry": entry,
            "play_url": play_url,
            "infohash": infohash,
            "index": index,
            "created_at_str": fmt_ts(entry.created_at),
            "completed_at_str": fmt_ts(entry.completed_at),
            "media_title": media_info["media_title"],
            "season": media_info["season"],
            "episode": media_info["episode"],
            "episode_title": media_info["episode_title"],
            "content_type": media_info["content_type"],
            "media_id": media_info["media_id"],
        }, 200

    def get_download_status(
        self,
        page: int = 1,
        limit: int = 10,
        search: str | None = None,
        status: str | None = None,
    ) -> DownloadStatusResponse:
        all_entries = self.cache_manager.list_entries()
        total_cache_bytes = sum(
            entry.size_bytes if entry.status == CacheEntryStatusEnum.READY else entry.downloaded_bytes
            for _, entry in all_entries
        )
        status_counts: dict[str, int] = {}
        active_downloads = 0
        active_items = []
        for cache_key, entry in all_entries:
            status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
            if entry.status in {CacheEntryStatusEnum.DOWNLOADING, CacheEntryStatusEnum.PROCESSING, CacheEntryStatusEnum.OPTIMIZING}:
                active_downloads += 1
            if entry.status in {
                CacheEntryStatusEnum.DOWNLOADING,
                CacheEntryStatusEnum.PROCESSING,
                CacheEntryStatusEnum.QUEUED,
                CacheEntryStatusEnum.OPTIMIZING,
            }:
                infohash, index = self.cache_manager.parse_cache_key(cache_key)
                media_info = self._resolve_media_info(entry)
                active_items.append(
                    DownloadStatus(
                        cache_key=cache_key,
                        title=entry.title,
                        infohash=infohash,
                        index=index,
                        status=entry.status,
                        created_at=entry.created_at,
                        completed_at=entry.completed_at,
                        downloaded_bytes=entry.downloaded_bytes,
                        expected_bytes=entry.expected_bytes,
                        progress_percent=entry.progress_percent,
                        download_speed_bytes_per_second=entry.download_speed_bytes_per_second,
                        attempt=entry.attempt,
                        last_error=entry.last_error,
                        last_progress_at=entry.last_progress_at,
                        media_title=media_info["media_title"],
                        season=media_info["season"],
                        episode=media_info["episode"],
                        episode_title=media_info["episode_title"],
                        content_type=media_info["content_type"],
                        media_id=media_info["media_id"],
                    )
                )

        entries = all_entries
        if search:
            search_lower = search.lower()
            filtered = []
            for k, e in entries:
                info = self._resolve_media_info(e)
                matches = False
                if e.title and search_lower in e.title.lower():
                    matches = True
                elif info["media_title"] and search_lower in info["media_title"].lower():
                    matches = True
                elif info["episode_title"] and search_lower in info["episode_title"].lower():
                    matches = True
                elif e.infohash and search_lower in e.infohash.lower():
                    matches = True
                if matches:
                    filtered.append((k, e))
            entries = filtered
        if status:
            if status == "active":
                entries = [
                    (k, e) for k, e in entries
                    if e.status in {
                        CacheEntryStatusEnum.DOWNLOADING,
                        CacheEntryStatusEnum.PROCESSING,
                        CacheEntryStatusEnum.QUEUED,
                        CacheEntryStatusEnum.OPTIMIZING,
                    }
                ]
            else:
                entries = [(k, e) for k, e in entries if e.status == status]

        total_items = len(entries) if (search or status) else len(all_entries)
        total_pages = max((total_items + limit - 1) // limit, 1)
        page = min(page, total_pages)
        start = (page - 1) * limit
        end = start + limit

        downloads = []
        for cache_key, entry in entries[start:end]:
            infohash, index = self.cache_manager.parse_cache_key(cache_key)
            media_info = self._resolve_media_info(entry)
            downloads.append(
                DownloadStatus(
                    cache_key=cache_key,
                    title=entry.title,
                    infohash=infohash,
                    index=index,
                    status=entry.status,
                    created_at=entry.created_at,
                    completed_at=entry.completed_at,
                    downloaded_bytes=entry.downloaded_bytes,
                    expected_bytes=entry.expected_bytes,
                    progress_percent=entry.progress_percent,
                    download_speed_bytes_per_second=entry.download_speed_bytes_per_second,
                    attempt=entry.attempt,
                    last_error=entry.last_error,
                    last_progress_at=entry.last_progress_at,
                    media_title=media_info["media_title"],
                    season=media_info["season"],
                    episode=media_info["episode"],
                    episode_title=media_info["episode_title"],
                    content_type=media_info["content_type"],
                    media_id=media_info["media_id"],
                )
            )

        return DownloadStatusResponse(
            manifest_url=f"{self.public_base_url}/manifest.json",
            page=page,
            limit=limit,
            total_items=total_items,
            total_pages=total_pages,
            total_cache_bytes=total_cache_bytes,
            status_counts=status_counts,
            active_downloads=active_downloads,
            downloads=downloads,
            active_items=active_items[:5],
        )
