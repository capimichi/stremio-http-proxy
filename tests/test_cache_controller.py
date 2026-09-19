import pytest
from fastapi import HTTPException
from starlette.responses import FileResponse

from stremio_http_proxy.controller.cache_controller import CacheController
from stremio_http_proxy.service.cache_token_service import CacheTokenService


class FakeCacheService:
    def __init__(self, file_path=None):
        self._file_path = file_path

    def get_cached_file_path(self, infohash: str, index: int) -> str | None:
        return self._file_path


class FakeDashboardService:
    pass


class FakeBasicAuthService:
    security = None


@pytest.mark.asyncio
async def test_cache_controller_serve_avi_file(tmp_path):
    video_file = tmp_path / "0.media"
    video_file.write_bytes(b"RIFF\x24\x00\x00\x00AVI LIST" + b"\x00" * 100)

    token_service = CacheTokenService("test-secret", 3600)
    expires = token_service.build_expires_at()
    token = token_service.build_token("hash123", 0, expires)

    controller = CacheController(
        cache_service=FakeCacheService(file_path=str(video_file)),
        cache_token_service=token_service,
        dashboard_service=FakeDashboardService(),
        basic_auth_service=FakeBasicAuthService(),
    )

    response = await controller.serve("hash123", 0, expires=expires, token=token)

    assert isinstance(response, FileResponse)
    assert response.media_type == "video/x-msvideo"
    assert response.headers["content-type"] == "video/x-msvideo"
    assert response.headers["content-disposition"] == 'inline; filename="video.avi"'


@pytest.mark.asyncio
async def test_cache_controller_serve_invalid_token(tmp_path):
    token_service = CacheTokenService("test-secret", 3600)
    controller = CacheController(
        cache_service=FakeCacheService(file_path=str(tmp_path / "0.media")),
        cache_token_service=token_service,
        dashboard_service=FakeDashboardService(),
        basic_auth_service=FakeBasicAuthService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.serve("hash123", 0, expires=12345, token="invalid_token")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cache_controller_serve_not_found():
    token_service = CacheTokenService("test-secret", 3600)
    expires = token_service.build_expires_at()
    token = token_service.build_token("hash123", 0, expires)

    controller = CacheController(
        cache_service=FakeCacheService(file_path=None),
        cache_token_service=token_service,
        dashboard_service=FakeDashboardService(),
        basic_auth_service=FakeBasicAuthService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await controller.serve("hash123", 0, expires=expires, token=token)

    assert exc_info.value.status_code == 404


def test_cache_controller_head_and_get_methods(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    video_file = tmp_path / "0.media"
    video_file.write_bytes(b"RIFF\x24\x00\x00\x00AVI LIST" + b"\x00" * 100)

    token_service = CacheTokenService("test-secret", 3600)
    expires = token_service.build_expires_at()
    token = token_service.build_token("hash123", 0, expires)

    controller = CacheController(
        cache_service=FakeCacheService(file_path=str(video_file)),
        cache_token_service=token_service,
        dashboard_service=FakeDashboardService(),
        basic_auth_service=FakeBasicAuthService(),
    )

    app = FastAPI()
    app.include_router(controller.router)
    client = TestClient(app)

    # HEAD request should succeed (200 OK) and have correct headers, no body
    head_resp = client.head(f"/cache/hash123/0?expires={expires}&token={token}")
    assert head_resp.status_code == 200
    assert head_resp.headers["content-type"] == "video/x-msvideo"
    assert "content-length" in head_resp.headers
    assert head_resp.content == b""

    # GET request should succeed (200 OK)
    get_resp = client.get(f"/cache/hash123/0?expires={expires}&token={token}")
    assert get_resp.status_code == 200
    assert len(get_resp.content) == len(b"RIFF\x24\x00\x00\x00AVI LIST" + b"\x00" * 100)

