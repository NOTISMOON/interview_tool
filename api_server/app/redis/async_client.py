"""Redis异步客户端模块，提供异步Redis客户端单例，适用于Agent业务。"""

import redis.asyncio as aioredis

from app.core.config import settings


class AsyncRedisClient:
    """Redis异步客户端封装（单例模式）。"""

    _client: aioredis.Redis | None = None

    @classmethod
    async def get_client(cls) -> aioredis.Redis:
        """获取异步Redis客户端单例。

        Returns:
            异步Redis客户端实例。
        """
        if cls._client is None:
            cls._client = aioredis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        return cls._client


async def get_async_redis() -> aioredis.Redis:
    """获取异步Redis客户端（依赖注入用）。

    Returns:
        异步Redis客户端实例。
    """
    return await AsyncRedisClient.get_client()