import asyncio
import os
import socket
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from celery import shared_task
import httpx
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.task.abstract_task import AbstractTask


class DownloadMediaTask(AbstractTask):
    task_name = "stremio_http_proxy.task.download_media_task"
    name = "download_media"

    @inject
    def __init__(
        self,
        torrserver_client: TorrServerClient,
        cache_manager: CacheManager,
        logger_factory: LoggerFactory,
        connect_timeout_seconds: int = 20,
        no_progress_timeout_seconds: int = 30,
        min_progress_bytes: int = 524288,
        min_progress_window_seconds: int = 60,
        max_total_seconds: int = 7200,
        progress_log_interval_seconds: int = 5,
        prefetch_min_progress_bytes: int = 1048576,
        next_episode_prefetch_service: Any = None,
    ):
        self.torrserver_client = torrserver_client
        self.cache_manager = cache_manager
        self.logger = logger_factory.get_logger("stremio_http_proxy.download_task", "download_worker.log")
        self.progress_logger = logger_factory.get_logger("stremio_http_proxy.download_progress", "download_progress.log")
        self.worker_id = socket.gethostname()
        self.connect_timeout_seconds = connect_timeout_seconds
        self.no_progress_timeout_seconds = no_progress_timeout_seconds
        self.min_progress_bytes = min_progress_bytes
        self.min_progress_window_seconds = min_progress_window_seconds
        self.max_total_seconds = max_total_seconds
        self.progress_log_interval_seconds = progress_log_interval_seconds
        self.prefetch_min_progress_bytes = prefetch_min_progress_bytes
        self.next_episode_prefetch_service = next_episode_prefetch_service

    def run(self, *args: Any, **kwargs: Any) -> bool:
        cache_key = args[0] if args else kwargs.get("cache_key")
        if not cache_key:
            self.logger.warning("DownloadMediaTask invoked without cache_key")
            return False
        return asyncio.run(self.execute(cache_key))

    async def execute(self, cache_key: str) -> bool:
        if self.cache_manager.is_ready(cache_key):
            self.logger.info("Cache entry %s already ready, skipping download", cache_key)
            return True

        entry = self.cache_manager.get_entry(cache_key)
        if not entry or not entry.source_link:
            self.logger.warning("Cache entry %s has no source_link", cache_key)
            return False

        link = entry.source_link
        attempt = (entry.attempt or 0) + 1
        self.cache_manager.mark_downloading(cache_key, attempt=attempt)
        self.logger.info("Starting download for %s (attempt %d): %s", cache_key, attempt, link)

        try:
            self.cache_manager.prune()
            if ".m3u8" in link:
                await self._download_hls(cache_key, link)
            elif link.startswith(("http://", "https://")):
                await self._download_http(cache_key, link)
            else:
                await self._download_torrent(cache_key, entry)

            size_bytes = self.cache_manager.finalize_download(cache_key)
            self._on_download_completed(cache_key, size_bytes)
            return True
        except Exception as exc:
            self.logger.exception("Download failed for %s: %s", cache_key, exc)
            self.cache_manager.cleanup_partial(cache_key)
            self.cache_manager.mark_failed(cache_key, str(exc), attempt)
            if self.next_episode_prefetch_service and getattr(entry, "trigger", None) == "next_episode_prefetch":
                try:
                    await self.next_episode_prefetch_service.on_download_failed(
                        entry.content_type, entry.content_id, entry.category
                    )
                except Exception:
                    self.logger.exception("Error triggering fallback for prefetch cache_key %s", cache_key)
            raise

    async def _download_hls(self, cache_key: str, url: str) -> None:
        tmp_path = self.cache_manager.prepare_download_path(cache_key)
        if tmp_path.exists():
            tmp_path.unlink()

        cmd = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            url,
            "-map",
            "0",
            "-c",
            "copy",
            "-f",
            "matroska",
            str(tmp_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise RuntimeError("ffmpeg binary not found in PATH")

        downloaded_bytes = 0
        started_at = time.time()
        window_started_at = started_at
        bytes_at_window_start = 0
        last_progress_log_at = started_at

        while True:
            try:
                await asyncio.wait_for(proc.wait(), timeout=float(min(self.progress_log_interval_seconds, 2)))
                break
            except asyncio.TimeoutError:
                pass

            now = time.time()
            downloaded_bytes = tmp_path.stat().st_size if tmp_path.exists() else 0
            elapsed_seconds = max(now - started_at, 0.001)
            speed_bytes_per_second = downloaded_bytes / elapsed_seconds

            if now - started_at > self.max_total_seconds:
                proc.kill()
                await proc.wait()
                raise TimeoutError("HLS download exceeded maximum duration")

            if now - window_started_at >= self.min_progress_window_seconds:
                if downloaded_bytes - bytes_at_window_start < self.min_progress_bytes:
                    proc.kill()
                    await proc.wait()
                    raise TimeoutError("HLS download progress stayed below threshold")
                window_started_at = now
                bytes_at_window_start = downloaded_bytes

            if now - last_progress_log_at >= self.progress_log_interval_seconds:
                self.cache_manager.mark_progress(
                    cache_key,
                    downloaded_bytes,
                    None,
                    None,
                    speed_bytes_per_second,
                )
                self.progress_logger.info(
                    "cache_key=%s downloaded_mb=%.2f speed_mbps=%.2f elapsed_s=%.0f",
                    cache_key,
                    downloaded_bytes / (1024 * 1024),
                    speed_bytes_per_second / (1024 * 1024),
                    elapsed_seconds,
                )
                last_progress_log_at = now

        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            error_msg = stderr.decode(errors="replace").strip() if stderr else ""
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}: {error_msg}")

        downloaded_bytes = tmp_path.stat().st_size if tmp_path.exists() else 0
        min_size_bytes = self.cache_manager.get_min_cache_size()
        if downloaded_bytes < min_size_bytes:
            raise RuntimeError(
                f"Download rifiutato: il file è troppo piccolo ({downloaded_bytes} byte). "
                f"Soglia minima: {min_size_bytes} byte."
            )

        self.cache_manager.mark_progress(
            cache_key,
            downloaded_bytes,
            downloaded_bytes,
            100.0,
            downloaded_bytes / max(time.time() - started_at, 0.001),
        )

    async def _download_http(self, cache_key: str, url: str, auth: httpx.Auth | tuple[str, str] | None = None) -> None:
        tmp_path = self.cache_manager.prepare_download_path(cache_key)
        downloaded_bytes = 0
        started_at = time.time()
        last_progress_log_at = started_at
        window_started_at = started_at
        bytes_at_window_start = 0

        timeout = httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.connect_timeout_seconds,
            write=30.0,
            pool=30.0,
        )
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, auth=auth) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_len = response.headers.get("content-length")
                expected_bytes = int(content_len) if content_len and content_len.isdigit() else None

                with tmp_path.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        handle.write(chunk)
                        downloaded_bytes += len(chunk)
                        now = time.time()

                        if now - started_at > self.max_total_seconds:
                            raise TimeoutError("HTTP download exceeded maximum duration")

                        if now - window_started_at >= self.min_progress_window_seconds:
                            if downloaded_bytes - bytes_at_window_start < self.min_progress_bytes:
                                raise TimeoutError("HTTP download progress stayed below threshold")
                            window_started_at = now
                            bytes_at_window_start = downloaded_bytes

                        if now - last_progress_log_at >= self.progress_log_interval_seconds:
                            elapsed_seconds = max(now - started_at, 0.001)
                            speed = downloaded_bytes / elapsed_seconds
                            pct = round(min((downloaded_bytes / expected_bytes) * 100, 100), 2) if expected_bytes else None
                            self.cache_manager.mark_progress(cache_key, downloaded_bytes, expected_bytes, pct, speed)
                            last_progress_log_at = now

        min_size_bytes = self.cache_manager.get_min_cache_size()
        if downloaded_bytes < min_size_bytes:
            raise RuntimeError(f"HTTP download troppo piccolo ({downloaded_bytes} byte). Soglia minima: {min_size_bytes} byte.")

        self.cache_manager.mark_progress(
            cache_key,
            downloaded_bytes,
            downloaded_bytes,
            100.0,
            downloaded_bytes / max(time.time() - started_at, 0.001),
        )

    async def _download_torrent(self, cache_key: str, entry: Any) -> None:
        download_url = self.torrserver_client.build_download_url(
            link=entry.source_link,
            title=entry.title,
            poster=entry.poster,
            category=entry.category,
            index=entry.cache_index,
        )
        await self._download_http(cache_key, download_url, auth=self.torrserver_client.auth)

    def _on_download_completed(self, cache_key: str, size_bytes: int) -> None:
        self.cache_manager.mark_optimizing(cache_key, size_bytes)
        try:
            from stremio_http_proxy.task.optimize_media_task import optimize_media_task
            optimize_media_task.apply_async(args=[cache_key], queue="transcode")
            self.logger.info("Enqueued optimize_media_task for %s", cache_key)
        except Exception as e:
            self.logger.warning("Failed to dispatch optimize_media_task for %s: %s; falling back to ready", cache_key, e)
            self.cache_manager.mark_ready(cache_key, size_bytes)


@shared_task(name="stremio_http_proxy.task.download_media_task", bind=True, max_retries=3)
def download_media_task(self, cache_key: str):
    from stremio_http_proxy.container.default_container import DefaultContainer

    container = DefaultContainer.getInstance()
    try:
        task: DownloadMediaTask = container.get(DownloadMediaTask)
        return task.run(cache_key)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
