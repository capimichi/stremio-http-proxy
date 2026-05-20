import asyncio

from starlette.responses import FileResponse

from stremio_http_proxy.controller.dashboard_controller import DashboardController


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


def test_dashboard_controller_serves_static_index():
    controller = DashboardController(FakeDashboardService())

    response = asyncio.run(controller.index())

    assert isinstance(response, FileResponse)
    assert response.path.endswith("static/index.html")


def test_dashboard_controller_returns_download_payload():
    service = FakeDashboardService()
    controller = DashboardController(service)

    payload = asyncio.run(controller.downloads(page=2, limit=10))

    assert service.calls == [(2, 10)]
    assert payload["manifest_url"] == "https://proxy.example.com/manifest.json"
    assert payload["page"] == 2
    assert payload["limit"] == 10
    assert payload["total_cache_bytes"] == 10
    assert payload["downloads"][0]["title"] == "Demo Episode"
    assert payload["downloads"][0]["cache_key"] == "abc:1"
