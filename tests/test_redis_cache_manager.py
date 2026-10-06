from unittest.mock import AsyncMock, MagicMock
import pytest

from stremio_http_proxy.manager.redis_cache_manager import RedisCacheManager


@pytest.fixture
def logger_factory():
    factory = MagicMock()
    logger = MagicMock()
    factory.get_logger.return_value = logger
    return factory


@pytest.mark.asyncio
async def test_redis_cache_manager_get_and_set(logger_factory):
    mock_redis = AsyncMock()
    mock_redis.get.return_value = '{"title": "Matrix", "streams": [1, 2]}'

    manager = RedisCacheManager(
        redis_url="redis://localhost:6379/0",
        logger_factory=logger_factory,
        enabled=True,
        default_ttl_seconds=3600,
        redis_client=mock_redis,
    )

    result = await manager.get("upstream:test")
    assert result == {"title": "Matrix", "streams": [1, 2]}
    mock_redis.get.assert_awaited_once_with("upstream:test")

    success = await manager.set("upstream:test", {"title": "Matrix"}, ttl_seconds=1800)
    assert success is True
    mock_redis.set.assert_awaited_once_with("upstream:test", '{"title": "Matrix"}', ex=1800)


@pytest.mark.asyncio
async def test_redis_cache_manager_disabled(logger_factory):
    mock_redis = AsyncMock()
    manager = RedisCacheManager(
        redis_url="redis://localhost:6379/0",
        logger_factory=logger_factory,
        enabled=False,
        redis_client=mock_redis,
    )

    assert await manager.get("key") is None
    assert await manager.set("key", "val") is False
    assert await manager.delete("key") is False
    assert await manager.exists("key") is False
    mock_redis.get.assert_not_called()
    mock_redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_redis_cache_manager_resilience_on_exception(logger_factory):
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = ConnectionError("Redis down")
    mock_redis.set.side_effect = ConnectionError("Redis down")
    mock_redis.delete.side_effect = ConnectionError("Redis down")
    mock_redis.exists.side_effect = ConnectionError("Redis down")

    manager = RedisCacheManager(
        redis_url="redis://localhost:6379/0",
        logger_factory=logger_factory,
        enabled=True,
        redis_client=mock_redis,
    )

    # Must return gracefully without raising exceptions
    assert await manager.get("key") is None
    assert await manager.set("key", "val") is False
    assert await manager.delete("key") is False
    assert await manager.exists("key") is False


@pytest.mark.asyncio
async def test_redis_cache_manager_delete_and_exists(logger_factory):
    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 1
    mock_redis.delete.return_value = 1

    manager = RedisCacheManager(
        redis_url="redis://localhost:6379/0",
        logger_factory=logger_factory,
        enabled=True,
        redis_client=mock_redis,
    )

    assert await manager.exists("key") is True
    assert await manager.delete("key") is True
    mock_redis.exists.assert_awaited_once_with("key")
    mock_redis.delete.assert_awaited_once_with("key")
