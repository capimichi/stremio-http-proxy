import asyncio
import json
import shutil
from pathlib import Path
from urllib.parse import urljoin

import httpx
from injector import inject

from stremio_http_proxy.logger.logger_factory import LoggerFactory


class HlsChunkManager:
    @inject
    def __init__(self, base_dir: Path | str, logger_factory: LoggerFactory):
        self.base_dir = Path(base_dir)
        self.logger = logger_factory.get_logger("stremio_http_proxy.hls_chunk", "hls_chunk.log")
        self._locks: dict[str, asyncio.Lock] = {}
        self._metadata_cache: dict[str, list[str]] = {}

    def _parse_cache_key(self, cache_key: str) -> tuple[str, int]:
        if ":" in cache_key:
            infohash, raw_index = cache_key.split(":", 1)
            try:
                return infohash, int(raw_index)
            except ValueError:
                return infohash, 0
        return cache_key, 0

    def get_chunks_dir(self, cache_key: str) -> Path:
        infohash, index = self._parse_cache_key(cache_key)
        chunks_dir = self.base_dir / infohash / f"chunks_{index}"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        return chunks_dir

    def get_chunk_path(self, cache_key: str, seq: int) -> Path:
        chunks_dir = self.get_chunks_dir(cache_key)
        return chunks_dir / f"{seq:05d}.ts"

    def has_chunk(self, cache_key: str, seq: int) -> bool:
        infohash, index = self._parse_cache_key(cache_key)
        chunk_path = self.base_dir / infohash / f"chunks_{index}" / f"{seq:05d}.ts"
        return chunk_path.is_file() and chunk_path.stat().st_size > 0

    def get_downloaded_indices(self, cache_key: str) -> set[int]:
        infohash, index = self._parse_cache_key(cache_key)
        chunks_dir = self.base_dir / infohash / f"chunks_{index}"
        if not chunks_dir.exists():
            return set()
        indices = set()
        for f in chunks_dir.glob("*.ts"):
            try:
                indices.add(int(f.stem))
            except ValueError:
                continue
        return indices

    def get_chunks_total_bytes(self, cache_key: str) -> int:
        infohash, index = self._parse_cache_key(cache_key)
        chunks_dir = self.base_dir / infohash / f"chunks_{index}"
        if not chunks_dir.exists():
            return 0
        total = 0
        for f in chunks_dir.glob("*.ts"):
            try:
                total += f.stat().st_size
            except OSError:
                pass
        return total

    def save_playlist_metadata(self, cache_key: str, chunk_urls: list[str]) -> None:
        self._metadata_cache[cache_key] = chunk_urls
        chunks_dir = self.get_chunks_dir(cache_key)
        meta_file = chunks_dir / "playlist.json"
        try:
            with meta_file.open("w", encoding="utf-8") as f:
                json.dump(chunk_urls, f)
        except Exception as e:
            self.logger.warning("Failed to write playlist.json for %s: %s", cache_key, e)

    def get_playlist_metadata(self, cache_key: str) -> list[str] | None:
        if cache_key in self._metadata_cache:
            return self._metadata_cache[cache_key]
        infohash, index = self._parse_cache_key(cache_key)
        meta_file = self.base_dir / infohash / f"chunks_{index}" / "playlist.json"
        if meta_file.is_file():
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    urls = json.load(f)
                    if isinstance(urls, list):
                        self._metadata_cache[cache_key] = urls
                        return urls
            except Exception as e:
                self.logger.warning("Failed to read playlist.json for %s: %s", cache_key, e)
        return None

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def get_or_download_chunk(
        self,
        cache_key: str,
        seq: int,
        chunk_url: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
    ) -> Path:
        lock_key = f"{cache_key}:{seq}"
        async with self._get_lock(lock_key):
            chunk_path = self.get_chunk_path(cache_key, seq)
            if chunk_path.is_file() and chunk_path.stat().st_size > 0:
                return chunk_path

            tmp_path = chunk_path.with_suffix(".tmp")
            if client is not None:
                resp = await client.get(chunk_url)
                resp.raise_for_status()
                content = resp.content
            else:
                async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as c:
                    resp = await c.get(chunk_url)
                    resp.raise_for_status()
                    content = resp.content

            with tmp_path.open("wb") as f:
                f.write(content)
            tmp_path.replace(chunk_path)
            return chunk_path

    async def merge_chunks_to_media(
        self,
        cache_key: str,
        total_chunks: int,
        output_media_path: Path,
    ) -> bool:
        chunks_dir = self.get_chunks_dir(cache_key)
        concat_file = chunks_dir / "concat_list.txt"

        lines = ["ffconcat version 1.0"]
        for i in range(total_chunks):
            chunk_file = chunks_dir / f"{i:05d}.ts"
            if not chunk_file.is_file() or chunk_file.stat().st_size == 0:
                self.logger.error("Missing chunk %05d for %s during merge", i, cache_key)
                return False
            lines.append(f"file '{chunk_file.name}'")

        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        output_media_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-f",
            "mp4",
            str(output_media_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_text = stderr.decode(errors="replace").strip() if stderr else ""
                self.logger.error("ffmpeg concat failed for %s (code %d): %s", cache_key, proc.returncode, err_text)
                return False
        except Exception as e:
            self.logger.exception("Error executing ffmpeg concat for %s: %s", cache_key, e)
            return False

        if not output_media_path.is_file() or output_media_path.stat().st_size == 0:
            self.logger.error("Merged file %s is missing or empty for %s", output_media_path, cache_key)
            return False

        self.logger.info(
            "Successfully merged %d chunks for %s into %s (%d bytes)",
            total_chunks,
            cache_key,
            output_media_path,
            output_media_path.stat().st_size,
        )
        return True

    def cleanup_chunks(self, cache_key: str) -> None:
        infohash, index = self._parse_cache_key(cache_key)
        chunks_dir = self.base_dir / infohash / f"chunks_{index}"
        if chunks_dir.exists():
            try:
                shutil.rmtree(chunks_dir, ignore_errors=True)
                self.logger.info("Cleaned up chunks for %s", cache_key)
            except Exception as e:
                self.logger.warning("Error cleaning up chunks for %s: %s", cache_key, e)
        self._metadata_cache.pop(cache_key, None)
