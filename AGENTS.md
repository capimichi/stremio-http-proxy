# Repository Guidelines

## Architecture Rules
- Do not use config files or config classes. Read environment variables in `stremio_http_proxy/container/default_container.py` and pass those values directly into constructors.
- Keep every `__init__.py` file empty.
- Use `injector` for dependency injection. In `default_container`, bind only classes that require manual constructor values; let `injector` resolve the rest automatically.
- Do not use `dataclass`. Use Pydantic models and keep model classes inside the `stremio_http_proxy/model/` layer.
- Persistent entities must live in `stremio_http_proxy/entity/`.
- Entity classes must use domain names only, never names prefixed or suffixed with `Entity`.
- Enum classes must live in `stremio_http_proxy/enum/` and inherit from standard `enum.StrEnum` (or `enum.Enum`).
- Never use raw/hardcoded strings for domain states, modes, targets, or configurable options. Define corresponding enums and type constructor parameters with the enum class.
- When parsing environment variables for enum-backed settings in `default_container.py`, implement a `@classmethod from_str(...)` on the enum to handle sanitization, aliases, and fallbacks cleanly in a single line.
- Manager classes must live in `stremio_http_proxy/manager/`. Service classes must live in `stremio_http_proxy/service/`. Do not place managers in the service layer.
- Controllers must communicate with services, not managers.
