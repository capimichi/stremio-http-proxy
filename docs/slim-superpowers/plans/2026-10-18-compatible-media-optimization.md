# Compatible Media Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `compatible` media optimization mode in `stremio-http-proxy` that fast-remuxes all cached media into MKV with Cues at the front (`-map 0 -c copy -cues_to_front true -f matroska`), preserves all streams/tracks with fallback conversions when needed, sets `notWebReady: false` for ready cache streams, and removes legacy `mkv` mode.

**Architecture:** 
1. `OptimizeMediaTask` executes `_run_compatible_optimization` when `optimize_media_target == "compatible"`:
   - Primary: Fast stream-copy remux (`ffmpeg -y -i <src> -map 0 -c copy -cues_to_front true -f matroska <tmp.mkv>`)
   - Fallback 1: Audio/subtitle transcode (`-map 0 -c:v copy -c:a aac -c:s copy -cues_to_front true -f matroska`)
   - Fallback 2: Full video transcode (`-map 0 -c:v libx264 -preset ultrafast -crf 22 -c:a aac -c:s copy -cues_to_front true -f matroska`)
   - Fallback 3: Preserve original file and mark ready.
2. `StreamRewriteService` evaluates `_is_web_ready` as `True` when `optimize_media_target == "compatible"` for ready cache entries, ensuring `notWebReady: false` in `behaviorHints`.
3. `DefaultContainer` sets default `OPTIMIZE_MEDIA_TARGET` to `compatible`.

**Tech Stack:** Python 3.11+, Celery, FFmpeg / FFprobe, FastAPI / Starlette, pytest.

## Global Constraints

- Do not use config files or config classes. Read environment variables in `stremio_http_proxy/container/default_container.py` and pass values directly into constructors.
- Keep every `__init__.py` file empty.
- Use `injector` for dependency injection.
- Do not use `dataclass`. Use Pydantic models in `model/`.
- No backward compatibility alias for `mkv`. The valid modes are `compatible`, `web_ready_mp4`, and `disabled`/`none`/`false`.
- All streams (video, audio, subtitles, chapters) must be preserved using `-map 0`.

---

### Task 1: Implement `_run_compatible_optimization` in `OptimizeMediaTask`

**Files:**
- Modify: `stremio_http_proxy/task/optimize_media_task.py:79-81,253-335`
- Test: `tests/test_optimize_media_task.py`

**Interfaces:**
- Consumes: `CacheManager.mark_ready(cache_key: str, size_bytes: int)`, `CacheManager._media_path(infohash: str, index: int)`
- Produces: `OptimizeMediaTask._run_compatible_optimization(cache_key: str, media_path: Path, orig_size: int) -> bool`

- [x] **Step 1: Write failing tests for compatible optimization in `tests/test_optimize_media_task.py`**

Add tests covering:
1. Fast remux with `-c copy -cues_to_front true -map 0 -f matroska` on any source format (including existing MKVs, AVIs, MP4s).
2. Fallback to audio transcode (`-c:v copy -c:a aac -c:s copy -cues_to_front true -f matroska`) when fast remux fails.
3. Fallback to full video transcode (`-c:v libx264 -preset ultrafast -crf 22 -c:a aac -c:s copy -cues_to_front true -f matroska`) when audio transcode fails.
4. Fallback to original file marked ready when all FFmpeg steps fail.

Add to `tests/test_optimize_media_task.py`:
```python
@pytest.mark.asyncio
async def test_compatible_optimization_runs_fast_remux_with_cues_to_front(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"RAW_TORRENT_MKV_OR_AVI")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target="compatible")

    executed_cmd = []

    async def fake_ffmpeg(cmd):
        executed_cmd.extend(cmd)
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"OPTIMIZED_COMPATIBLE_MKV")
        return True

    with patch.object(task, "_run_ffmpeg", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert media_file.read_bytes() == b"OPTIMIZED_COMPATIBLE_MKV"
    assert mgr.ready_sizes["abc123hash:1"] == len(b"OPTIMIZED_COMPATIBLE_MKV")
    assert "-map" in executed_cmd
    assert executed_cmd[executed_cmd.index("-map") + 1] == "0"
    assert "-c" in executed_cmd
    assert executed_cmd[executed_cmd.index("-c") + 1] == "copy"
    assert "-cues_to_front" in executed_cmd
    assert executed_cmd[executed_cmd.index("-cues_to_front") + 1] == "true"
    assert "-f" in executed_cmd
    assert executed_cmd[executed_cmd.index("-f") + 1] == "matroska"


@pytest.mark.asyncio
async def test_compatible_optimization_audio_fallback(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"SOURCE_CONTENT")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target="compatible")

    calls = []

    async def fake_ffmpeg(cmd):
        calls.append(list(cmd))
        if len(calls) == 1:
            return False  # Fast copy fails
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"AUDIO_TRANSCODED_MKV")
        return True

    with patch.object(task, "_run_ffmpeg", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert len(calls) == 2
    assert "-c:a" in calls[1]
    assert calls[1][calls[1].index("-c:a") + 1] == "aac"
    assert "-c:v" in calls[1]
    assert calls[1][calls[1].index("-c:v") + 1] == "copy"
    assert "-cues_to_front" in calls[1]
    assert media_file.read_bytes() == b"AUDIO_TRANSCODED_MKV"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_optimize_media_task.py::test_compatible_optimization_runs_fast_remux_with_cues_to_front -v`
Expected: FAIL (because `compatible` mode is routed to `_run_web_ready_optimization` or unhandled)

- [x] **Step 3: Implement `_run_compatible_optimization` in `OptimizeMediaTask`**

In `stremio_http_proxy/task/optimize_media_task.py`:
1. Change routing in `run()`:
```python
        if self.optimize_media_target == "compatible":
            return await self._run_compatible_optimization(cache_key, media_path, orig_size)
```
2. Replace `_run_legacy_mkv_optimization` with:
```python
    async def _run_compatible_optimization(self, cache_key: str, media_path: Path, orig_size: int) -> bool:
        self.logger.info("Starting compatible MKV optimization for %s...", cache_key)
        temp_mkv_path = media_path.with_suffix(".opt.mkv")

        # Phase 1: Fast remux (stream copy) with cues to front
        success = await self._remux_compatible(media_path, temp_mkv_path)
        if not success:
            self.logger.warning("Fast remux failed for %s, attempting audio transcode fallback...", cache_key)
            success = await self._transcode_audio_fallback(media_path, temp_mkv_path)

        if not success:
            self.logger.warning("Audio fallback failed for %s, attempting full video transcode fallback...", cache_key)
            success = await self._transcode_full_fallback(media_path, temp_mkv_path)

        if success and temp_mkv_path.exists() and temp_mkv_path.stat().st_size > 0:
            temp_mkv_path.replace(media_path)
            try:
                media_path.chmod(0o666)
            except Exception:
                pass
            new_size = media_path.stat().st_size
            self.cache_manager.mark_ready(cache_key, new_size)
            self.logger.info("Media %s successfully optimized to compatible MKV (size: %s bytes)", cache_key, new_size)
            return True
        else:
            if temp_mkv_path.exists():
                temp_mkv_path.unlink(missing_ok=True)
            self.cache_manager.mark_ready(cache_key, orig_size)
            self.logger.error("Failed to optimize media %s; original file preserved and marked ready", cache_key)
            return False

    async def _remux_compatible(self, src: Path, dest: Path) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-map", "0",
            "-c", "copy",
            "-cues_to_front", "true",
            "-f", "matroska",
            str(dest),
        ]
        return await self._run_ffmpeg(cmd)

    async def _transcode_audio_fallback(self, src: Path, dest: Path) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-map", "0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-c:s", "copy",
            "-cues_to_front", "true",
            "-f", "matroska",
            str(dest),
        ]
        return await self._run_ffmpeg(cmd)

    async def _transcode_full_fallback(self, src: Path, dest: Path) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-map", "0",
            "-c:v", "libx264",
            "-preset", self.preset,
            "-crf", "22",
            "-c:a", "aac",
            "-c:s", "copy",
            "-cues_to_front", "true",
            "-f", "matroska",
            str(dest),
        ]
        return await self._run_ffmpeg(cmd)
```
3. Remove old `_run_legacy_mkv_optimization`, `_remux_to_mkv`, `_transcode_fallback`.
4. Update existing tests in `tests/test_optimize_media_task.py` that referenced `optimize_media_target="mkv"` to `"compatible"`.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_optimize_media_task.py -v`
Expected: ALL PASS

---

### Task 2: Implement `_is_web_ready` and `notWebReady` Handling in `StreamRewriteService`

**Files:**
- Modify: `stremio_http_proxy/service/stream_rewrite_service.py:177-179,199-213,294-304`
- Test: `tests/test_stream_rewrite_service.py`

**Interfaces:**
- Consumes: `CacheManager.is_ready(cache_key: str) -> bool`, `CacheManager.get_ready_entries_by_content(...)`
- Produces: `StreamRewriteService._is_web_ready(infohash: str | None, index: int | None) -> bool`

- [x] **Step 1: Write failing test in `tests/test_stream_rewrite_service.py`**

Add test checking that for `optimize_media_target="compatible"`:
1. When a cache entry is `READY`, `_is_web_ready` returns `True`, and injected stream has `behaviorHints: {"notWebReady": False}`.
2. Rewritten existing streams with matching ready cache entry get `notWebReady: False`.

```python
@pytest.mark.asyncio
async def test_stream_rewrite_sets_not_web_ready_false_for_compatible_ready_entry():
    from stremio_http_proxy.model.cache_entry import CacheEntry as CacheEntryModel
    from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum

    hash1 = "a" * 40
    cache_manager = MagicMock()
    cache_manager.build_cache_key.return_value = f"{hash1}:1"
    cache_manager.is_ready.return_value = True
    cache_manager.parse_cache_key.return_value = (hash1, 1)

    cached_entry = CacheEntryModel(
        cache_key=f"{hash1}:1",
        infohash=hash1,
        cache_index=1,
        status=CacheEntryStatusEnum.READY.value,
        title="Movie.1080p.mkv",
        source_link=f"magnet:?xt=urn:btih:{hash1}",
        file_path="/var/cache/hash1_1.mkv",
        tmp_path="/var/cache/hash1_1.tmp",
        size_bytes=2 * 1024 * 1024 * 1024,
    )
    cache_manager.get_ready_entries_by_content.return_value = [cached_entry]

    service = StreamRewriteService(
        public_base_url="http://localhost:8691",
        cache_manager=cache_manager,
        cache_enabled=True,
        optimize_media_target="compatible",
    )

    upstream_payload = {
        "streams": [
            {
                "name": "Torrentio 1080p",
                "title": "Movie 1080p",
                "infoHash": hash1,
                "fileIdx": 1,
            }
        ]
    }

    result = await service.rewrite(
        upstream_payload,
        category="movie",
        content_type="movie",
        content_id="tt0304141",
    )

    streams = result.get("streams", [])
    assert len(streams) >= 1
    first_stream = streams[0]
    assert first_stream["behaviorHints"]["notWebReady"] is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stream_rewrite_service.py::test_stream_rewrite_sets_not_web_ready_false_for_compatible_ready_entry -v`
Expected: FAIL (because `_is_web_ready` checks `ext in ("mp4", "webm")` and returns `False` for MKV)

- [x] **Step 3: Update `StreamRewriteService` logic**

In `stremio_http_proxy/service/stream_rewrite_service.py`:
Update `_is_web_ready`:
```python
    def _is_web_ready(self, infohash: str | None, index: int | None) -> bool:
        if self.optimize_media_target == "web_ready_mp4":
            return True
        if not infohash:
            return False
        if self.optimize_media_target == "compatible":
            # In compatible mode, any READY entry in cache is indexed with cues at front
            cache_key = f"{infohash}:{index if index is not None else 0}"
            if self.cache_manager and hasattr(self.cache_manager, "is_ready"):
                if self.cache_manager.is_ready(cache_key):
                    return True
            return False
        try:
            if hasattr(self.cache_manager, "_media_path"):
                media_path = self.cache_manager._media_path(infohash, index or 0)
                if media_path and media_path.exists():
                    from stremio_http_proxy.helper.media_type_helper import detect_media_type
                    _, ext = detect_media_type(media_path)
                    return ext in ("mp4", "webm")
        except Exception:
            pass
        return False
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stream_rewrite_service.py -v`
Expected: ALL PASS

---

### Task 3: Update `DefaultContainer` Configuration

**Files:**
- Modify: `stremio_http_proxy/container/default_container.py:117`
- Test: `tests/test_container.py` (or existing container tests)

**Interfaces:**
- Consumes: `os.environ["OPTIMIZE_MEDIA_TARGET"]`
- Produces: `DefaultContainer.optimize_media_target` defaulting to `"compatible"`

- [x] **Step 1: Write test for container default value**

Verify that `DefaultContainer` initializes `optimize_media_target` with default `"compatible"`.
- [x] **Step 2: Update `default_container.py`**

In `stremio_http_proxy/container/default_container.py`:
Change:
```python
self.optimize_media_target = os.environ.get("OPTIMIZE_MEDIA_TARGET", "compatible").lower()
```
- [x] **Step 3: Run full test suite**

Run: `pytest -q`
Expected: 100% PASS

---

### Task 4: Full Test Suite Verification

**Files:**
- Verify: all test files

- [x] **Step 1: Run complete test suite**

Run: `pytest -v`
Expected: 180+ tests passing without warnings or regressions.
