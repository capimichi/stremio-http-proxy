from stremio_http_proxy.model.playlist_models import TorrentJob
from stremio_http_proxy.repository.torrent_registry_repository import TorrentRegistryRepository
from stremio_http_proxy.service.playlist_service import PlaylistService


def test_playlist_service_builds_m3u8(tmp_path):
    repository = TorrentRegistryRepository(str(tmp_path / "registry.json"))
    repository.upsert(
        TorrentJob(
            infohash="abc123",
            magnet="magnet:?xt=urn:btih:abc123",
            name="demo",
            segments=["0001", "0002"],
        )
    )

    service = PlaylistService("http://localhost:8459", repository)
    playlist = service.build_for_infohash("abc123")

    assert "#EXTM3U" in playlist
    assert "/streams/abc123/segments/0001.ts" in playlist
