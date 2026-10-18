# Design Spec: Media Optimization Target Enum and Enum Layer Guidelines

## Context & Motivation
Media optimization modes (`"compatible"`, `"web_ready_mp4"`, `"none"`) and related checks have historically been scattered as raw string literals across `default_container.py`, `optimize_media_task.py`, and `stream_rewrite_service.py`.

Using raw strings introduces risks of typos, complicates refactoring, and leads to duplicated parsing/normalization logic. To establish a consistent standard across the codebase, this spec defines:
1. `OptimizeMediaTargetEnum` in `stremio_http_proxy/enum/`.
2. A single-line parsing pattern via `@classmethod from_str` to keep `default_container.py` concise and maintainable.
3. Updated consumers and unit tests using typed enum values.
4. Repository rules in `AGENTS.md` enforcing typed enums for domain states, modes, and targets.

---

## 1. Enum Definition
File: `stremio_http_proxy/enum/optimize_media_target_enum.py`

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

### Key Properties:
- Inherits from standard library `StrEnum` (Python 3.11+).
- Canonizes target values: `COMPATIBLE` (default fast remux EBML cues), `WEB_READY_MP4` (legacy web-ready MP4 transcode), `NONE` (optimization disabled).
- Normalizes env inputs (`"disabled"`, `"false"` -> `NONE`; `"web_ready"` -> `WEB_READY_MP4`; invalid strings fall back to `COMPATIBLE`).

---

## 2. Container Integration
File: `stremio_http_proxy/container/default_container.py`

Replace the string assignment:
```python
# Before
self.optimize_media_target = os.environ.get("OPTIMIZE_MEDIA_TARGET", "compatible").lower()

# After
self.optimize_media_target = OptimizeMediaTargetEnum.from_str(os.environ.get("OPTIMIZE_MEDIA_TARGET"))
```

`self.optimize_media_target` is typed as `OptimizeMediaTargetEnum` and passed to `OptimizeMediaTask` and `StreamRewriteService`.

---

## 3. Consumer Updates

### 3.1 `OptimizeMediaTask`
File: `stremio_http_proxy/task/optimize_media_task.py`

- Constructor parameter:
  ```python
  optimize_media_target: OptimizeMediaTargetEnum = OptimizeMediaTargetEnum.COMPATIBLE,
  ```
- Target checks:
  ```python
  if not self.optimize_media_enabled or self.optimize_media_target == OptimizeMediaTargetEnum.NONE:
      self.logger.info("Optimization is disabled via config, marking %s ready (%s bytes)", cache_key, orig_size)
      self.cache_manager.mark_ready(cache_key, orig_size)
      return True

  if self.optimize_media_target == OptimizeMediaTargetEnum.COMPATIBLE:
      return await self._run_compatible_optimization(cache_key, media_path, orig_size)

  return await self._run_web_ready_optimization(cache_key, media_path, orig_size)
  ```

### 3.2 `StreamRewriteService`
File: `stremio_http_proxy/service/stream_rewrite_service.py`

- Constructor parameter:
  ```python
  optimize_media_target: OptimizeMediaTargetEnum = OptimizeMediaTargetEnum.COMPATIBLE,
  ```
- Target checks in `_is_web_ready`:
  ```python
  if self.optimize_media_target == OptimizeMediaTargetEnum.WEB_READY_MP4:
      return True
  if not infohash:
      return False
  if self.optimize_media_target == OptimizeMediaTargetEnum.COMPATIBLE:
      if self.cache_manager and hasattr(self.cache_manager, "is_ready"):
          cache_key = f"{infohash}:{index if index is not None else 0}"
          if self.cache_manager.is_ready(cache_key):
              return True
  ```

---

## 4. AGENTS.md Architectural Guidelines
File: `AGENTS.md`

Add the following guidelines under `## Architecture Rules`:
- Enum classes must live in `stremio_http_proxy/enum/` and inherit from standard `enum.StrEnum` (or `enum.Enum`).
- Never use raw/hardcoded strings for domain states, modes, targets, or configurable options. Define corresponding enums and type constructor parameters with the enum class.
- When parsing environment variables for enum-backed settings in `default_container.py`, implement a `@classmethod from_str(...)` on the enum to handle sanitization, aliases, and fallbacks cleanly in a single line.

---

## 5. Testing Strategy
1. **Container Tests (`test_default_container.py`)**:
   - Verify default environment parses to `OptimizeMediaTargetEnum.COMPATIBLE`.
   - Verify `OPTIMIZE_MEDIA_TARGET=web_ready_mp4` and `web_ready` parse to `OptimizeMediaTargetEnum.WEB_READY_MP4`.
   - Verify `none`, `disabled`, and `false` parse to `OptimizeMediaTargetEnum.NONE`.
   - Verify unknown values fall back safely to `OptimizeMediaTargetEnum.COMPATIBLE`.
2. **Task Tests (`test_optimize_media_task.py`)**:
   - Update tests passing `optimize_media_target` to use `OptimizeMediaTargetEnum`.
   - Verify disabled behavior when target is `NONE`.
3. **Rewrite Service Tests (`test_stream_rewrite_service.py`)**:
   - Update tests passing `optimize_media_target` to use `OptimizeMediaTargetEnum`.
4. **Full Regression**:
   - Run complete test suite (`pytest`) to ensure 100% pass rate.
