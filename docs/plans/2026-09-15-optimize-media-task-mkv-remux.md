# Optimize Media Task (MKV Remux / Transcode) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically optimize/remux cached media files into MKV container format using ffmpeg when a non-standard or problematic container (such as AVI) is downloaded, ensuring maximum compatibility with Amazon FireStick and smart TV players.

**Architecture:** A new task `optimize_media` implemented in `stremio_http_proxy/task/optimize_media_task.py` and registered in `TaskRegistry`. Triggered on download completion in `DownloadWorkerService`. It detects media container type using `detect_media_type`; if already a compatible container (MKV/MP4/WebM), it immediately skips; otherwise, it executes a fast ffmpeg remux (`-map 0 -c copy`), with a fallback transcode if needed, atomically replaces the cached `.media` file, and updates the database entry with the new size.

**Tech Stack:** Python 3.12, ffmpeg, asyncio subprocess, SQLAlchemy, SQLite, pytest.

## Global Constraints
- Target container format must be Matroska (`.mkv`) which natively encapsulates all audio/video/subtitle streams and is universally supported on FireStick/ExoPlayer/VLC.
- The conversion must be as fast as possible: remux with `-map 0 -c copy` must be attempted first (taking only seconds with zero CPU re-encoding overhead).
- Fallback transcode must use fast presets (`-c:v copy -c:a aac` then `-preset ultrafast`).
- Replacement of the cached `.media` file must be atomic using temporary files and `os.replace`.
- All tests must pass (122+ tests) with zero regressions.

---

### Task 1: Create `OptimizeMediaTask` in `stremio_http_proxy/task/optimize_media_task.py`

**Files:**
- Create: `stremio_http_proxy/task/optimize_media_task.py`
- Test: `tests/test_optimize_media_task.py`

**Interfaces:**
- Consumes: `AbstractTask`, `CacheManager`, `LoggerFactory`, `detect_media_type`
- Produces: `OptimizeMediaTask(AbstractTask)` with `name = "optimize_media"` and `async def run(arguments: dict[str, Any]) -> bool`

- [ ] **Step 1: Write the failing unit tests for OptimizeMediaTask**

```python
# tests/test_optimize_media_task.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from stremio_http_proxy.task.optimize_media_task import OptimizeMediaTask


class FakeCacheManager:
    def __init__(self, media_path: Path):
        self.media_path = media_path
        self.ready_sizes = {}

    def get_entry(self, cache_key: str):
        mock_entry = MagicMock()
        mock_entry.status.value = "ready"
        return mock_entry

    def parse_cache_key(self, cache_key: str):
        return ("abc123hash", 1)

    def _media_path(self, infohash: str, index: int) -> Path:
        return self.media_path

    def mark_ready(self, cache_key: str, size_bytes: int):
        self.ready_sizes[cache_key] = size_bytes


class FakeLoggerFactory:
    def get_logger(self, name: str, file: str):
        return MagicMock()


@pytest.mark.asyncio
async def test_skips_optimization_if_already_mkv_or_mp4(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"dummy mp4 content")
    mgr = FakeCacheManager(media_file)
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory)

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/mp4", "mp4")):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert "abc123hash:1" not in mgr.ready_sizes


@pytest.mark.asyncio
async def test_remuxes_avi_to_mkv_successfully(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"RIFF....AVI ")
    mgr = FakeCacheManager(media_file)
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory)

    async def fake_ffmpeg(*args, **kwargs):
        # Create output file
        out_file = Path(args[8])
        out_file.write_bytes(b"MATROSKA_MKV_CONTENT")
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/x-msvideo", "avi")), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert media_file.read_bytes() == b"MATROSKA_MKV_CONTENT"
    assert mgr.ready_sizes["abc123hash:1"] == len(b"MATROSKA_MKV_CONTENT")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/michele/.venv/bin/pytest tests/test_optimize_media_task.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stremio_http_proxy.task.optimize_media_task'`

- [ ] **Step 3: Implement `OptimizeMediaTask`**

```python
# stremio_http_proxy/task/optimize_media_task.py
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
        if status_val != "ready":
            self.logger.info("Cache entry %s status is %s (not ready), skipping optimization", cache_key, status_val)
            return True

        infohash, index = self.cache_manager.parse_cache_key(cache_key)
        media_path = self.cache_manager._media_path(infohash, index)
        if not media_path.exists():
            self.logger.warning("Media file %s does not exist on disk", media_path)
            return True

        _, ext = detect_media_type(media_path)
        if ext.lower() in COMPATIBLE_EXTENSIONS:
            self.logger.info("Media %s is already in compatible container (%s), skipping", cache_key, ext)
            return True

        self.logger.info("Media %s container (%s) needs optimization. Starting ffmpeg remux to MKV...", cache_key, ext)
        temp_mkv_path = media_path.with_suffix(".opt.mkv")

        success = await self._remux_to_mkv(media_path, temp_mkv_path)
        if not success:
            self.logger.warning("Fast remux failed for %s, attempting transcode fallback...", cache_key)
            success = await self._transcode_fallback(media_path, temp_mkv_path)

        if success and temp_mkv_path.exists() and temp_mkv_path.stat().st_size > 0:
            temp_mkv_path.replace(media_path)
            new_size = media_path.stat().st_size
            self.cache_manager.mark_ready(cache_key, new_size)
            self.logger.info("Media %s successfully optimized to MKV (size: %s bytes)", cache_key, new_size)
            return True
        else:
            if temp_mkv_path.exists():
                temp_mkv_path.unlink(missing_ok=True)
            self.logger.error("Failed to optimize media %s to MKV; original file preserved", cache_key)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/michele/.venv/bin/pytest tests/test_optimize_media_task.py -v`
Expected: PASS (2 passed)

---

### Task 2: Register `OptimizeMediaTask` in `TaskRegistry` and `DefaultContainer`

**Files:**
- Modify: `stremio_http_proxy/container/default_container.py`
- Modify: `stremio_http_proxy/task/__init__.py`
- Test: `tests/test_default_container.py`

**Interfaces:**
- Consumes: `OptimizeMediaTask`, `TaskRegistry`
- Produces: `optimize_media` task available in registry for task workers

- [ ] **Step 1: Write test verifying OptimizeMediaTask is registered**

Add to `tests/test_default_container.py`:
```python
def test_default_container_registers_optimize_media_task(monkeypatch):
    DefaultContainer.instance = None
    monkeypatch.setattr("stremio_http_proxy.container.default_container.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("APP_SECRET", "test-secret")
    container = DefaultContainer()
    registry = container.get(TaskRegistry)
    assert registry.has("optimize_media")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/michele/.venv/bin/pytest tests/test_default_container.py::test_default_container_registers_optimize_media_task -v`
Expected: FAIL (`assert False`)

- [ ] **Step 3: Update `default_container.py` and `stremio_http_proxy/task/__init__.py`**

In `stremio_http_proxy/task/__init__.py`, export `OptimizeMediaTask`.
In `stremio_http_proxy/container/default_container.py`:
```python
optimize_media_task = OptimizeMediaTask(cache_manager, logger_factory)
task_registry.register(optimize_media_task)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/michele/.venv/bin/pytest tests/test_default_container.py::test_default_container_registers_optimize_media_task -v`
Expected: PASS

---

### Task 3: Enqueue `optimize_media` on download completion in `DownloadWorkerService`

**Files:**
- Modify: `stremio_http_proxy/service/download_worker_service.py`
- Modify: `stremio_http_proxy/container/default_container.py`
- Test: `tests/test_download_worker_service.py`

**Interfaces:**
- Consumes: `task_service.enqueue_task("optimize_media", {"cache_key": job.cache_key})`
- Produces: Triggered optimization whenever a download completes and is marked ready

- [ ] **Step 1: Write failing test in `tests/test_download_worker_service.py`**

```python
def test_finalize_download_enqueues_optimize_media_task():
    # Test that finalize_download triggers enqueue_task("optimize_media", ...)
```

- [ ] **Step 2: Run test to verify failure**

- [ ] **Step 3: Wire `task_service` into `DownloadWorkerService`**

In `DownloadWorkerService`:
Add optional `task_service: TaskService | None = None` to `__init__`.
In `_download_http_stream` (and HLS/ffmpeg completion):
After `self.cache_manager.mark_ready(job.cache_key, size_bytes)`:
```python
if self.task_service is not None:
    try:
        self.task_service.enqueue_task(
            name="optimize_media",
            arguments={"cache_key": job.cache_key},
            deduplicate=True,
        )
    except Exception as e:
        self.logger.warning("Failed to enqueue optimize_media task for %s: %s", job.cache_key, e)
```
In `default_container.py`, pass `task_service=task_service` to `DownloadWorkerService`.

- [ ] **Step 4: Run test suite to verify it passes**

Run: `/Users/michele/.venv/bin/pytest tests/test_download_worker_service.py -v`
Expected: PASS

---

### Task 4: End-to-End Verification and Live Validation

**Files:**
- Test all: `tests/`
- Documentation: `README.md`

- [ ] **Step 1: Run complete test suite**

Run: `/Users/michele/.venv/bin/pytest`
Expected: 125+ passed, 0 failures.

- [ ] **Step 2: Commit and push changes to `master`**

- [ ] **Step 3: Verify with real sample on production**
Ensure `task_worker` picks up the task and remuxes AVI to MKV seamlessly.
