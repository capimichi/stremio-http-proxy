# Optimize Media Target Enum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `OptimizeMediaTargetEnum` to replace raw string comparisons for media optimization targets, parse it cleanly via a classmethod in `default_container.py`, update consumer tasks/services, and document the architectural rule in `AGENTS.md`.

**Architecture:** Create `OptimizeMediaTargetEnum(StrEnum)` in `stremio_http_proxy/enum/` with `@classmethod from_str(...)`. Parse environment variables in `default_container.py` in a single line, and type constructor parameters and condition checks in `OptimizeMediaTask` and `StreamRewriteService` with the new enum. Update `AGENTS.md` with guidelines on enums.

**Tech Stack:** Python 3.11+ (`enum.StrEnum`), Pytest, Injector.

## Global Constraints

- Do not use config files or config classes.
- Keep every `__init__.py` file empty.
- Enum classes must live in `stremio_http_proxy/enum/` and inherit from standard `enum.StrEnum` (or `enum.Enum`).
- No raw/hardcoded strings for domain states, modes, targets, or configurable options.
- Parse env vars for enum-backed settings in `default_container.py` using `@classmethod from_str(...)` on the enum.

---

### Task 1: Create `OptimizeMediaTargetEnum` and Unit Tests

**Files:**
- Create: `stremio_http_proxy/enum/optimize_media_target_enum.py`
- Test: `tests/test_optimize_media_target_enum.py`

**Interfaces:**
- Produces: `OptimizeMediaTargetEnum(StrEnum)` with:
  - `COMPATIBLE = "compatible"`
  - `WEB_READY_MP4 = "web_ready_mp4"`
  - `NONE = "none"`
  - `@classmethod from_str(cls, value: str | None) -> OptimizeMediaTargetEnum`

- [x] **Step 1: Write the failing test**

Create `tests/test_optimize_media_target_enum.py`:
```python
from stremio_http_proxy.enum.optimize_media_target_enum import OptimizeMediaTargetEnum


def test_optimize_media_target_enum_values():
    assert OptimizeMediaTargetEnum.COMPATIBLE == "compatible"
    assert OptimizeMediaTargetEnum.WEB_READY_MP4 == "web_ready_mp4"
    assert OptimizeMediaTargetEnum.NONE == "none"


def test_optimize_media_target_enum_from_str():
    assert OptimizeMediaTargetEnum.from_str(None) == OptimizeMediaTargetEnum.COMPATIBLE
    assert OptimizeMediaTargetEnum.from_str("") == OptimizeMediaTargetEnum.COMPATIBLE
    assert OptimizeMediaTargetEnum.from_str("compatible") == OptimizeMediaTargetEnum.COMPATIBLE
    assert OptimizeMediaTargetEnum.from_str("COMPATIBLE") == OptimizeMediaTargetEnum.COMPATIBLE
    assert OptimizeMediaTargetEnum.from_str("web_ready_mp4") == OptimizeMediaTargetEnum.WEB_READY_MP4
    assert OptimizeMediaTargetEnum.from_str("web_ready") == OptimizeMediaTargetEnum.WEB_READY_MP4
    assert OptimizeMediaTargetEnum.from_str("none") == OptimizeMediaTargetEnum.NONE
    assert OptimizeMediaTargetEnum.from_str("disabled") == OptimizeMediaTargetEnum.NONE
    assert OptimizeMediaTargetEnum.from_str("false") == OptimizeMediaTargetEnum.NONE
    assert OptimizeMediaTargetEnum.from_str("unknown_val") == OptimizeMediaTargetEnum.COMPATIBLE
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_optimize_media_target_enum.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'stremio_http_proxy.enum.optimize_media_target_enum')

- [x] **Step 3: Write implementation**

Create `stremio_http_proxy/enum/optimize_media_target_enum.py`:
```python
from enum import StrEnum


class OptimizeMediaTargetEnum(StrEnum):
    COMPATIBLE = "compatible"
    WEB_READY_MP4 = "web_ready_mp4"
    NONE = "none"

    @classmethod
    def from_str(cls, value: str | None) -> "OptimizeMediaTargetEnum":
        if not value:
            return cls.COMPATIBLE
        val = value.strip().lower()
        if val in ("none", "disabled", "false"):
            return cls.NONE
        if val in ("web_ready", "web_ready_mp4"):
            return cls.WEB_READY_MP4
        try:
            return cls(val)
        except ValueError:
            return cls.COMPATIBLE
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_optimize_media_target_enum.py -v`
Expected: PASS

---

### Task 2: Integrate `OptimizeMediaTargetEnum` in `default_container.py`

**Files:**
- Modify: `stremio_http_proxy/container/default_container.py:117`
- Test: `tests/test_default_container.py:141-148`

**Interfaces:**
- Consumes: `OptimizeMediaTargetEnum`
- Produces: `self.optimize_media_target: OptimizeMediaTargetEnum` on `DefaultContainer`

- [x] **Step 1: Write/update container tests**

In `tests/test_default_container.py`, replace `test_default_container_defaults_optimize_media_target_to_compatible`:
```python
from stremio_http_proxy.enum.optimize_media_target_enum import OptimizeMediaTargetEnum


def test_default_container_defaults_optimize_media_target_to_compatible(monkeypatch):
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.delenv("OPTIMIZE_MEDIA_TARGET", raising=False)
    container = DefaultContainer()
    assert container.optimize_media_target == OptimizeMediaTargetEnum.COMPATIBLE


def test_default_container_parses_optimize_media_target_variations(monkeypatch):
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("OPTIMIZE_MEDIA_TARGET", "web_ready")
    container = DefaultContainer()
    assert container.optimize_media_target == OptimizeMediaTargetEnum.WEB_READY_MP4

    monkeypatch.setenv("OPTIMIZE_MEDIA_TARGET", "disabled")
    container2 = DefaultContainer()
    assert container2.optimize_media_target == OptimizeMediaTargetEnum.NONE
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_default_container.py -k "optimize_media_target" -v`
Expected: FAIL (assertion string != enum or container.optimize_media_target is str)

- [x] **Step 3: Update `default_container.py`**

In `stremio_http_proxy/container/default_container.py`:
Add import:
```python
from stremio_http_proxy.enum.optimize_media_target_enum import OptimizeMediaTargetEnum
```
Update line 117:
```python
        self.optimize_media_target = OptimizeMediaTargetEnum.from_str(os.environ.get("OPTIMIZE_MEDIA_TARGET"))
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_default_container.py -k "optimize_media_target" -v`
Expected: PASS

---

### Task 3: Update `OptimizeMediaTask` & `StreamRewriteService`

**Files:**
- Modify: `stremio_http_proxy/task/optimize_media_task.py:28,36,74,79`
- Modify: `stremio_http_proxy/service/stream_rewrite_service.py:26,34,200,204`
- Test: `tests/test_optimize_media_task.py`
- Test: `tests/test_stream_rewrite_service.py`

**Interfaces:**
- Consumes: `OptimizeMediaTargetEnum`
- Produces: Strongly typed constructors and comparisons

- [x] **Step 1: Update `OptimizeMediaTask`**

In `stremio_http_proxy/task/optimize_media_task.py`:
Add import:
```python
from stremio_http_proxy.enum.optimize_media_target_enum import OptimizeMediaTargetEnum
```
Update constructor parameter:
```python
        optimize_media_target: OptimizeMediaTargetEnum = OptimizeMediaTargetEnum.COMPATIBLE,
```
Update target checks in `optimize(...)`:
```python
        if not self.optimize_media_enabled or self.optimize_media_target == OptimizeMediaTargetEnum.NONE:
            self.logger.info("Optimization is disabled via config, marking %s ready (%s bytes)", cache_key, orig_size)
            self.cache_manager.mark_ready(cache_key, orig_size)
            return True

        if self.optimize_media_target == OptimizeMediaTargetEnum.COMPATIBLE:
            return await self._run_compatible_optimization(cache_key, media_path, orig_size)

        return await self._run_web_ready_optimization(cache_key, media_path, orig_size)
```

- [x] **Step 2: Update `StreamRewriteService`**

In `stremio_http_proxy/service/stream_rewrite_service.py`:
Add import:
```python
from stremio_http_proxy.enum.optimize_media_target_enum import OptimizeMediaTargetEnum
```
Update constructor parameter:
```python
        optimize_media_target: OptimizeMediaTargetEnum = OptimizeMediaTargetEnum.COMPATIBLE,
```
Update `_is_web_ready`:
```python
    def _is_web_ready(self, infohash: str | None, index: int | None) -> bool:
        if self.optimize_media_target == OptimizeMediaTargetEnum.WEB_READY_MP4:
            return True
        if not infohash:
            return False
        if self.optimize_media_target == OptimizeMediaTargetEnum.COMPATIBLE:
            if self.cache_manager and hasattr(self.cache_manager, "is_ready"):
                cache_key = f"{infohash}:{index if index is not None else 0}"
                if self.cache_manager.is_ready(cache_key):
                    return True
            if hasattr(self.cache_manager, "_media_path"):
                try:
                    media_path = self.cache_manager._media_path(infohash, index or 0)
                    if media_path and media_path.exists():
                        return True
                except Exception:
                    pass
        return False
```

- [x] **Step 3: Update tests in `test_optimize_media_task.py` and `test_stream_rewrite_service.py`**

Import `OptimizeMediaTargetEnum` in both test files and update calls passing `optimize_media_target` string literals (`"compatible"` -> `OptimizeMediaTargetEnum.COMPATIBLE`, `"web_ready_mp4"` -> `OptimizeMediaTargetEnum.WEB_READY_MP4`).

- [x] **Step 4: Run unit tests for task and rewrite service**

Run: `pytest tests/test_optimize_media_task.py tests/test_stream_rewrite_service.py -v`
Expected: PASS

---

### Task 4: Update `AGENTS.md` and Run Full Regression

**Files:**
- Modify: `AGENTS.md`

- [x] **Step 1: Update `AGENTS.md`**

In `AGENTS.md`, replace:
```markdown
- Enum classes must live in `stremio_http_proxy/enum/`.
```
with:
```markdown
- Enum classes must live in `stremio_http_proxy/enum/` and inherit from standard `enum.StrEnum` (or `enum.Enum`).
- Never use raw/hardcoded strings for domain states, modes, targets, or configurable options. Define corresponding enums and type constructor parameters with the enum class.
- When parsing environment variables for enum-backed settings in `default_container.py`, implement a `@classmethod from_str(...)` on the enum to handle sanitization, aliases, and fallbacks cleanly in a single line.
```

- [x] **Step 2: Run full regression test suite**

Run: `pytest`
Expected: 185+ passed, 0 failed.
