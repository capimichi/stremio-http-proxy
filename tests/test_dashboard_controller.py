import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from starlette.responses import FileResponse

from stremio_http_proxy.controller.cache_controller import CacheController
from stremio_http_proxy.controller.dashboard_controller import DashboardController
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.cache_token_service import CacheTokenService


class FakeJinjaManager:
    def render(self, template_name: str, **context: object) -> str:
        self.last_template = template_name
        self.last_context = context
        return f"<html>{template_name}</html>"


class FakeDashboardService:
    def __init__(self):
        self.calls = []
        self.context_to_return = {}
        self.context_entry_to_return = ({"entry": None, "play_url": None, "infohash": "abc", "index": 1, "created_at_str": "N/A", "completed_at_str": "N/A"}, 200)

    def get_index_context(self) -> dict:
        self.calls.append("get_index_context")
        return self.context_to_return

    def get_cache_items_context(self) -> dict:
        self.calls.append("get_cache_items_context")
        return self.context_to_return

    def get_cache_entry_context(self, infohash: str, index: int) -> tuple[dict | None, int]:
        self.calls.append(("get_cache_entry_context", infohash, index))
        return self.context_entry_to_return

    def get_download_status(self, page=1, limit=10, search=None):
        self.calls.append((page, limit, search))
        return type(
            "Payload",
            (),
            {
                "model_dump": lambda self: {
                    "manifest_url": "https://proxy.example.com/manifest.json",
                "page": page,
                "limit": limit,
                "total_items": 1,
                "total_pages": 1,
                "total_cache_bytes": 10,
                "status_counts": {"downloading": 1},
                "active_downloads": 1,
                "downloads": [
                        {
                            "cache_key": "abc:1",
                            "title": "Demo Episode",
                            "infohash": "abc",
                            "index": 1,
                            "status": "downloading",
                            "created_at": 100.0,
                            "completed_at": None,
                            "downloaded_bytes": 10,
                            "expected_bytes": 20,
                            "progress_percent": 50.0,
                            "download_speed_bytes_per_second": 5.0,
                            "attempt": 1,
                            "last_error": None,
                            "last_progress_at": 123.0,
                        }
                    ],
                }
            },
        )()


class FakeCacheService:
    def get_cached_file_path(self, infohash: str, index: int) -> str | None:
        return __file__


def test_dashboard_index_renders_html():
    service = FakeDashboardService()
    jinja = FakeJinjaManager()
    controller = DashboardController(service, BasicAuthService(), jinja)

    response = asyncio.run(controller.dashboard_index())

    assert isinstance(response, HTMLResponse)
    assert "dashboard/pages/index.html" in response.body.decode()
    assert jinja.last_template == "dashboard/pages/index.html"


def test_cache_items_renders_html():
    service = FakeDashboardService()
    jinja = FakeJinjaManager()
    controller = DashboardController(service, BasicAuthService(), jinja)

    response = asyncio.run(controller.cache_items())

    assert isinstance(response, HTMLResponse)
    assert "dashboard/pages/cache_items.html" in response.body.decode()
    assert jinja.last_template == "dashboard/pages/cache_items.html"


def test_cache_entry_renders_html():
    service = FakeDashboardService()
    jinja = FakeJinjaManager()
    controller = DashboardController(service, BasicAuthService(), jinja)

    response = asyncio.run(controller.cache_entry("abc", 1))

    assert isinstance(response, HTMLResponse)
    assert "dashboard/pages/cache_entry.html" in response.body.decode()
    assert jinja.last_template == "dashboard/pages/cache_entry.html"


def test_cache_entry_returns_404_when_missing():
    service = FakeDashboardService()
    service.context_entry_to_return = (None, 404)
    jinja = FakeJinjaManager()
    controller = DashboardController(service, BasicAuthService(), jinja)

    response = asyncio.run(controller.cache_entry("abc", 1))

    assert response.status_code == 404


def test_dashboard_controller_returns_download_payload():
    service = FakeDashboardService()
    controller = CacheController(
        FakeCacheService(),
        CacheTokenService("secret", 259200),
        service,
        BasicAuthService(),
    )

    payload = asyncio.run(controller.downloads(page=2, limit=10))

    assert service.calls[0][:2] == (2, 10)
    assert payload["manifest_url"] == "https://proxy.example.com/manifest.json"
    assert payload["page"] == 2
    assert payload["limit"] == 10
    assert payload["total_cache_bytes"] == 10
    assert payload["status_counts"] == {"downloading": 1}
    assert payload["active_downloads"] == 1
    assert payload["downloads"][0]["title"] == "Demo Episode"
    assert payload["downloads"][0]["cache_key"] == "abc:1"


def test_dashboard_routes_require_auth_when_enabled():
    app = FastAPI()
    auth_service = BasicAuthService("admin", "secret")
    jinja = FakeJinjaManager()
    app.include_router(DashboardController(FakeDashboardService(), auth_service, jinja).router)
    fake_dashboard_service = FakeDashboardService()
    app.include_router(CacheController(FakeCacheService(), CacheTokenService("secret", 259200), fake_dashboard_service, auth_service).router)
    client = TestClient(app)

    dashboard_response = client.get("/")
    downloads_response = client.get("/downloads")
    token_service = CacheTokenService("secret", 259200)
    expires = token_service.build_expires_at()
    token = token_service.build_token("abc", 1, expires)
    cache_response = client.get(f"/cache/abc/1?expires={expires}&token={token}")

    assert dashboard_response.status_code == 401
    assert dashboard_response.headers["www-authenticate"] == "Basic"
    assert downloads_response.status_code == 401
    assert cache_response.status_code == 200


def test_dashboard_routes_accept_valid_auth():
    app = FastAPI()
    auth_service = BasicAuthService("admin", "secret")
    jinja = FakeJinjaManager()
    app.include_router(DashboardController(FakeDashboardService(), auth_service, jinja).router)
    fake_dashboard_service = FakeDashboardService()
    app.include_router(CacheController(FakeCacheService(), CacheTokenService("secret", 259200), fake_dashboard_service, auth_service).router)
    client = TestClient(app)
    token_service = CacheTokenService("secret", 259200)
    expires = token_service.build_expires_at()
    token = token_service.build_token("abc", 1, expires)

    dashboard_response = client.get("/", auth=("admin", "secret"))
    downloads_response = client.get("/downloads", auth=("admin", "secret"))
    cache_response = client.get(f"/cache/abc/1?expires={expires}&token={token}")

    assert dashboard_response.status_code == 200
    assert downloads_response.status_code == 200
    assert downloads_response.json()["active_downloads"] == 1
    assert cache_response.status_code == 200


def test_cache_route_rejects_invalid_token():
    app = FastAPI()
    app.include_router(CacheController(FakeCacheService(), CacheTokenService("secret", 259200), FakeDashboardService(), BasicAuthService()).router)
    client = TestClient(app)

    response = client.get("/cache/abc/1?expires=1700000000&token=wrong")

    assert response.status_code == 403
