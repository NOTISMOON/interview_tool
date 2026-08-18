"""生产者模块，负责向 RabbitMQ 发布消息。

设计要点：
    - 异步发布，适配 FastAPI 异步事件循环，禁止阻塞 IO。
    - 消息默认持久化（delivery_mode=2），防止 Broker 重启丢消息。
    - 消息体以 JSON 序列化，业务负载放 payload 字段，便于消费端统一解析。
    - 复用 MQConnection 全局通道，避免每次发布都新建连接。
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika

from app.mq.connection import MQConnection
from app.mq.exchanges import ExchangeName, declare_exchange
from app.mq.queues import get_routing_key, QueueName

logger = logging.getLogger(__name__)


class MQProducer:
    """RabbitMQ 异步生产者。

    用法：
        producer = MQProducer()
        await producer.publish(
            exchange=ExchangeName.INTERVIEW,
            routing_queue=QueueName.INTERVIEW_RESUME_PARSE,
            payload={"resume_id": 123, "user_id": 456},
        )

    可选：通过依赖注入获取通道（FastAPI 场景）。
    """

    def __init__(self, channel: aio_pika.RobustChannel | None = None) -> None:
        """初始化生产者。

        Args:
            channel: 可选的 RabbitMQ 通道，不传则使用 MQConnection 全局单例。
        """
        self._channel = channel

    async def _ensure_channel(self) -> aio_pika.RobustChannel:
        """获取可用通道，若未注入则使用全局单例。"""
        if self._channel is not None and not self._channel.is_closed:
            return self._channel
        return await MQConnection.get_channel()

    async def publish(
        self,
        exchange: ExchangeName,
        routing_queue: QueueName,
        payload: dict[str, Any],
        *,
        message_id: str | None = None,
        content_type: str = "application/json",
        priority: int = 0,
    ) -> str:
        """发布消息到指定交换机，routing_key 由队列绑定关系推导。

        Args:
            exchange: 目标交换机名称枚举。
            routing_queue: 目标队列枚举（用于反查 routing_key）。
            payload: 业务负载字典，将作为消息体 JSON 序列化。
            message_id: 消息唯一ID，不传则自动生成 UUID。
            content_type: 内容类型，默认 application/json。
            priority: 消息优先级（0-9），默认 0。

        Returns:
            生成的或传入的 message_id 字符串。

        Raises:
            Exception: 发布失败时抛出。
        """
        routing_key = get_routing_key(routing_queue)
        if message_id is None:
            message_id = uuid.uuid4().hex

        body = self._build_body(message_id, payload)
        channel = await self._ensure_channel()
        target_exchange = await declare_exchange(channel, exchange)

        message = aio_pika.Message(
            body=body.encode("utf-8"),
            content_type=content_type,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            priority=priority,
            message_id=message_id,
            timestamp=datetime.now(timezone.utc),
        )

        await target_exchange.publish(message, routing_key=routing_key)
        logger.info(
            "消息已发布 exchange=%s routing_key=%s message_id=%s",
            exchange.value,
            routing_key,
            message_id,
        )
        return message_id

    @staticmethod
    def _build_body(message_id: str, payload: dict[str, Any]) -> str:
        """构造消息体 JSON 字符串。

        统一信封格式：{message_id, timestamp, payload}，
        便于消费端解析与日志追踪。

        Args:
            message_id: 消息唯一ID。
            payload: 业务负载字典。

        Returns:
            JSON 序列化后的字符串。
        """
        envelope = {
            "message_id": message_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        return json.dumps(envelope, ensure_ascii=False, default=str)
