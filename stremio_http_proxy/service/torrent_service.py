from datetime import datetime, timedelta, timezone
from pathlib import Path

from injector import inject

from stremio_http_proxy.client.torrent_client import TorrentClient
from stremio_http_proxy.helper.hash_helper import extract_infohash
from stremio_http_proxy.model.playlist_models import TorrentJob
from stremio_http_proxy.repository.torrent_registry_repository import TorrentRegistryRepository
from stremio_http_proxy.service.cache_service import CacheService


class TorrentService:
    @inject
    def __init__(
        self,
        torrent_client: TorrentClient,
        registry_repository: TorrentRegistryRepository,
        cache_service: CacheService,
        max_cache_size_gb: int,
    ):
        self.torrent_client = torrent_client
        self.registry_repository = registry_repository
        self.cache_service = cache_service
        self.max_cache_size_gb = max_cache_size_gb

    def add_magnet(self, magnet: str, segments: list[str] | None = None) -> TorrentJob:
        infohash = extract_infohash(magnet)
        if infohash is None:
            raise ValueError("Unable to extract infohash from magnet link")
        status = self.torrent_client.add_magnet(magnet, infohash)
        job = TorrentJob(
            infohash=infohash,
            magnet=magnet,
            name=status["name"],
            status=status["status"],
            segments=segments or [],
            storage_path=str(Path(self.torrent_client.state_dir) / infohash),
        )
        return self.registry_repository.upsert(job)

    def list_jobs(self) -> list[TorrentJob]:
        return self.registry_repository.list_jobs()

    def get_job(self, infohash: str) -> TorrentJob | None:
        return self.registry_repository.touch(infohash)

    def ensure_segment(self, infohash: str, segment_name: str) -> Path:
        job = self.get_job(infohash)
        if job is None:
            raise FileNotFoundError(f"Torrent {infohash} is not registered")
        target_path = self.cache_service.segment_path(infohash, segment_name)
        return self.torrent_client.ensure_segment(job, segment_name, target_path)

    def cleanup(self, older_than_days: int, max_size_gb: int | None = None) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        deleted_files = 0
        reclaimed_bytes = 0
        for path in self.cache_service.segment_dir.rglob("*.ts"):
            accessed_at = datetime.fromtimestamp(path.stat().st_atime, tz=timezone.utc)
            if accessed_at < cutoff:
                reclaimed_bytes += path.stat().st_size
                path.unlink()
                deleted_files += 1

        limit_bytes = (max_size_gb or self.max_cache_size_gb) * 1024 * 1024 * 1024
        current_size = self.cache_service.get_total_size_bytes()
        if current_size > limit_bytes:
            files = sorted(
                [path for path in self.cache_service.segment_dir.rglob("*.ts") if path.is_file()],
                key=lambda item: item.stat().st_atime,
            )
            for path in files:
                if current_size <= limit_bytes:
                    break
                size = path.stat().st_size
                path.unlink()
                current_size -= size
                reclaimed_bytes += size
                deleted_files += 1

        return {"deleted_files": deleted_files, "reclaimed_bytes": reclaimed_bytes}
