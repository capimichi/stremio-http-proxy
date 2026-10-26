# Download Worker Safety Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate worker deadlocks and freezing by fixing subprocess pipe buffer starvation, ensuring process group termination for child processes (yt-dlp and ffmpeg), adding bounded timeouts to all stream drains, and configuring Celery hard/soft task limits and Redis visibility timeouts.

**Architecture:**
- Refactor `DownloadMediaTask._download_hls` to use `start_new_session=True`, drain `stderr` via a bounded asynchronous line reader task, redirect `stdout` to `DEVNULL`, terminate whole process groups with `os.killpg`, and enforce timeouts on `proc.communicate()`.
- Update `stremio_http_proxy/worker.py` with Celery `task_time_limit`, `task_soft_time_limit`, and Redis `visibility_timeout` to prevent unacknowledged task redispatch.
- Provide comprehensive unit tests covering pipe drainage, process group termination, and task timeouts.

**Tech Stack:** Python 3.12, asyncio, Celery, Redis, pytest, pytest-asyncio

## Global Constraints
- Preserve documentation integrity.
- Keep every `__init__.py` file empty.
- Do not use config files or config classes; read environment variables in `default_container.py` if configurable.
- Use `injector` for dependency injection.

---

### Task 1: Add Process Group Termination and Bounded Stderr Drainage to `DownloadMediaTask`

**Files:**
- Modify: `stremio_http_proxy/task/download_media_task.py`
- Test: `tests/test_download_media_task.py`

**Interfaces:**
- Consumes: `DownloadMediaTask._download_hls(cache_key: str, url: str) -> None`
- Produces: Robust `_download_hls` and helper `_kill_process(proc)` that terminates entire process groups via `os.killpg(proc.pid, signal.SIGKILL)` and reads `stderr` concurrently without blocking the 64KB OS pipe buffer.

- [ ] **Step 1: Write unit tests for process group termination and stderr draining in `tests/test_download_media_task.py`**

```python
@pytest.mark.asyncio
async def test_download_media_task_download_hls_drains_stderr_and_uses_process_group(fake_logger_factory, tmp_path):
    torrserver_client = MagicMock()
    cache_manager = MagicMock()
    fake_target = tmp_path / "target.tmp"
    fake_target.write_bytes(b"x" * 200)
    cache_manager.prepare_download_path.return_value = fake_target
    cache_manager.get_min_cache_size.return_value = 100

    task = DownloadMediaTask(torrserver_client, cache_manager, fake_logger_factory)

    mock_proc = MagicMock()
    mock_proc.pid = 12345
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    async def fake_stream_lines():
        yield b"line 1\n"
        yield b"line 2\n"

    mock_proc.stderr = MagicMock()
    mock_proc.stderr.__aiter__ = fake_stream_lines

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
        await task._download_hls("key1:0", "https://upstream.example/live.m3u8")

        mock_exec.assert_called_once()
        _, kwargs = mock_exec.call_args
        assert kwargs.get("start_new_session") is True
        assert kwargs.get("stdout") == asyncio.subprocess.DEVNULL
        assert kwargs.get("stderr") == asyncio.subprocess.PIPE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_download_media_task.py::test_download_media_task_download_hls_drains_stderr_and_uses_process_group -v`
Expected: FAIL due to missing `start_new_session` and `stdout=DEVNULL`.

- [ ] **Step 3: Implement process group management, background stderr drainage, and timeout-bounded communicate in `DownloadMediaTask`**

Modify `_download_hls` in `stremio_http_proxy/task/download_media_task.py`:
- Use `start_new_session=True`.
- Set `stdout=asyncio.subprocess.DEVNULL`.
- Read lines from `proc.stderr` concurrently into a bounded `collections.deque(maxlen=100)`.
- Helper `_terminate_process_group(proc)` calls `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` inside `try/except (ProcessLookupError, PermissionError)`.
- Wrap `proc.communicate()` with `asyncio.wait_for(..., timeout=10.0)`.

```python
    def _terminate_process_group(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_download_media_task.py -v`
Expected: PASS for all tests.

---

### Task 2: Configure Celery Worker Time Limits and Redis Visibility Timeout via Environment Variables

**Files:**
- Modify: `stremio_http_proxy/container/default_container.py`
- Modify: `stremio_http_proxy/worker.py`
- Modify: `.env.example`
- Test: `tests/test_default_container.py`
- Test: `tests/test_celery_worker_and_beat.py`

**Interfaces:**
- Consumes: Environment variables `CELERY_TASK_TIME_LIMIT` (default 7200), `CELERY_TASK_SOFT_TIME_LIMIT` (default 7000), `CELERY_VISIBILITY_TIMEOUT` (default 14400).
- Produces: `DefaultContainer` properties (`celery_task_time_limit`, `celery_task_soft_time_limit`, `celery_visibility_timeout`), updated `.env.example`, and Celery application configuration in `stremio_http_proxy/worker.py`.

- [ ] **Step 1: Write test for DefaultContainer Celery environment variables in `tests/test_default_container.py` and worker configuration in `tests/test_celery_worker_and_beat.py`**

In `tests/test_default_container.py`:
```python
def test_default_container_loads_celery_timeout_env_vars(monkeypatch):
    DefaultContainer.instance = None
    monkeypatch.setattr("stremio_http_proxy.container.default_container.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("CELERY_TASK_TIME_LIMIT", "3600")
    monkeypatch.setenv("CELERY_TASK_SOFT_TIME_LIMIT", "3500")
    monkeypatch.setenv("CELERY_VISIBILITY_TIMEOUT", "7200")

    container = DefaultContainer()
    assert container.celery_task_time_limit == 3600
    assert container.celery_task_soft_time_limit == 3500
    assert container.celery_visibility_timeout == 7200

    DefaultContainer.instance = None
    monkeypatch.delenv("CELERY_TASK_TIME_LIMIT", raising=False)
    monkeypatch.delenv("CELERY_TASK_SOFT_TIME_LIMIT", raising=False)
    monkeypatch.delenv("CELERY_VISIBILITY_TIMEOUT", raising=False)

    default_container = DefaultContainer()
    assert default_container.celery_task_time_limit == 7200
    assert default_container.celery_task_soft_time_limit == 7000
    assert default_container.celery_visibility_timeout == 14400
```

In `tests/test_celery_worker_and_beat.py`:
```python
def test_celery_worker_safety_configuration():
    from stremio_http_proxy.worker import celery_app
    assert celery_app.conf.task_time_limit >= 7000
    assert celery_app.conf.task_soft_time_limit >= 6000
    assert celery_app.conf.broker_transport_options.get("visibility_timeout") >= 14000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_default_container.py::test_default_container_loads_celery_timeout_env_vars tests/test_celery_worker_and_beat.py::test_celery_worker_safety_configuration -v`
Expected: FAIL due to missing attributes and configuration keys.

- [ ] **Step 3: Update `default_container.py`, `worker.py`, and `.env.example`**

In `stremio_http_proxy/container/default_container.py`:
```python
        self.celery_task_time_limit = int(os.environ.get("CELERY_TASK_TIME_LIMIT", "7200"))
        self.celery_task_soft_time_limit = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "7000"))
        self.celery_visibility_timeout = int(os.environ.get("CELERY_VISIBILITY_TIMEOUT", "14400"))
```

In `stremio_http_proxy/worker.py`:
```python
task_time_limit = int(os.environ.get("CELERY_TASK_TIME_LIMIT", "7200"))
task_soft_time_limit = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "7000"))
visibility_timeout = int(os.environ.get("CELERY_VISIBILITY_TIMEOUT", "14400"))

celery_app.conf.update(
    ...
    task_time_limit=task_time_limit,
    task_soft_time_limit=task_soft_time_limit,
    broker_transport_options={
        "visibility_timeout": visibility_timeout,
    },
)
```

In `.env.example`:
```ini
# Celery worker timeouts (seconds)
CELERY_TASK_TIME_LIMIT=7200
CELERY_TASK_SOFT_TIME_LIMIT=7000
CELERY_VISIBILITY_TIMEOUT=14400
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_default_container.py tests/test_celery_worker_and_beat.py -v`
Expected: PASS.

---

### Task 3: Full Test Suite Verification, Git Commit, and Deployment

**Files:**
- Full repository test suite

- [ ] **Step 1: Run full pytest suite**

Run: `pytest -v`
Expected: 189 passed.

- [ ] **Step 2: Commit changes to Git**

Command:
```bash
git add stremio_http_proxy/task/download_media_task.py stremio_http_proxy/worker.py tests/
git commit -m "fix: resolve worker deadlocks with pipe drainage, process group kill, and celery timeouts"
git push origin master
```

- [ ] **Step 3: Deploy to Home Server via Ansible and verify container restart**

Command:
```bash
cd /Users/michele/PycharmProjects/capimichi-home
ansible-playbook playbooks/services/stremio_http_proxy.yml --vault-password-file /Users/michele/.vault_pass
```

- [ ] **Step 4: Verify Celery worker recovery on server**

Verify on `192.168.1.100`:
- Confirm `stremio-http-proxy-worker` container restarted cleanly.
- Inspect active Celery tasks (`celery -A stremio_http_proxy.worker.celery_app inspect active`) to confirm both slots are unblocked and processing the pending queue.
