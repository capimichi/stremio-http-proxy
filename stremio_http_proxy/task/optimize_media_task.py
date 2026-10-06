import asyncio
import json
import os
from pathlib import Path
from typing import Any
from celery import shared_task
from injector import inject

from stremio_http_proxy.helper.media_type_helper import detect_media_type
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.task.abstract_task import AbstractTask


COMPATIBLE_EXTENSIONS = {"mp4", "mkv", "webm"}


class OptimizeMediaTask(AbstractTask):
    task_name = "stremio_http_proxy.task.optimize_media_task"
    name = "optimize_media"

    @inject
    def __init__(
        self,
        cache_manager: CacheManager,
        logger_factory: LoggerFactory,
        optimize_media_enabled: bool = True,
        optimize_media_target: str = "web_ready_mp4",
        gpu_enabled: bool = True,
        vaapi_device: str = "/dev/dri/renderD128",
        preset: str = "ultrafast",
    ):
        self.cache_manager = cache_manager
        self.logger = logger_factory.get_logger("stremio_http_proxy.optimize_media", "optimize_media.log")
        self.optimize_media_enabled = optimize_media_enabled
        self.optimize_media_target = optimize_media_target
        self.gpu_enabled = gpu_enabled
        self.vaapi_device = vaapi_device
        self.preset = preset

    async def run(self, arguments: dict[str, Any] | str | None = None, *args: Any, **kwargs: Any) -> bool:
        cache_key = None
        if isinstance(arguments, str):
            cache_key = arguments
        elif isinstance(arguments, dict):
            cache_key = arguments.get("cache_key")
        elif args:
            cache_key = args[0]
        elif kwargs.get("cache_key"):
            cache_key = kwargs.get("cache_key")

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

        orig_size = media_path.stat().st_size

        if not self.optimize_media_enabled or self.optimize_media_target in ("none", "disabled", "false"):
            self.logger.info("Optimization is disabled via config, marking %s ready (%s bytes)", cache_key, orig_size)
            self.cache_manager.mark_ready(cache_key, orig_size)
            return True

        if self.optimize_media_target == "mkv":
            return await self._run_legacy_mkv_optimization(cache_key, media_path, orig_size)

        return await self._run_web_ready_optimization(cache_key, media_path, orig_size)

    async def _probe_media(self, media_path: Path) -> dict | None:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return json.loads(stdout.decode("utf-8", errors="ignore"))
        except Exception as e:
            self.logger.warning("ffprobe failed on %s: %s", media_path, e)
        return None

    def _is_vaapi_available(self) -> bool:
        if not self.gpu_enabled or not self.vaapi_device:
            return False
        try:
            dev = Path(self.vaapi_device)
            return dev.exists() and os.access(dev, os.R_OK | os.W_OK)
        except Exception:
            return False

    def _analyze_streams(self, probe_data: dict | None, ext: str) -> tuple[bool, bool, bool]:
        """
        Returns:
            (is_already_fully_web_ready, is_video_web_ready, is_audio_web_ready)
        """
        if not probe_data:
            return False, False, False

        streams = probe_data.get("streams", [])
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

        is_video_web_ready = False
        if video_streams:
            v0 = video_streams[0]
            v_codec = (v0.get("codec_name") or "").lower()
            v_pix_fmt = (v0.get("pix_fmt") or "").lower()
            if v_codec == "h264" and v_pix_fmt in ("yuv420p", "yuvj420p"):
                is_video_web_ready = True

        is_audio_web_ready = True
        if not audio_streams:
            is_audio_web_ready = True
        else:
            for a in audio_streams:
                a_codec = (a.get("codec_name") or "").lower()
                a_channels = a.get("channels", 2)
                if not (a_codec in ("aac", "mp3") and a_channels <= 2):
                    is_audio_web_ready = False
                    break

        is_already_fully_web_ready = (
            ext.lower() == "mp4" and is_video_web_ready and is_audio_web_ready
        )
        return is_already_fully_web_ready, is_video_web_ready, is_audio_web_ready

    async def _run_web_ready_optimization(self, cache_key: str, media_path: Path, orig_size: int) -> bool:
        _, ext = detect_media_type(media_path)
        probe_data = await self._probe_media(media_path)
        is_fully_ready, is_video_ready, is_audio_ready = self._analyze_streams(probe_data, ext)

        if is_fully_ready:
            self.cache_manager.mark_ready(cache_key, orig_size)
            self.logger.info("Media %s is already web-ready MP4 (size: %s bytes)", cache_key, orig_size)
            return True

        self.logger.info(
            "Optimizing media %s to web-ready MP4 (video_ready=%s, audio_ready=%s, ext=%s)...",
            cache_key, is_video_ready, is_audio_ready, ext,
        )

        temp_mp4_path = media_path.with_suffix(".opt.mp4")

        use_gpu = self._is_vaapi_available() and not is_video_ready
        cmd = self._build_ffmpeg_cmd(
            media_path,
            temp_mp4_path,
            is_video_ready=is_video_ready,
            is_audio_ready=is_audio_ready,
            use_gpu=use_gpu,
        )

        success = await self._run_ffmpeg(cmd)
        if not success and use_gpu:
            self.logger.warning("GPU web-ready optimization failed for %s, falling back to CPU transcode...", cache_key)
            cmd_cpu = self._build_ffmpeg_cmd(
                media_path,
                temp_mp4_path,
                is_video_ready=is_video_ready,
                is_audio_ready=is_audio_ready,
                use_gpu=False,
            )
            success = await self._run_ffmpeg(cmd_cpu)

        if success and temp_mp4_path.exists() and temp_mp4_path.stat().st_size > 0:
            temp_mp4_path.replace(media_path)
            try:
                media_path.chmod(0o666)
            except Exception:
                pass
            new_size = media_path.stat().st_size
            self.cache_manager.mark_ready(cache_key, new_size)
            self.logger.info("Media %s successfully optimized to web-ready MP4 (size: %s bytes)", cache_key, new_size)
            return True
        else:
            if temp_mp4_path.exists():
                temp_mp4_path.unlink(missing_ok=True)
            self.cache_manager.mark_ready(cache_key, orig_size)
            self.logger.error("Failed to optimize media %s to MP4; original file preserved and marked ready", cache_key)
            return False

    def _build_ffmpeg_cmd(
        self,
        src: Path,
        dest: Path,
        is_video_ready: bool,
        is_audio_ready: bool,
        use_gpu: bool,
    ) -> list[str]:
        cmd = ["ffmpeg", "-y"]
        if use_gpu:
            cmd.extend([
                "-hwaccel", "vaapi",
                "-hwaccel_device", self.vaapi_device,
                "-hwaccel_output_format", "vaapi",
            ])

        cmd.extend(["-i", str(src)])
        cmd.extend(["-map", "0:v:0", "-map", "0:a?", "-sn"])

        if is_video_ready:
            cmd.extend(["-c:v", "copy"])
        elif use_gpu:
            cmd.extend([
                "-vf", "scale_vaapi=format=nv12",
                "-c:v", "h264_vaapi",
                "-low_power", "1",
                "-quality", "7",
                "-qp", "28",
                "-async_depth", "4",
                "-b_depth", "1",
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", self.preset,
                "-crf", "28",
                "-pix_fmt", "yuv420p",
            ])

        if is_audio_ready:
            cmd.extend(["-c:a", "copy"])
        else:
            cmd.extend(["-c:a", "aac", "-ac", "2", "-b:a", "128k"])

        cmd.extend(["-movflags", "+faststart", str(dest)])
        return cmd

    async def _run_legacy_mkv_optimization(self, cache_key: str, media_path: Path, orig_size: int) -> bool:
        _, ext = detect_media_type(media_path)
        if ext.lower() in COMPATIBLE_EXTENSIONS:
            self.cache_manager.mark_ready(cache_key, orig_size)
            self.logger.info("Media %s is already in compatible container (%s), marked ready (size: %s bytes)", cache_key, ext, orig_size)
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


@shared_task(name="stremio_http_proxy.task.optimize_media_task", bind=True, max_retries=2)
def optimize_media_task(self, cache_key: str):
    from stremio_http_proxy.container.default_container import DefaultContainer

    container = DefaultContainer.getInstance()
    try:
        task: OptimizeMediaTask = container.get(OptimizeMediaTask)
        return asyncio.run(task.run(cache_key))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)

