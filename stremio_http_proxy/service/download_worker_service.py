import asyncio
import socket
import time
from pathlib import Path

import httpx
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.model.download_job import DownloadJob


class DownloadWorkerService:
    @inject
    def __init__(
        self,
        torrserver_client: TorrServerClient,
        cache_manager: CacheManager,
        logger_factory: LoggerFactory,
        poll_seconds: int,
        connect_timeout_seconds: int,
        no_progress_timeout_seconds: int,
        min_progress_bytes: int,
        min_progress_window_seconds: int,
        max_total_seconds: int,
        progress_log_interval_seconds: int,
    ):
        self.torrserver_client = torrserver_client
        self.cache_manager = cache_manager
        self.logger = logger_factory.get_logger("stremio_http_proxy.download_worker", "download_worker.log")
        self.progress_logger = logger_factory.get_logger("stremio_http_proxy.download_progress", "download_progress.log")
        self.worker_id = socket.gethostname()
        self.poll_seconds = poll_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.no_progress_timeout_seconds = no_progress_timeout_seconds
        self.min_progress_bytes = min_progress_bytes
        self.min_progress_window_seconds = min_progress_window_seconds
        self.max_total_seconds = max_total_seconds
        self.progress_log_interval_seconds = progress_log_interval_seconds

    async def run_forever(self) -> None:
        while True:
            processed = await self.process_next_job()
            if not processed:
                await asyncio.sleep(self.poll_seconds)

    async def process_next_job(self) -> bool:
        job = await self.cache_manager.claim_next_download(self.worker_id)
        if job is None:
            return False

        self.logger.info("Worker %s picked job %s for %s", self.worker_id, job.job_id, job.cache_key)
        if self.cache_manager.is_ready(job.cache_key):
            self.logger.info("Worker %s skipping job %s because cache is already ready", self.worker_id, job.job_id)
            entry = self.cache_manager.get_entry(job.cache_key)
            self.cache_manager.mark_ready(job.cache_key, Path(entry.file_path).stat().st_size)
            await self.cache_manager.acknowledge_download(job)
            return True

        try:
            self.cache_manager.prune()
            await self._download(job)
            await self.cache_manager.acknowledge_download(job)
            return True
        except Exception as exc:
            error = str(exc)
            self.cache_manager.cleanup_partial(job.cache_key)
            if job.attempt + 1 >= job.max_attempts:
                self.cache_manager.mark_failed(job.cache_key, error, job.attempt + 1)
                self.logger.error("Worker %s discarding job %s: %s", self.worker_id, job.job_id, error)
                await self.cache_manager.move_to_dead_letter(job, error)
                return True

            delay_seconds = self._retry_delay(job.attempt + 1)
            self.cache_manager.mark_failed(job.cache_key, error, job.attempt + 1)
            self.logger.warning("Worker %s retrying job %s in %ss: %s", self.worker_id, job.job_id, delay_seconds, error)
            await self.cache_manager.retry_download(job, delay_seconds, error)
            return True

    async def _download(self, job: DownloadJob) -> None:
        self.cache_manager.mark_downloading(job.cache_key, job.attempt)
        self.cache_manager.touch_processing_lease(job.cache_key, self.worker_id)
        await self.torrserver_client.add_torrent(job.link, job.title, job.poster, job.category)

        download_url = self.torrserver_client.build_play_url(job.link, job.title, job.poster, job.category, job.index)
        timeout = httpx.Timeout(connect=self.connect_timeout_seconds, read=self.no_progress_timeout_seconds, write=30, pool=30)
        tmp_path = self.cache_manager.prepare_download_path(job.cache_key)

        downloaded_bytes = 0
        started_at = time.time()
        window_started_at = started_at
        bytes_at_window_start = 0
        last_progress_log_at = started_at

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", download_url) as response:
                response.raise_for_status()
                expected_bytes = self._expected_bytes(response)
                with tmp_path.open("wb") as handle:
                    async for chunk in response.aiter_bytes(1024 * 512):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded_bytes += len(chunk)
                        now = time.time()
                        elapsed_seconds = max(now - started_at, 0.001)
                        speed_bytes_per_second = downloaded_bytes / elapsed_seconds
                        progress_percent = self._progress_percent(downloaded_bytes, expected_bytes)
                        if now - started_at > self.max_total_seconds:
                            raise TimeoutError("download exceeded maximum duration")
                        if now - window_started_at >= self.min_progress_window_seconds:
                            if downloaded_bytes - bytes_at_window_start < self.min_progress_bytes:
                                raise TimeoutError("download progress stayed below threshold")
                            window_started_at = now
                            bytes_at_window_start = downloaded_bytes
                        if now - last_progress_log_at >= self.progress_log_interval_seconds:
                            self.cache_manager.mark_progress(
                                job.cache_key,
                                downloaded_bytes,
                                expected_bytes,
                                progress_percent,
                                speed_bytes_per_second,
                            )
                            self.cache_manager.touch_processing_lease(job.cache_key, self.worker_id)
                            self.progress_logger.info(
                                "worker=%s job=%s cache_key=%s downloaded_mb=%.2f total_mb=%s progress_pct=%s speed_mbps=%.2f elapsed_s=%.0f",
                                self.worker_id,
                                job.job_id,
                                job.cache_key,
                                downloaded_bytes / (1024 * 1024),
                                self._format_total_mb(expected_bytes),
                                self._format_progress(progress_percent),
                                speed_bytes_per_second / (1024 * 1024),
                                elapsed_seconds,
                            )
                            last_progress_log_at = now

                self.cache_manager.mark_progress(
                    job.cache_key,
                    downloaded_bytes,
                    expected_bytes,
                    self._progress_percent(downloaded_bytes, expected_bytes),
                    downloaded_bytes / max(time.time() - started_at, 0.001),
                )

        min_size_bytes = self.cache_manager.get_min_cache_size()
        if downloaded_bytes < min_size_bytes:
            raise RuntimeError(
                f"Download rifiutato: il file è troppo piccolo ({downloaded_bytes} byte). "
                f"Soglia minima: {min_size_bytes} byte."
            )

        size_bytes = self.cache_manager.finalize_download(job.cache_key)
        self.cache_manager.mark_ready(job.cache_key, size_bytes)
        self.logger.info("Worker %s completed job %s for %s (%s bytes)", self.worker_id, job.job_id, job.cache_key, size_bytes)

    def _retry_delay(self, attempt: int) -> int:
        schedule = {1: 30, 2: 300, 3: 1800}
        return schedule.get(attempt, 1800)

    def _expected_bytes(self, response: httpx.Response) -> int | None:
        header = response.headers.get("content-length")
        if header and header.isdigit():
            return int(header)
        return None

    def _progress_percent(self, downloaded_bytes: int, expected_bytes: int | None) -> float | None:
        if not expected_bytes or expected_bytes <= 0:
            return None
        return round(min((downloaded_bytes / expected_bytes) * 100, 100), 2)

    def _format_total_mb(self, expected_bytes: int | None) -> str:
        if expected_bytes is None:
            return "unknown"
        return f"{expected_bytes / (1024 * 1024):.2f}"

    def _format_progress(self, progress_percent: float | None) -> str:
        if progress_percent is None:
            return "unknown"
        return f"{progress_percent:.2f}"
