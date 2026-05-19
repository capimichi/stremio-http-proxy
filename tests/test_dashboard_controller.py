import asyncio

from starlette.responses import FileResponse

from stremio_http_proxy.controller.dashboard_controller import DashboardController


class FakeDashboardService:
    def get_download_status(self):
        return type(
            "Payload",
            (),
            {
                "model_dump": lambda self: {
                    "manifest_url": "https://proxy.example.com/manifest.json",
                    "downloads": [
                        {
                            "cache_key": "abc:1",
                            "infohash": "abc",
                            "index": 1,
                            "status": "downloading",
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
    controller = DashboardController(FakeDashboardService())

    payload = asyncio.run(controller.downloads())

    assert payload["manifest_url"] == "https://proxy.example.com/manifest.json"
    assert payload["downloads"][0]["cache_key"] == "abc:1"
