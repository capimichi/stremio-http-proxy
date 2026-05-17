from pathlib import Path

from injector import inject

from stremio_http_proxy.model.playlist_models import TorrentJob

try:
    import libtorrent  # type: ignore
except ImportError:  # pragma: no cover
    libtorrent = None


class TorrentClient:
    @inject
    def __init__(self, state_dir: str):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def add_magnet(self, magnet: str, infohash: str) -> dict:
        if libtorrent is None:
            return {
                "name": infohash,
                "status": "registered",
                "metadata_available": False,
            }

        session = libtorrent.session({"listen_interfaces": "0.0.0.0:6881"})
        handle = libtorrent.add_magnet_uri(
            session,
            magnet,
            {"save_path": str(self.state_dir / infohash)},
        )
        return {
            "name": handle.name() or infohash,
            "status": "downloading_metadata",
            "metadata_available": handle.status().has_metadata,
        }

    def ensure_segment(self, job: TorrentJob, segment_name: str, target_path: Path) -> Path:
        if target_path.exists():
            return target_path
        if job.storage_path:
            source_path = Path(job.storage_path) / f"{segment_name}.ts"
            if source_path.exists():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(source_path.read_bytes())
                return target_path
        raise FileNotFoundError(
            f"Segment {segment_name}.ts for {job.infohash} is not available in cache or storage"
        )
