import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import FileResponse

from stremio_http_proxy.controller.cache_controller import CacheController
from stremio_http_proxy.controller.dashboard_controller import DashboardController
from stremio_http_proxy.service.basic_auth_service import BasicAuthService


class FakeDashboardService:
    def __init__(self):
        self.calls = []

    def get_download_status(self, page=1, limit=10):
        self.calls.append((page, limit))
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


def test_dashboard_controller_serves_static_index():
    controller = DashboardController(FakeDashboardService(), BasicAuthService())

    response = asyncio.run(controller.index())

    assert isinstance(response, FileResponse)
    assert response.path.endswith("static/index.html")


def test_dashboard_controller_returns_download_payload():
    service = FakeDashboardService()
    controller = DashboardController(service, BasicAuthService())

    payload = asyncio.run(controller.downloads(page=2, limit=10))

    assert service.calls == [(2, 10)]
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
    app.include_router(DashboardController(FakeDashboardService(), auth_service).router)
    app.include_router(CacheController(FakeCacheService(), auth_service).router)
    client = TestClient(app)

    dashboard_response = client.get("/")
    downloads_response = client.get("/downloads")
    cache_response = client.get("/cache/abc/1")

    assert dashboard_response.status_code == 401
    assert dashboard_response.headers["www-authenticate"] == "Basic"
    assert downloads_response.status_code == 401
    assert cache_response.status_code == 401


def test_dashboard_routes_accept_valid_auth():
    app = FastAPI()
    auth_service = BasicAuthService("admin", "secret")
    app.include_router(DashboardController(FakeDashboardService(), auth_service).router)
    app.include_router(CacheController(FakeCacheService(), auth_service).router)
    client = TestClient(app)

    dashboard_response = client.get("/", auth=("admin", "secret"))
    downloads_response = client.get("/downloads", auth=("admin", "secret"))
    cache_response = client.get("/cache/abc/1", auth=("admin", "secret"))

    assert dashboard_response.status_code == 200
    assert downloads_response.status_code == 200
    assert downloads_response.json()["active_downloads"] == 1
    assert cache_response.status_code == 200
