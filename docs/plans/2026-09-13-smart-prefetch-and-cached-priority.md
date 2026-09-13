# Smart Prefetch and Cached Stream Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve prefetch reliability by filtering zero-seeders, increasing timeouts, relaxing background progress thresholds, downloading one candidate at a time with automatic cascade fallback until N cached copies are reached (default 1), making all parameters configurable via environment variables with `.env.example`, and stably prioritizing cached streams at the top of stream responses.

**Architecture:** 
1. `StreamRewriteService` parses stream metadata (seeders and size) and stably sorts cached streams to the very top of `streams` array.
2. `NextEpisodePrefetchService` filters out 0-seeder streams, sorts candidates by health/seeders, and manages cascade fallback (enqueues 1 candidate at a time, checks target completed count `N`, and enqueues next candidate on permanent failure).
3. `DownloadWorkerService` differentiates between playback downloads and prefetch downloads for progress thresholds, and uses configurable extended timeouts.
4. `DefaultContainer` wires all new environment variables with safe defaults and documents them in `.env.example`.

**Tech Stack:** Python 3.12, FastAPI, Injector, Pydantic, pytest, pytest-asyncio, httpx.

## Global Constraints

- Never break existing HTTP passthrough redirect logic.
- Keep tests fast and isolated (mock upstream HTTP and TorrServer calls).
- All new configurations must have sensible defaults if absent from `.env`.
- Preserves stream list stability when sorting cached streams to the top.

---

### Task 1: Prioritize Cached Streams at the Top of Stream List

**Files:**
- Modify: `stremio_http_proxy/service/stream_rewrite_service.py`
- Test: `tests/test_stream_rewrite_service.py`

**Interfaces:**
- `StreamRewriteService.rewrite(payload: dict, category: str, content_id: str | None) -> dict`:
  Stably sorts `rewritten_streams` so that any stream with `_meta["cached"] is True` appears first.

- [ ] **Step 1: Write the failing test in `tests/test_stream_rewrite_service.py`**

```python
@pytest.mark.asyncio
async def test_stream_rewrite_puts_cached_streams_at_the_top():
    cache_service = MagicMock()
    # Assume infohash "cachedhash123" is ready in cache
    cache_service.is_ready.side_effect = lambda key: key == "cachedhash123:0"
    cache_service.build_cached_play_url.return_value = "http://localhost:8691/play?link=cachedhash123"

    service = StreamRewriteService(
        torrserver_client=MagicMock(),
        cache_service=cache_service,
        public_base_url="http://localhost:8691",
        http_streams_proxy_enabled=True,
    )

    payload = {
        "streams": [
            {"name": "Stream 1", "infoHash": "otherhash456", "title": "Other Torrent"},
            {"name": "Stream 2", "infoHash": "cachedhash123", "title": "Cached Torrent"},
            {"name": "Stream 3", "url": "https://example.com/stream.mp4", "title": "HTTP Stream"},
        ]
    }

    result = await service.rewrite(payload, category="tv", content_id="tt1234567:1:1")
    streams = result["streams"]

    # Stream 2 (the cached one) must now be at index 0
    assert "🔥" in streams[0]["name"]
    assert streams[0]["_meta"]["cached"] is True
    assert streams[0]["infoHash"] == "cachedhash123"

    # Other streams retain their relative order
    assert streams[1]["infoHash"] == "otherhash456"
    assert streams[2]["url"] == "http://localhost:8691/play?link=https%3A%2F%2Fexample.com%2Fstream.mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/michele/.venv/bin/pytest tests/test_stream_rewrite_service.py -k test_stream_rewrite_puts_cached_streams_at_the_top -v`
Expected: FAIL (cached stream is at index 1 instead of index 0).

- [ ] **Step 3: Implement cached sorting in `StreamRewriteService.rewrite`**

In `stremio_http_proxy/service/stream_rewrite_service.py`:
Right before returning `updated_payload`, sort `rewritten_streams` stably with key:
```python
        # Sort cached streams to the very top, preserving relative order
        rewritten_streams.sort(
            key=lambda s: 1 if (isinstance(s.get("_meta"), dict) and s["_meta"].get("cached")) else 0,
            reverse=True,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/michele/.venv/bin/pytest tests/test_stream_rewrite_service.py -k test_stream_rewrite_puts_cached_streams_at_the_top -v`
Expected: PASS.

---

### Task 2: Parse Seeders and Filter Out Zero-Seeder Streams

**Files:**
- Modify: `stremio_http_proxy/service/stream_rewrite_service.py`
- Modify: `stremio_http_proxy/service/next_episode_prefetch_service.py`
- Test: `tests/test_stream_rewrite_service.py`
- Test: `tests/test_next_episode_prefetch_service.py`

**Interfaces:**
- `StreamRewriteService.extract_download_candidates(payload: dict) -> list[dict]`:
  Each candidate dict now includes `"seeders": int | None`.
- `NextEpisodePrefetchService._filter_and_sort_candidates(candidates: list[dict]) -> list[dict]`:
  Filters out candidates where `seeders == 0` (if `skip_zero_seeders` is True), and sorts by `seeders` descending (treating None as lower priority than positive numbers).

- [ ] **Step 1: Write failing test in `tests/test_stream_rewrite_service.py` for seeders parsing**

```python
def test_extract_download_candidates_extracts_seeders():
    service = StreamRewriteService(
        torrserver_client=MagicMock(),
        cache_service=MagicMock(),
        public_base_url="http://localhost:8691",
    )
    payload = {
        "streams": [
            {
                "name": "Stream 1",
                "description": "📄 File1.mkv\n💾 1.2 GB\n🌍 🇮🇹 | 👤 10 | ⏰",
                "infoHash": "hash1",
            },
            {
                "name": "Stream 2",
                "description": "📄 File2.mkv\n💾 500 MB\n🌍 🇮🇹 | 👤 0 | ⏰",
                "infoHash": "hash2",
            },
            {
                "name": "Stream 3",
                "description": "📄 File3.mkv\n💾 500 MB",
                "infoHash": "hash3",
            },
        ]
    }
    candidates = service.extract_download_candidates(payload)
    assert len(candidates) == 3
    assert candidates[0]["seeders"] == 10
    assert candidates[1]["seeders"] == 0
    assert candidates[2]["seeders"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/michele/.venv/bin/pytest tests/test_stream_rewrite_service.py -k test_extract_download_candidates_extracts_seeders -v`
Expected: FAIL (KeyError or `candidate["seeders"]` not present).

- [ ] **Step 3: Implement seeders extraction in `StreamRewriteService`**

In `stremio_http_proxy/service/stream_rewrite_service.py`:
Add helper `_extract_seeders(self, stream: dict) -> int | None`:
```python
    def _extract_seeders(self, stream: dict) -> int | None:
        # Check _meta first if available
        meta = stream.get("_meta")
        if isinstance(meta, dict) and meta.get("seeders") is not None:
            try:
                return int(meta["seeders"])
            except (ValueError, TypeError):
                pass
        
        # Check text description/title for 👤 icon pattern: 👤 10 or 👤10
        for field in ("description", "title"):
            val = stream.get(field)
            if isinstance(val, str):
                match = re.search(r"👤\s*(\d+)", val)
                if match:
                    return int(match.group(1))
        return None
```
And add `"seeders": self._extract_seeders(stream)` to each dict in `extract_download_candidates`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/michele/.venv/bin/pytest tests/test_stream_rewrite_service.py -k test_extract_download_candidates_extracts_seeders -v`
Expected: PASS.

---

### Task 3: Sequential Prefetch with Target Count & Cascade Fallback

**Files:**
- Modify: `stremio_http_proxy/service/next_episode_prefetch_service.py`
- Modify: `stremio_http_proxy/service/download_worker_service.py`
- Modify: `stremio_http_proxy/manager/cache_manager.py`
- Test: `tests/test_next_episode_prefetch_service.py`
- Test: `tests/test_download_worker_service.py`

**Interfaces:**
- `NextEpisodePrefetchService.__init__(..., target_completed_per_episode: int = 1, skip_zero_seeders: bool = True)`
- `NextEpisodePrefetchService.enqueue_next_episode(content_type, content_id, category)`:
  Checks `cache_manager.count_active_or_ready(content_id)`. If `< target_completed_per_episode`, picks the best candidate that has not already been attempted or queued and enqueues it.
- `NextEpisodePrefetchService.on_download_failed(content_type, content_id, category)`:
  Called by `DownloadWorkerService` when a prefetch job reaches permanent failure. Triggers `enqueue_next_episode` to try the next candidate.

- [ ] **Step 1: Write failing test in `tests/test_next_episode_prefetch_service.py` for 0-seeder filtering and 1-by-1 enqueuing**

```python
@pytest.mark.asyncio
async def test_prefetch_skips_zero_seeders_and_enqueues_single_best_candidate():
    upstream = AsyncMock()
    upstream.get_json.return_value = {
        "streams": [
            {"name": "Zero Seeds", "description": "👤 0", "infoHash": "deadhash0"},
            {"name": "Healthy", "description": "👤 15", "infoHash": "healthyhash1"},
            {"name": "Decent", "description": "👤 5", "infoHash": "decenthash2"},
        ]
    }
    queue_service = AsyncMock()
    cache_manager = MagicMock()
    cache_manager.count_completed_or_in_progress.return_value = 0
    cache_manager.is_attempted.return_value = False

    rewrite_service = StreamRewriteService(MagicMock(), MagicMock(), "http://localhost:8691")

    service = NextEpisodePrefetchService(
        upstream_client=upstream,
        stream_rewrite_service=rewrite_service,
        download_queue_service=queue_service,
        cache_manager=cache_manager,
        target_completed_per_episode=1,
        skip_zero_seeders=True,
    )

    await service.enqueue_next_episode("series", "tt3749900:1:1", "tv")

    # Must only enqueue ONE candidate (target=1)
    assert queue_service.enqueue_download.call_count == 1
    call_kwargs = queue_service.enqueue_download.call_args.kwargs
    # Must have chosen healthyhash1 (15 seeders), skipping deadhash0 (0 seeders)
    assert call_kwargs["link"] == "healthyhash1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/michele/.venv/bin/pytest tests/test_next_episode_prefetch_service.py -k test_prefetch_skips_zero_seeders_and_enqueues_single_best_candidate -v`
Expected: FAIL.

- [ ] **Step 3: Implement candidate filtering, ranking, and cascade fallback in `NextEpisodePrefetchService`**

In `NextEpisodePrefetchService`:
1. Filter candidates: if `self.skip_zero_seeders`: exclude `c["seeders"] == 0`.
2. Sort candidates: primary key: `(c["seeders"] is not None, c["seeders"] or 0)` descending.
3. Check `cache_manager.count_ready_for_content(next_content_id)`. If `>= self.target_completed_per_episode`: return early.
4. Check candidates: pick the first candidate that is not already in DB (`status in ('ready', 'downloading', 'pending', 'failed')`).
5. Enqueue it.
6. Provide method `async def on_download_failed(content_type, content_id, category)` which re-calls `enqueue_next_candidate(content_type, content_id, category)`.

- [ ] **Step 4: Wire `on_download_failed` in `DownloadWorkerService`**

In `stremio_http_proxy/service/download_worker_service.py`:
When `job.trigger == "next_episode_prefetch"` and the job is discarded/failed:
```python
if self.next_episode_prefetch_service and job.trigger == "next_episode_prefetch":
    asyncio.create_task(
        self.next_episode_prefetch_service.on_download_failed(
            job.content_type, job.content_id, job.category
        )
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/Users/michele/.venv/bin/pytest tests/test_next_episode_prefetch_service.py -v`
Expected: PASS.

---

### Task 4: Extended Initial Timeout & Elastic Progress Threshold for Prefetch

**Files:**
- Modify: `stremio_http_proxy/service/download_worker_service.py`
- Test: `tests/test_download_worker_service.py`

**Interfaces:**
- `DownloadWorkerService.__init__(..., prefetch_min_progress_bytes: int = 1048576, ...)`:
  If `job.trigger == "next_episode_prefetch"`, uses `self.prefetch_min_progress_bytes` (e.g. 1 MB per 10 minutes instead of 32 MB).
- In `_download_http_stream`: uses configurable `no_progress_timeout_seconds` (default raised to 90s).

- [ ] **Step 1: Write failing test in `tests/test_download_worker_service.py` for prefetch progress tolerance**

```python
@pytest.mark.asyncio
async def test_worker_allows_slow_progress_for_prefetch_jobs(tmp_path):
    # Test that a prefetch job downloading 2 MB in 10 minutes is NOT cancelled
    # when prefetch_min_progress_bytes is 1 MB, whereas a playback job would be cancelled.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/michele/.venv/bin/pytest tests/test_download_worker_service.py -k test_worker_allows_slow_progress_for_prefetch_jobs -v`
Expected: FAIL.

- [ ] **Step 3: Implement threshold distinction in `DownloadWorkerService`**

In `stremio_http_proxy/service/download_worker_service.py`:
In `_check_progress_window(self, job: DownloadJob, window_bytes: int)`:
```python
min_required = (
    self.prefetch_min_progress_bytes
    if job.trigger == "next_episode_prefetch"
    else self.min_progress_bytes
)
if window_bytes < min_required:
    raise RuntimeError("download progress stayed below threshold")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/michele/.venv/bin/pytest tests/test_download_worker_service.py -k test_worker_allows_slow_progress_for_prefetch_jobs -v`
Expected: PASS.

---

### Task 5: Environment Variables, Container Wiring & `.env.example`

**Files:**
- Modify: `stremio_http_proxy/container/default_container.py`
- Modify: `.env.example`
- Test: `tests/test_default_container.py`

**Interfaces:**
New environment variables read in `DefaultContainer`:
- `PREFETCH_TARGET_COMPLETED_PER_EPISODE` (int, default: 1)
- `PREFETCH_SKIP_ZERO_SEEDERS` (bool, default: True)
- `DOWNLOAD_NO_PROGRESS_TIMEOUT_SECONDS` (int, default: 90)
- `DOWNLOAD_PREFETCH_MIN_PROGRESS_BYTES` (int, default: 1048576) # 1MB
- `DOWNLOAD_MIN_PROGRESS_BYTES` (int, default: 33554432) # 32MB
- `DOWNLOAD_MIN_PROGRESS_WINDOW_SECONDS` (int, default: 600) # 10m

- [ ] **Step 1: Write test in `tests/test_default_container.py` verifying new env parameters are loaded**

```python
def test_container_loads_prefetch_and_download_env_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("PREFETCH_TARGET_COMPLETED_PER_EPISODE", "2")
    monkeypatch.setenv("PREFETCH_SKIP_ZERO_SEEDERS", "false")
    monkeypatch.setenv("DOWNLOAD_NO_PROGRESS_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("DOWNLOAD_PREFETCH_MIN_PROGRESS_BYTES", "524288")
    container = DefaultContainer(tmp_path=tmp_path)
    assert container.prefetch_target_completed == 2
    assert container.prefetch_skip_zero_seeders is False
    assert container.download_no_progress_timeout_seconds == 120
    assert container.download_prefetch_min_progress_bytes == 524288
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/michele/.venv/bin/pytest tests/test_default_container.py -k test_container_loads_prefetch_and_download_env_vars -v`
Expected: FAIL.

- [ ] **Step 3: Implement container wiring and update `.env.example`**

Update `DefaultContainer` to parse the new env variables with fallback defaults.
Inject them into `NextEpisodePrefetchService` and `DownloadWorkerService`.
Update `.env.example` with clear comments explaining each variable.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/michele/.venv/bin/pytest tests/test_default_container.py -k test_container_loads_prefetch_and_download_env_vars -v`
Expected: PASS.

---

### Task 6: Full Test Suite Verification & Production Deployment

**Files:**
- Test all: `tests/`
- Production deploy to host `home`

- [ ] **Step 1: Run complete test suite**
Run: `/Users/michele/.venv/bin/pytest -v`
Expected: 100% tests passing.

- [ ] **Step 2: Commit and push changes**
Commit message: `feat: smart prefetch with seed filtering, fallback cascade, relaxed thresholds and cached stream priority`

- [ ] **Step 3: Deploy to `home` and verify live**
Run remote update on `home`:
`ssh home "cd /home/capimichi/docker/stremio-http-proxy && git pull && docker compose up -d --build"`

- [ ] **Step 4: Live verification**
Verify that querying Gotham S01E02 streams prioritizes healthy torrents or cached streams, and that triggering prefetch skips 0-seeder streams and downloads candidate 1.
