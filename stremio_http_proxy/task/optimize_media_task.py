import asyncio
import os
from pathlib import Path
from typing import Any
from injector import inject

from stremio_http_proxy.helper.media_type_helper import detect_media_type
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.task.abstract_task import AbstractTask


COMPATIBLE_EXTENSIONS = {"mp4", "mkv", "webm"}


class OptimizeMediaTask(AbstractTask):
    name = "optimize_media"

    @inject
    def __init__(self, cache_manager: CacheManager, logger_factory: LoggerFactory):
        self.cache_manager = cache_manager
        self.logger = logger_factory.get_logger("stremio_http_proxy.optimize_media", "optimize_media.log")

    async def run(self, arguments: dict[str, Any]) -> bool:
        cache_key = arguments.get("cache_key")
        if not cache_key:
            self.logger.warning("OptimizeMediaTask called without cache_key")
            return True

        entry = self.cache_manager.get_entry(cache_key)
        if entry is None:
            self.logger.warning("Cache entry %s not found for optimization", cache_key)
            return True

        status_val = getattr(entry.status, "value", entry.status)
        if status_val not in ("optimizing", "ready"):
            self.logger.info("Cache entry %s status is %s (neither optimizing nor ready), skipping optimization", cache_key, status_val)
            return True

        infohash, index = self.cache_manager.parse_cache_key(cache_key)
        media_path = self.cache_manager._media_path(infohash, index)
        if not media_path.exists():
            self.logger.warning("Media file %s does not exist on disk", media_path)
            return True

        _, ext = detect_media_type(media_path)
        if ext.lower() in COMPATIBLE_EXTENSIONS:
            size_bytes = media_path.stat().st_size
            self.cache_manager.mark_ready(cache_key, size_bytes)
            self.logger.info("Media %s is already in compatible container (%s), marked ready (size: %s bytes)", cache_key, ext, size_bytes)
            return True

        self.logger.info("Media %s container (%s) needs optimization. Starting ffmpeg remux to MKV...", cache_key, ext)
        temp_mkv_path = media_path.with_suffix(".opt.mkv")

        success = await self._remux_to_mkv(media_path, temp_mkv_path)
        if not success:
            self.logger.warning("Fast remux failed for %s, attempting transcode fallback...", cache_key)
            success = await self._transcode_fallback(media_path, temp_mkv_path)

        if success and temp_mkv_path.exists() and temp_mkv_path.stat().st_size > 0:
            temp_mkv_path.replace(media_path)
            try:
                media_path.chmod(0o666)
            except Exception:
                pass
            new_size = media_path.stat().st_size
            self.cache_manager.mark_ready(cache_key, new_size)
            self.logger.info("Media %s successfully optimized to MKV (size: %s bytes)", cache_key, new_size)
            return True
        else:
            if temp_mkv_path.exists():
                temp_mkv_path.unlink(missing_ok=True)
            if media_path.exists():
                orig_size = media_path.stat().st_size
                self.cache_manager.mark_ready(cache_key, orig_size)
            self.logger.error("Failed to optimize media %s to MKV; original file preserved and marked ready", cache_key)
            return False

    async def _remux_to_mkv(self, src: Path, dest: Path) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-map", "0",
            "-c", "copy",
            str(dest),
        ]
        return await self._run_ffmpeg(cmd)

    async def _transcode_fallback(self, src: Path, dest: Path) -> bool:
        # Fallback 1: keep video codec, transcode audio to aac
        cmd_audio = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-map", "0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-c:s", "copy",
            str(dest),
        ]
        if await self._run_ffmpeg(cmd_audio):
            return True

        # Fallback 2: ultrafast h264 transcode for obsolete MPEG-4 ASP / DivX
        cmd_full = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-map", "0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-c:a", "aac",
            str(dest),
        ]
        return await self._run_ffmpeg(cmd_full)

    async def _run_ffmpeg(self, cmd: list[str]) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True
            self.logger.debug("FFmpeg exited with %s: %s", proc.returncode, stderr.decode("utf-8", errors="ignore")[-400:])
            return False
        except Exception as e:
            self.logger.exception("Exception running ffmpeg command: %s", e)
            return False
