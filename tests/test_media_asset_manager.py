import pytest
import respx
import httpx
from stremio_http_proxy.manager.media_asset_manager import MediaAssetManager


@pytest.fixture
def media_asset_manager(tmp_path):
    return MediaAssetManager(media_dir=str(tmp_path / "media"))


@pytest.mark.asyncio
async def test_media_asset_manager_download_and_cache(media_asset_manager, tmp_path):
    image_url = "https://image.tmdb.org/t/p/w500/test_poster.jpg"
    fake_content = b"FAKE_JPEG_BINARY_DATA"

    with respx.mock(base_url="https://image.tmdb.org") as respx_mock:
        respx_mock.get("/t/p/w500/test_poster.jpg").mock(
            return_value=httpx.Response(200, content=fake_content)
        )

        static_url = await media_asset_manager.save_image_from_url(
            image_url, "posters", "poster_123"
        )

        assert static_url is not None
        assert static_url.startswith("/media/images/posters/poster_123_")
        assert static_url.endswith(".jpg")

        # Second call should not hit network, returns same static URL
        cached_static_url = await media_asset_manager.save_image_from_url(
            image_url, "posters", "poster_123"
        )
        assert cached_static_url == static_url
        assert respx_mock.calls.call_count == 1


@pytest.mark.asyncio
async def test_media_asset_manager_already_local(media_asset_manager):
    local_url = "/media/images/posters/my_local_poster.jpg"
    res = await media_asset_manager.save_image_from_url(local_url, "posters", "prefix")
    assert res == local_url


@pytest.mark.asyncio
async def test_media_asset_manager_empty_url(media_asset_manager):
    assert await media_asset_manager.save_image_from_url(None, "posters", "prefix") is None
    assert await media_asset_manager.save_image_from_url("", "posters", "prefix") is None
