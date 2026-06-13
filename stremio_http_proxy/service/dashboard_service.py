from injector import inject

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.manager.jinja_manager import JinjaManager
from stremio_http_proxy.model.download_status import DownloadStatus, DownloadStatusResponse


class DashboardService:
    @inject
    def __init__(self, cache_manager: CacheManager, public_base_url: str, jinja_manager: JinjaManager):
        self.cache_manager = cache_manager
        self.public_base_url = public_base_url.rstrip("/")
        self.jinja_manager = jinja_manager

    def get_index_html(self) -> str:
        return self.jinja_manager.render("dashboard/pages/index.html")

    def get_cache_items_html(self) -> str:
        return self.jinja_manager.render("dashboard/pages/cache_items.html")

    def get_download_status(self, page: int = 1, limit: int = 10, search: str | None = None) -> DownloadStatusResponse:
        entries = self.cache_manager.list_entries()
        if search:
            search_lower = search.lower()
            entries = [
                (k, e) for k, e in entries
                if e.title and search_lower in e.title.lower()
            ]
        total_items = len(entries)
        total_pages = max((total_items + limit - 1) // limit, 1)
        page = min(page, total_pages)
        start = (page - 1) * limit
        end = start + limit
        total_cache_bytes = sum(
            entry.size_bytes if entry.status == CacheEntryStatusEnum.READY else entry.downloaded_bytes
            for _, entry in entries
        )
        status_counts: dict[str, int] = {}
        active_downloads = 0
        for _, entry in entries:
            status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
            if entry.status in {CacheEntryStatusEnum.DOWNLOADING, CacheEntryStatusEnum.PROCESSING}:
                active_downloads += 1

        downloads = []
        for cache_key, entry in entries[start:end]:
            infohash, index = self.cache_manager.parse_cache_key(cache_key)
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
        )
