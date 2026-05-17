from pathlib import Path

from injector import inject


class CacheService:
    @inject
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.segment_dir = self.cache_dir / "segments"
        self.segment_dir.mkdir(parents=True, exist_ok=True)

    def segment_path(self, infohash: str, segment_name: str) -> Path:
        return self.segment_dir / infohash / f"{segment_name}.ts"

    def get_total_size_bytes(self) -> int:
        total = 0
        for path in self.segment_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total
