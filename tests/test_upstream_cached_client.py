from unittest.mock import AsyncMock, patch
import httpx
import pytest

from stremio_http_proxy.client.upstream_cached_client import UpstreamCachedClient
from stremio_http_proxy.client.upstream_client import UpstreamClient


@pytest.mark.asyncio
async def test_upstream_cached_client_inherits_upstream_client():
    cache_manager = AsyncMock()
    client = UpstreamCachedClient(
        base_url="http://upstream.local",
        timeout_seconds=10,
        cache_manager=cache_manager,
    )
    assert isinstance(client, UpstreamClient)


@pytest.mark.asyncio
async def test_upstream_cached_client_cache_hit():
    cache_manager = AsyncMock()
    cache_manager.get.return_value = {"streams": [{"title": "Cached Stream"}]}

    client = UpstreamCachedClient(
        base_url="http://upstream.local",
        timeout_seconds=10,
        cache_manager=cache_manager,
    )

    with patch.object(UpstreamClient, "get_json") as mock_super_get:
        res = await client.get_json("/stream/movie/tt12345.json")
        assert res == {"streams": [{"title": "Cached Stream"}]}
        cache_manager.get.assert_awaited_once_with("upstream:stream/movie/tt12345.json")
        mock_super_get.assert_not_called()


@pytest.mark.asyncio
async def test_upstream_cached_client_cache_miss_and_store():
    cache_manager = AsyncMock()
    cache_manager.get.return_value = None

    client = UpstreamCachedClient(
        base_url="http://upstream.local",
        timeout_seconds=10,
        cache_manager=cache_manager,
        cache_ttl_seconds=86400,
    )

    upstream_data = {"streams": [{"title": "Live Stream"}]}

    with patch.object(UpstreamClient, "get_json", new_callable=AsyncMock) as mock_super_get:
        mock_super_get.return_value = upstream_data
        res = await client.get_json("/stream/series/tt12345:1:2.json")

        assert res == upstream_data
        mock_super_get.assert_awaited_once_with("/stream/series/tt12345:1:2.json", query_params=None)
        cache_manager.get.assert_awaited_once_with("upstream:stream/series/tt12345:1:2.json")
        cache_manager.set.assert_awaited_once_with(
            "upstream:stream/series/tt12345:1:2.json",
            upstream_data,
            ttl_seconds=86400,
        )


@pytest.mark.asyncio
async def test_upstream_cached_client_bypasses_non_stream_paths():
    cache_manager = AsyncMock()

    client = UpstreamCachedClient(
        base_url="http://upstream.local",
        timeout_seconds=10,
        cache_manager=cache_manager,
    )

    manifest_data = {"id": "org.example.addon", "name": "Test Addon"}

    with patch.object(UpstreamClient, "get_json", new_callable=AsyncMock) as mock_super_get:
        mock_super_get.return_value = manifest_data
        res = await client.get_json("/manifest.json")

        assert res == manifest_data
        cache_manager.get.assert_not_called()
        cache_manager.set.assert_not_called()
