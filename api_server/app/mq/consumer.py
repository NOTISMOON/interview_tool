"""消费者基类模块。

封装消息消费的通用流程：消息解析、异常处理、ACK/Reject 策略、日志记录。
具体业务消费者只需继承 BaseConsumer 并实现 handle_message 方法。

ACK/Reject 策略：
    - 处理成功：ack（消息从队列移除）。
    - 处理失败（业务异常）：reject 并 requeue=False（配置了DLX的队列进入死信队列
      存档，未配置则丢弃，避免无限重试）。
    - 解析失败（消息格式错误）：reject 并 requeue=False（毒消息丢弃）。
    - 网络异常：依赖 RobustChannel 自动重连，消息不 ACK，Broker 会重新投递。
"""

import abc
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import aio_pika

from app.mq.connection import MQConnection
from app.mq.queues import QueueName, ensure_queue_topology

logger = logging.getLogger(__name__)


@dataclass
class MQMessage:
    """统一的入站消息封装，便于业务层消费。

    Attributes:
        message_id: 消息唯一ID（来自信封）。
        timestamp: 消息发送时间（ISO 字符串）。
        payload: 业务负载字典。
        raw: aio_pika 原始 IncomingMessage 对象，用于 ACK/Nack 操作。
        routing_key: 消息路由键（默认空串，同一队列消费多类事件时用于区分来源）。
    """

    message_id: str
    timestamp: str
    payload: dict[str, Any]
    raw: aio_pika.IncomingMessage
    routing_key: str = ""


class BaseConsumer(abc.ABC):
    """消费者抽象基类。

    子类需实现 handle_message 方法，并指定消费的队列 queue_name。
    提供 start/stop 控制方法，由 runner 统一编排。

    示例：
        class MyConsumer(BaseConsumer):
            queue_name = QueueName.INTERVIEW_RESUME_PARSE

            async def handle_message(self, message: MQMessage) -> None:
                resume_id = message.payload["resume_id"]
                await parse_resume(resume_id)
    """

    queue_name: QueueName

    def __init__(self) -> None:
        """初始化消费者，预置队列与标签。"""
        self._queue: aio_pika.RobustQueue | None = None
        self._consumer_tag: str | None = None

    async def start(self) -> str:
        """启动消费者，订阅指定队列。

        订阅前确保该队列的完整拓扑（队列声明+交换机绑定+死信队列），
        独立启动场景（未经runner统一声明）下仅声明不绑定会导致
        消息发往交换机后无路由可达而被Broker静默丢弃。

        Returns:
            consumer_tag 字符串，用于后续取消订阅。
        """
        channel = await MQConnection.get_channel()
        self._queue = await ensure_queue_topology(channel, self.queue_name)

        self._consumer_tag = await self._queue.consume(self._on_message)
        logger.info(
            "消费者已启动 queue=%s consumer_tag=%s",
            self.queue_name.value,
            self._consumer_tag,
        )
        return self._consumer_tag

    async def stop(self) -> None:
        """停止消费者，取消订阅。"""
        if self._queue is not None and self._consumer_tag is not None:
            await self._queue.cancel(self._consumer_tag)
            logger.info("消费者已停止 queue=%s", self.queue_name.value)
            self._consumer_tag = None
            self._queue = None

    async def _on_message(self, message: aio_pika.IncomingMessage) -> None:
        """消息到达回调，负责解析、分发与异常兜底。

        异常向外抛出后由 message.process 统一 reject(requeue=False)：
        队列配置了 DLX 时进入死信队列存档（支撑人工重放），未配置则丢弃。

        Args:
            message: aio_pika IncomingMessage 对象。
        """
        message_id = message.message_id or "(unknown)"
        routing_key = message.routing_key or ""
        logger.debug(
            "MQ消息到达 queue=%s message_id=%s routing_key=%s body_size=%s",
            self.queue_name.value,
            message_id,
            routing_key,
            len(message.body),
        )
        started_at = time.monotonic()
        async with message.process(requeue=False, ignore_processed=True):
            try:
                mq_msg = self._parse(message)
            except Exception:
                # 解析失败：毒消息，reject不重投，避免无限重投
                logger.exception(
                    "消息解析失败，将reject丢弃 queue=%s message_id=%s",
                    self.queue_name.value,
                    message_id,
                )
                raise

            try:
                await self.handle_message(mq_msg)
            except Exception:
                # 业务处理失败：reject不重投避免循环；配置DLX的队列由死信队列存档
                logger.exception(
                    "消息处理失败，将reject queue=%s message_id=%s routing_key=%s elapsed_ms=%d",
                    self.queue_name.value,
                    message_id,
                    routing_key,
                    (time.monotonic() - started_at) * 1000,
                )
                raise

            logger.info(
                "消息处理成功 queue=%s message_id=%s routing_key=%s elapsed_ms=%d",
                self.queue_name.value,
                message_id,
                routing_key,
                (time.monotonic() - started_at) * 1000,
            )

    @staticmethod
    def _parse(message: aio_pika.IncomingMessage) -> MQMessage:
        """解析入站消息，反序列化信封。

        Args:
            message: aio_pika IncomingMessage 对象。

        Returns:
            MQMessage 封装对象。

        Raises:
            json.JSONDecodeError: 消息体非合法 JSON。
            KeyError: 信封缺少必要字段。
        """
        body = message.body.decode("utf-8")
        envelope = json.loads(body)
        return MQMessage(
            message_id=envelope["message_id"],
            timestamp=envelope["timestamp"],
            payload=envelope["payload"],
            raw=message,
            routing_key=message.routing_key or "",
        )

    @abc.abstractmethod
    async def handle_message(self, message: MQMessage) -> None:
        """业务消息处理逻辑，子类必须实现。

        Args:
            message: 统一封装的入站消息对象。

        Raises:
            Exception: 业务处理失败时抛出，由基类统一兜底。
        """
        raise NotImplementedError
