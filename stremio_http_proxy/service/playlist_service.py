from injector import inject

from stremio_http_proxy.helper.hls_helper import build_playlist
from stremio_http_proxy.repository.torrent_registry_repository import TorrentRegistryRepository


class PlaylistService:
    @inject
    def __init__(self, public_base_url: str, registry_repository: TorrentRegistryRepository):
        self.public_base_url = public_base_url.rstrip("/")
        self.registry_repository = registry_repository

    def build_for_infohash(self, infohash: str) -> str:
        job = self.registry_repository.touch(infohash)
        if job is None:
            raise FileNotFoundError(f"Torrent {infohash} is not registered")
        if not job.segments:
            raise FileNotFoundError(f"Torrent {infohash} has no registered HLS segments")
        return build_playlist(self.public_base_url, infohash, job.segments)
