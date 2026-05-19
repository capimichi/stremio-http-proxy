from injector import inject

from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.model.download_status import DownloadStatus, DownloadStatusResponse


class DashboardService:
    @inject
    def __init__(self, cache_manager: CacheManager, public_base_url: str):
        self.cache_manager = cache_manager
        self.public_base_url = public_base_url.rstrip("/")

    def get_download_status(self) -> DownloadStatusResponse:
        downloads = []
        for cache_key, entry in self.cache_manager.list_entries_by_status("downloading"):
            infohash, index = self.cache_manager.parse_cache_key(cache_key)
            downloads.append(
                DownloadStatus(
                    cache_key=cache_key,
                    infohash=infohash,
                    index=index,
                    status=entry.status,
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
            downloads=downloads,
        )
