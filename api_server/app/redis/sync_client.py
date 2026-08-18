"""Redis同步客户端模块，提供同步Redis客户端单例，适用于普通业务。"""

import redis

from app.core.config import settings


class SyncRedisClient:
    """Redis同步客户端封装（单例模式）。"""

    _client: redis.Redis | None = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        """获取同步Redis客户端单例。

        Returns:
            同步Redis客户端实例。
        """
        if cls._client is None:
            cls._client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        return cls._client


def get_redis() -> redis.Redis:
    """获取同步Redis客户端（依赖注入用）。

    Returns:
        同步Redis客户端实例。
    """
    return SyncRedisClient.get_client()
