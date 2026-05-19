# Repository Guidelines

## Architecture Rules
- Do not use config files or config classes. Read environment variables in `stremio_http_proxy/container/default_container.py` and pass those values directly into constructors.
- Keep every `__init__.py` file empty.
- Use `injector` for dependency injection. In `default_container`, bind only classes that require manual constructor values; let `injector` resolve the rest automatically.
- Do not use `dataclass`. Use Pydantic models and keep model classes inside the `stremio_http_proxy/model/` layer.
- Manager classes must live in `stremio_http_proxy/manager/`. Service classes must live in `stremio_http_proxy/service/`. Do not place managers in the service layer.
- Controllers must communicate with services, not managers.
