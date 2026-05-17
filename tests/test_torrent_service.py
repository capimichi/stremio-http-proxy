from stremio_http_proxy.client.torrent_client import TorrentClient
from stremio_http_proxy.model.playlist_models import TorrentJob
from stremio_http_proxy.repository.torrent_registry_repository import TorrentRegistryRepository
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.torrent_service import TorrentService


def test_add_magnet_registers_job(tmp_path):
    service = TorrentService(
        TorrentClient(str(tmp_path / "state")),
        TorrentRegistryRepository(str(tmp_path / "registry.json")),
        CacheService(str(tmp_path / "cache")),
        max_cache_size_gb=1,
    )

    job = service.add_magnet(
        "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
        ["0001"],
    )

    assert job.infohash == "abcdef1234567890abcdef1234567890abcdef12"
    assert job.segments == ["0001"]
