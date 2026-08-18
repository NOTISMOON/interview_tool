"""RabbitMQ 异步连接管理模块。

提供基于 aio-pika 的 RobustConnection 单例与依赖注入函数。
RobustConnection 会在网络中断时自动重连，适合长期运行的生产者与消费者。

参考：app/redis/async_client.py 的单例 + 依赖注入风格。
"""

import logging
from typing import Optional

import aio_pika

from app.core.config import settings

logger = logging.getLogger(__name__)


class MQConnection:
    """RabbitMQ 异步连接管理器（单例模式）。

    封装 aio-pika.RobustConnection，提供全局复用的连接与默认通道。
    连接与通道均由 aio-pika 自动管理重连与恢复，无需手动重试。
    """

    _connection: Optional[aio_pika.RobustConnection] = None
    _channel: Optional[aio_pika.RobustChannel] = None

    @classmethod
    async def get_connection(cls) -> aio_pika.RobustConnection:
        """获取 RabbitMQ 异步连接单例。

        首次调用时建立连接，后续复用。连接断开会自动重连。

        Returns:
            aio_pika.RobustConnection 实例。

        Raises:
            Exception: 连接建立失败时抛出。
        """
        if cls._connection is None or cls._connection.is_closed:
            logger.info("建立 RabbitMQ 异步连接: %s", _mask_url(settings.RABBITMQ_URL))
            cls._connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            logger.info("RabbitMQ 连接已建立")

        return cls._connection

    @classmethod
    async def get_channel(cls) -> aio_pika.RobustChannel:
        """获取默认异步通道单例。

        通道预取数量由 settings.RABBITMQ_PREFETCH_COUNT 控制，
        用于消费者背压。生产者复用同一通道即可。

        Returns:
            aio_pika.RobustChannel 实例。

        Raises:
            Exception: 获取连接或通道失败时抛出。
        """
        if cls._channel is None or cls._channel.is_closed:
            connection = await cls.get_connection()
            cls._channel = await connection.channel()
            await cls._channel.set_qos(prefetch_count=settings.RABBITMQ_PREFETCH_COUNT)
            logger.info(
                "RabbitMQ 通道已建立, prefetch_count=%d",
                settings.RABBITMQ_PREFETCH_COUNT,
            )

        return cls._channel

    @classmethod
    async def close(cls) -> None:
        """关闭连接与通道，用于应用关闭时清理资源。"""
        if cls._channel is not None and not cls._channel.is_closed:
            await cls._channel.close()
            cls._channel = None

        if cls._connection is not None and not cls._connection.is_closed:
            await cls._connection.close()
            cls._connection = None

        logger.info("RabbitMQ 连接与通道已关闭")


async def get_mq_channel() -> aio_pika.RobustChannel:
    """获取 RabbitMQ 异步通道（依赖注入用）。

    适用于 FastAPI 路由/服务层注入 Producer 的场景。

    Returns:
        aio_pika.RobustChannel 实例。
    """
    return await MQConnection.get_channel()


def _mask_url(url: str) -> str:
    """脱敏 RabbitMQ URL，隐藏密码，避免日志泄露。

    Args:
        url: 原始 amqp URL。

    Returns:
        脱敏后的 URL 字符串。
    """
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.password:
            # 仅保留用户名与主机，密码替换为 ***
            return f"amqp://{parsed.username}:***@{parsed.hostname}:{parsed.port}{parsed.path}"
        return url
    except Exception:
        return "amqp://***"
