import json
import logging
from typing import Any

from injector import inject
import redis.asyncio as aioredis

from stremio_http_proxy.logger.logger_factory import LoggerFactory


class RedisCacheManager:
    @inject
    def __init__(
        self,
        redis_url: str,
        logger_factory: LoggerFactory,
        enabled: bool = True,
        default_ttl_seconds: int = 172800,
        redis_client: aioredis.Redis | None = None,
    ):
        self.redis_url = redis_url
        self.enabled = enabled
        self.default_ttl_seconds = default_ttl_seconds
        self.logger = logger_factory.get_logger("stremio_http_proxy.redis_cache", "redis_cache.log")
        self._client = redis_client

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
        return self._client

    async def get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        try:
            client = self._get_client()
            raw = await client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            self.logger.warning("Redis get error for key %s: %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        if not self.enabled:
            return False
        try:
            client = self._get_client()
            serialized = json.dumps(value)
            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
            if ttl > 0:
                await client.set(key, serialized, ex=ttl)
            else:
                await client.set(key, serialized)
            return True
        except Exception as e:
            self.logger.warning("Redis set error for key %s: %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        if not self.enabled:
            return False
        try:
            client = self._get_client()
            await client.delete(key)
            return True
        except Exception as e:
            self.logger.warning("Redis delete error for key %s: %s", key, e)
            return False

    async def exists(self, key: str) -> bool:
        if not self.enabled:
            return False
        try:
            client = self._get_client()
            res = await client.exists(key)
            return bool(res)
        except Exception as e:
            self.logger.warning("Redis exists error for key %s: %s", key, e)
            return False

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
