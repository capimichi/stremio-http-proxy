import asyncio
import socket
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.manager.hls_chunk_manager import HlsChunkManager
from stremio_http_proxy.model.download_job import DownloadJob
from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService


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
        hls_chunk_manager: HlsChunkManager | None = None,
        prefetch_min_progress_bytes: int = 1048576,
        next_episode_prefetch_service: NextEpisodePrefetchService | None = None,
        prefetch_poll_seconds: int = 15,
        task_service: Any = None,
    ):
        self.torrserver_client = torrserver_client
        self.cache_manager = cache_manager
        self.hls_chunk_manager = hls_chunk_manager
        self.prefetch_min_progress_bytes = prefetch_min_progress_bytes
        self.next_episode_prefetch_service = next_episode_prefetch_service
        self.task_service = task_service
        self.logger = logger_factory.get_logger("stremio_http_proxy.download_worker", "download_worker.log")
        self.progress_logger = logger_factory.get_logger("stremio_http_proxy.download_progress", "download_progress.log")
        self.worker_id = socket.gethostname()
        self.poll_seconds = poll_seconds
        self.prefetch_poll_seconds = prefetch_poll_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.no_progress_timeout_seconds = no_progress_timeout_seconds
        self.min_progress_bytes = min_progress_bytes
        self.min_progress_window_seconds = min_progress_window_seconds
        self.max_total_seconds = max_total_seconds
        self.progress_log_interval_seconds = progress_log_interval_seconds

    def _required_min_progress_bytes(self, job: DownloadJob) -> int:
        if job.trigger == "next_episode_prefetch":
            return self.prefetch_min_progress_bytes
        return self.min_progress_bytes

    async def run_forever(self) -> None:
        await asyncio.gather(
            self.run_download_loop(),
            self.run_task_loop(),
        )

    async def run_download_loop(self) -> None:
        while True:
            try:
                processed = await self.process_next_job()
                if not processed:
                    await asyncio.sleep(self.poll_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.exception("Unhandled exception in download worker loop")
                await asyncio.sleep(self.poll_seconds)

    async def run_task_loop(self) -> None:
        while True:
            try:
                processed = await self.process_next_task()
                if not processed:
                    await asyncio.sleep(self.prefetch_poll_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.exception("Unhandled exception in task worker loop")
                await asyncio.sleep(self.prefetch_poll_seconds)

    async def run_prefetch_loop(self) -> None:
        await self.run_task_loop()

    async def process_next_task(self) -> bool:
        if self.task_service:
            return await self.task_service.process_next_task(self.worker_id)
        return False

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
            if job.attempt + 1 >= job.max_attempts or self._is_permanent_error(exc):
                self.cache_manager.mark_failed(job.cache_key, error, job.attempt + 1)
                self.logger.error(
                    "Worker %s discarding job %s (permanent error or max attempts reached): %s",
                    self.worker_id,
                    job.job_id,
                    error,
                )
                await self.cache_manager.move_to_dead_letter(job, error)
                if self.next_episode_prefetch_service and job.trigger == "next_episode_prefetch":
                    try:
                        await self.next_episode_prefetch_service.on_download_failed(
                            job.content_type, job.content_id, job.category
                        )
                    except Exception:
                        self.logger.exception("Error triggering fallback for prefetch job %s", job.job_id)
                return True

            delay_seconds = self._retry_delay(job.attempt + 1)
            self.cache_manager.mark_failed(job.cache_key, error, job.attempt + 1)
            self.logger.warning("Worker %s retrying job %s in %ss: %s", self.worker_id, job.job_id, delay_seconds, error)
            await self.cache_manager.retry_download(job, delay_seconds, error)
            return True

    @staticmethod
    def _is_permanent_error(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in (400, 401, 403, 404, 410, 451)
        err_msg = str(exc).lower()
        return any(
            code in err_msg
            for code in (
                "401 unauthorized",
                "403 forbidden",
                "404 not found",
                "410 gone",
                "451 unavailable for legal reasons",
                "access denied",
            )
        )

    async def _download(self, job: DownloadJob) -> None:
        self.cache_manager.mark_downloading(job.cache_key, job.attempt)
        self.cache_manager.touch_processing_lease(job.cache_key, self.worker_id)

        if job.link.startswith(("http://", "https://")):
            if self._is_hls_stream(job.link):
                await self._download_hls(job, job.link)
            else:
                await self._download_http_stream(job, job.link)
        else:
            await self.torrserver_client.add_torrent(job.link, job.title, job.poster, job.category)
            file_index = job.index
            if hasattr(self.torrserver_client, "resolve_file_index"):
                try:
                    resolved_index = await self.torrserver_client.resolve_file_index(
                        job.link,
                        index=file_index,
                        content_id=job.content_id,
                        content_type=job.content_type,
                        title=job.title,
                        poster=job.poster,
                        category=job.category,
                    )
                except TypeError:
                    resolved_index = await self.torrserver_client.resolve_file_index(
                        job.link,
                        content_id=job.content_id,
                        content_type=job.content_type,
                        title=job.title,
                        poster=job.poster,
                        category=job.category,
                    )
                if resolved_index:
                    file_index = resolved_index
                    job.index = resolved_index
            elif file_index is None or file_index <= 0:
                file_index = 1
                job.index = 1
            build_url = getattr(self.torrserver_client, "build_download_url", self.torrserver_client.build_play_url)
            download_url = build_url(job.link, job.title, job.poster, job.category, file_index)
            await self._download_http_stream(job, download_url)

    def _is_hls_stream(self, url: str) -> bool:
        return "/proxy/hls" in url or ".m3u8" in url

    async def _download_http_stream(self, job: DownloadJob, download_url: str) -> None:
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
                            if downloaded_bytes - bytes_at_window_start < self._required_min_progress_bytes(job):
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
        self._on_download_completed(job.cache_key, size_bytes)
        self.logger.info("Worker %s completed job %s for %s (%s bytes)", self.worker_id, job.job_id, job.cache_key, size_bytes)

    async def _download_hls(self, job: DownloadJob, url: str) -> None:
        if self.hls_chunk_manager is not None:
            try:
                await self._download_hls_chunks(job, url)
                return
            except Exception as e:
                if self._is_permanent_error(e):
                    self.logger.error("HLS chunk download encountered permanent error for %s: %s", job.cache_key, e)
                    raise
                self.logger.warning("Chunk-based HLS download failed for %s (%s), falling back to ffmpeg direct stream", job.cache_key, e)

        await self._download_hls_ffmpeg(job, url)

    async def _resolve_hls_chunks(self, url: str) -> list[str]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.connect_timeout_seconds) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.text
            base_url = str(resp.url)
            lines = content.splitlines()

            if any(l.strip().startswith("#EXT-X-STREAM-INF") for l in lines):
                variant_url = None
                expect_variant = False
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("#EXT-X-STREAM-INF"):
                        expect_variant = True
                        continue
                    if expect_variant and not stripped.startswith("#") and stripped:
                        variant_url = urljoin(base_url, stripped)
                        if variant_url.startswith("http://") and base_url.startswith("https://"):
                            variant_url = "https://" + variant_url[7:]
                        break
                if not variant_url:
                    return []
                resp = await client.get(variant_url)
                resp.raise_for_status()
                content = resp.text
                base_url = str(resp.url)
                lines = content.splitlines()

            chunk_urls: list[str] = []
            expect_chunk = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#EXTINF"):
                    expect_chunk = True
                    continue
                if expect_chunk and not stripped.startswith("#") and stripped:
                    chunk_url = urljoin(base_url, stripped)
                    if chunk_url.startswith("http://") and base_url.startswith("https://"):
                        chunk_url = "https://" + chunk_url[7:]
                    chunk_urls.append(chunk_url)
                    expect_chunk = False

            return chunk_urls

    async def _download_hls_chunks(self, job: DownloadJob, url: str) -> None:
        chunk_urls = self.hls_chunk_manager.get_playlist_metadata(job.cache_key)
        if not chunk_urls:
            chunk_urls = await self._resolve_hls_chunks(url)
            if chunk_urls:
                self.hls_chunk_manager.save_playlist_metadata(job.cache_key, chunk_urls)

        if not chunk_urls:
            raise RuntimeError(f"Could not resolve any HLS chunks from {url}")

        total_chunks = len(chunk_urls)
        self.logger.info("Starting chunk-based HLS download for %s: %d total chunks", job.cache_key, total_chunks)

        started_at = time.time()
        last_progress_log_at = started_at
        window_started_at = started_at
        bytes_at_window_start = self.hls_chunk_manager.get_chunks_total_bytes(job.cache_key)

        async with httpx.AsyncClient(follow_redirects=True, timeout=self.no_progress_timeout_seconds) as client:
            for i, chunk_url in enumerate(chunk_urls):
                now = time.time()
                if now - started_at > self.max_total_seconds:
                    raise TimeoutError("HLS chunk download exceeded maximum duration")

                if not self.hls_chunk_manager.has_chunk(job.cache_key, i):
                    await self.hls_chunk_manager.get_or_download_chunk(
                        job.cache_key,
                        i,
                        chunk_url,
                        client=client,
                        timeout=self.no_progress_timeout_seconds,
                    )
                    await asyncio.sleep(0.02)

                now = time.time()
                downloaded_indices = self.hls_chunk_manager.get_downloaded_indices(job.cache_key)
                downloaded_count = len(downloaded_indices)
                downloaded_bytes = self.hls_chunk_manager.get_chunks_total_bytes(job.cache_key)
                elapsed_seconds = max(now - started_at, 0.001)
                speed_bytes_per_second = downloaded_bytes / elapsed_seconds
                progress_percent = (downloaded_count / total_chunks) * 100.0

                if now - window_started_at >= self.min_progress_window_seconds:
                    if downloaded_bytes - bytes_at_window_start < self._required_min_progress_bytes(job):
                        raise TimeoutError("HLS chunk download progress stayed below threshold")
                    window_started_at = now
                    bytes_at_window_start = downloaded_bytes

                if now - last_progress_log_at >= self.progress_log_interval_seconds or i == total_chunks - 1:
                    self.cache_manager.mark_progress(
                        job.cache_key,
                        downloaded_bytes,
                        None,
                        progress_percent,
                        speed_bytes_per_second,
                    )
                    self.cache_manager.touch_processing_lease(job.cache_key, self.worker_id)
                    self.progress_logger.info(
                        "worker=%s job=%s cache_key=%s chunks=%d/%d (%.1f%%) downloaded_mb=%.2f speed_mbps=%.2f elapsed_s=%.0f",
                        self.worker_id,
                        job.job_id,
                        job.cache_key,
                        downloaded_count,
                        total_chunks,
                        progress_percent,
                        downloaded_bytes / (1024 * 1024),
                        speed_bytes_per_second / (1024 * 1024),
                        elapsed_seconds,
                    )
                    last_progress_log_at = now

        tmp_path = self.cache_manager.prepare_download_path(job.cache_key)
        if tmp_path.exists():
            tmp_path.unlink()

        merged = await self.hls_chunk_manager.merge_chunks_to_media(job.cache_key, total_chunks, tmp_path)
        if not merged:
            raise RuntimeError(f"Failed to merge {total_chunks} chunks into {tmp_path}")

        downloaded_bytes = tmp_path.stat().st_size if tmp_path.exists() else 0
        min_size_bytes = self.cache_manager.get_min_cache_size()
        if downloaded_bytes < min_size_bytes:
            raise RuntimeError(
                f"Download rifiutato: il file è troppo piccolo ({downloaded_bytes} byte). "
                f"Soglia minima: {min_size_bytes} byte."
            )

        self.cache_manager.mark_progress(
            job.cache_key,
            downloaded_bytes,
            downloaded_bytes,
            100.0,
            downloaded_bytes / max(time.time() - started_at, 0.001),
        )

        size_bytes = self.cache_manager.finalize_download(job.cache_key)
        self._on_download_completed(job.cache_key, size_bytes)
        self.logger.info("Worker %s completed HLS job %s for %s (%s bytes)", self.worker_id, job.job_id, job.cache_key, size_bytes)

        asyncio.create_task(self._delayed_chunks_cleanup(job.cache_key, delay_seconds=1800))

    async def _delayed_chunks_cleanup(self, cache_key: str, delay_seconds: int = 1800) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            if self.hls_chunk_manager:
                self.hls_chunk_manager.cleanup_chunks(cache_key)
        except Exception:
            pass

    async def _download_hls_ffmpeg(self, job: DownloadJob, url: str) -> None:
        tmp_path = self.cache_manager.prepare_download_path(job.cache_key)
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
            "-c",
            "copy",
            "-f",
            "mp4",
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
                raise TimeoutError("download exceeded maximum duration")

            if now - window_started_at >= self.min_progress_window_seconds:
                if downloaded_bytes - bytes_at_window_start < self._required_min_progress_bytes(job):
                    proc.kill()
                    await proc.wait()
                    raise TimeoutError("download progress stayed below threshold")
                window_started_at = now
                bytes_at_window_start = downloaded_bytes

            if now - last_progress_log_at >= self.progress_log_interval_seconds:
                self.cache_manager.mark_progress(
                    job.cache_key,
                    downloaded_bytes,
                    None,
                    None,
                    speed_bytes_per_second,
                )
                self.cache_manager.touch_processing_lease(job.cache_key, self.worker_id)
                self.progress_logger.info(
                    "worker=%s job=%s cache_key=%s downloaded_mb=%.2f total_mb=unknown progress_pct=unknown speed_mbps=%.2f elapsed_s=%.0f",
                    self.worker_id,
                    job.job_id,
                    job.cache_key,
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
            job.cache_key,
            downloaded_bytes,
            downloaded_bytes,
            100.0,
            downloaded_bytes / max(time.time() - started_at, 0.001),
        )

        size_bytes = self.cache_manager.finalize_download(job.cache_key)
        self._on_download_completed(job.cache_key, size_bytes)
        self.logger.info("Worker %s completed job %s for %s (%s bytes)", self.worker_id, job.job_id, job.cache_key, size_bytes)

    def _on_download_completed(self, cache_key: str, size_bytes: int) -> None:
        if self.task_service is not None:
            self.cache_manager.mark_optimizing(cache_key, size_bytes)
            try:
                self.task_service.enqueue_task(
                    name="optimize_media",
                    arguments={"cache_key": cache_key},
                    deduplicate=True,
                )
            except Exception as e:
                self.logger.warning("Failed to enqueue optimize_media task for %s: %s; falling back to ready", cache_key, e)
                self.cache_manager.mark_ready(cache_key, size_bytes)
        else:
            self.cache_manager.mark_ready(cache_key, size_bytes)

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
