"""Redis Pub/Sub 广播监听器抽象基类（异步）。

抽离各实时推送管理器共有的 Redis Pub/Sub 订阅基础设施：
    - 统一管理启动/关闭，幂等可重入。
    - 订阅一组模式通道 + 一组精确通道。
    - 断线自动重连（指数退避，封顶60秒）。
    - 统一消息解码与订阅控制帧过滤。

子类只需实现三个抽象成员即可复用整套监听/重连/解码能力：
    - pattern_channels：待订阅的模式通道（含通配符，如 ["notify:push:*"]）。
    - exact_channels：待订阅的精确通道（如 ["notify:broadcast"]）。
    - on_message：处理一条已解码的业务消息。

设计动机（抽离解决代码冗余 + 订阅时机不确定）：
    sse_manager 与 chat_connection_manager 原先各自实现了一套几乎相同的
    "监听循环/重连退避/消息解码/分发"逻辑，存在明显代码冗余；且二者均采用
    "首个连接建立才启动"的懒初始化，导致 Redis 广播订阅时机不确定。抽离为
    基类后，在应用启动阶段显式 start()，让订阅在进程启动时立即建立。

注意：本基类只负责监听基础设施，本地队列/连接池的维护与投递由子类各自实现。
"""

import abc
import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.redis.async_client import AsyncRedisClient

logger = logging.getLogger(__name__)

# 订阅控制帧类型（subscribe/psubscribe 确认帧，data 为订阅计数而非业务数据）
_SUB_CONTROL_TYPES = ("subscribe", "psubscribe", "unsubscribe", "punsubscribe")


class RedisPubSubListener(abc.ABC):
    """Redis Pub/Sub 广播监听器抽象基类。

    职责：
        - start() 幂等启动监听任务（可重入）。
        - shutdown() 关闭监听任务并释放 Pub/Sub 连接。
        - 断线时按指数退避自动重连。

    用法：
        子类实现 pattern_channels / exact_channels / on_message 后，
        在应用启动阶段调用 start()，在关闭阶段调用 shutdown()。
    """

    # 断线重连退避基数（秒），指数翻倍封顶60秒
    RECONNECT_BACKOFF_BASE = 2
    RECONNECT_BACKOFF_MAX = 60

    def __init__(self) -> None:
        """初始化监听基础状态。"""
        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._running = False

    @property
    @abc.abstractmethod
    def pattern_channels(self) -> list[str]:
        """待订阅的模式通道列表（含通配符）。

        Returns:
            模式通道字符串列表。
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def exact_channels(self) -> list[str]:
        """待订阅的精确通道列表。

        Returns:
            精确通道字符串列表。
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def on_message(self, channel: str, payload: Any) -> None:
        """处理一条业务消息。

        Args:
            channel: 已解码为字符串的通道名。
            payload: 已解码的消息负载（dict/str 等）。
        """
        raise NotImplementedError

    def listen_task_name(self) -> str:
        """监听任务名（便于日志定位），默认以类名命名。

        Returns:
            任务名字符串。
        """
        return f"{self.__class__.__name__.lower()}-pubsub-listener"

    async def start(self) -> None:
        """幂等启动监听任务（可重入，供应用启动阶段显式拉起）。"""
        async with self._lock:
            if self._running and self._listener_task is not None and not self._listener_task.done():
                return
            self._running = True
            if self._listener_task is None or self._listener_task.done():
                self._listener_task = asyncio.create_task(
                    self._listen_loop(), name=self.listen_task_name()
                )

    async def _listen_loop(self) -> None:
        """持续监听 Redis Pub/Sub 消息，异常时自动重连（指数退避）。"""
        backoff = self.RECONNECT_BACKOFF_BASE
        while self._running:
            try:
                redis_client = await AsyncRedisClient.get_client()
                self._pubsub = redis_client.pubsub()
                for pattern in self.pattern_channels:
                    await self._pubsub.psubscribe(pattern)
                for channel in self.exact_channels:
                    await self._pubsub.subscribe(channel)
                logger.info(
                    "Pub/Sub 监听已启动 listener=%s patterns=%s channels=%s",
                    self.listen_task_name(),
                    self.pattern_channels,
                    self.exact_channels,
                )
                # 连接成功，重置退避基数
                backoff = self.RECONNECT_BACKOFF_BASE

                async for message in self._pubsub.listen():
                    if message is None:
                        continue
                    await self._handle_raw(message)
            except asyncio.CancelledError:
                logger.info("Pub/Sub 监听任务已取消 listener=%s", self.listen_task_name())
                return
            except Exception:
                logger.exception(
                    "Pub/Sub 监听异常，%s秒后重连 listener=%s",
                    backoff,
                    self.listen_task_name(),
                )

            # 清理失效 Pub/Sub 连接后退避重试
            if self._pubsub is not None:
                try:
                    await self._pubsub.close()
                except Exception:
                    pass
                self._pubsub = None
            if not self._running:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.RECONNECT_BACKOFF_MAX)

    async def _handle_raw(self, message: dict[str, Any]) -> None:
        """解码单条原始 Pub/Sub 消息并分发给 on_message。

        过滤订阅控制帧；channel 在 decode_responses=False 时为 bytes，需解码。

        Args:
            message: Redis Pub/Sub 消息字典。
        """
        if message.get("type") in _SUB_CONTROL_TYPES:
            return
        channel = message.get("channel", "")
        data = message.get("data")
        if data is None:
            return
        if isinstance(channel, bytes):
            channel_str = channel.decode("utf-8")
        elif isinstance(channel, str):
            channel_str = channel
        else:
            return
        payload = self._decode(data)
        await self.on_message(channel_str, payload)

    @staticmethod
    def _decode(data: Any) -> Any:
        """解码 Pub/Sub 消息体（bytes/str JSON -> 对象，解析失败退化为字符串）。

        Args:
            data: 原始 Pub/Sub 数据。

        Returns:
            解码后的对象。
        """
        if isinstance(data, bytes):
            try:
                return json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                return data.decode("utf-8")
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
        return data

    async def shutdown(self) -> None:
        """关闭监听器，停止监听任务并释放 Pub/Sub 连接。

        Note:
            本地队列/连接池的清理由子类负责（各自维护的本地映射）。
        """
        self._running = False
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub is not None:
            try:
                await self._pubsub.punsubscribe()
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                logger.exception("关闭Pub/Sub连接失败 listener=%s", self.listen_task_name())
            self._pubsub = None