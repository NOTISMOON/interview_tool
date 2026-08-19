"""SSE（Server-Sent Events）连接管理器模块。

管理所有 SSE 长连接的用户队列，通过 Redis Pub/Sub 实现跨实例广播：
    - 每个 API 实例维护本地 SSE 连接池（同一用户可存在多个队列，支持多标签页/多端）。
    - 所有实例订阅 Redis Pub/Sub 通道（{prefix}:* 模式），
      收到消息后查本地队列，仅持有目标用户连接的实例才实际写入 SSE 流。
    - 支持系统广播通道。
    - Pub/Sub 监听异常时自动重连（指数退避）。
"""

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.redis.async_client import AsyncRedisClient

logger = logging.getLogger(__name__)


class SSEManager:
    """SSE 连接管理器（单例），维护用户 -> 队列列表 的映射。

    职责：
        - 建立/断开 SSE 连接时维护本地队列映射（每连接独立队列，多标签页互不干扰）。
        - 订阅 Redis Pub/Sub，收到消息后推送到本地对应的所有队列。
        - 监听异常时自动重连（指数退避，封顶60秒）。
        - 提供 shutdown 方法清理资源。
    """

    # Pub/Sub 断线重连退避基数（秒），指数翻倍封顶60秒
    RECONNECT_BACKOFF_BASE = 2
    RECONNECT_BACKOFF_MAX = 60

    def __init__(self) -> None:
        """初始化 SSE 管理器。"""
        # 用户 -> 队列列表：同一用户多个标签页/端各持有独立队列
        self._queues: dict[int, list[asyncio.Queue]] = {}
        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._running = False

    @property
    def push_channel_prefix(self) -> str:
        """用户推送通道前缀（来自配置，如 notify:push -> notify:push:100）。"""
        return settings.NOTIFY_PUSH_CHANNEL_PREFIX

    @property
    def broadcast_channel(self) -> str:
        """系统广播通道名（来自配置）。"""
        return settings.NOTIFY_BROADCAST_CHANNEL

    async def connect(self, user_id: int) -> asyncio.Queue:
        """为用户建立一条 SSE 连接，注册独立队列并确保 Pub/Sub 监听已启动。

        同一用户多次调用（多标签页/多端）返回不同队列实例，消息会复制到每个队列。

        Args:
            user_id: 用户唯一标识。

        Returns:
            本次连接专属的 asyncio.Queue 实例，SSE 端点从此队列读取事件。
        """
        async with self._lock:
            # 确保 Pub/Sub 监听已启动
            if not self._running or self._listener_task is None or self._listener_task.done():
                await self._start_listener()

            queue = asyncio.Queue(maxsize=256)
            self._queues.setdefault(user_id, []).append(queue)
            logger.info("SSE 用户连接建立 user_id=%s 当前连接数=%s", user_id, len(self._queues[user_id]))
            return queue

    async def disconnect(self, user_id: int, queue: asyncio.Queue) -> None:
        """断开一条用户 SSE 连接，仅移除传入的队列实例（不影响同用户其他连接）。

        Args:
            user_id: 用户唯一标识。
            queue: connect 时返回的队列实例。
        """
        async with self._lock:
            queues = self._queues.get(user_id)
            if queues is None:
                return
            try:
                queues.remove(queue)
            except ValueError:
                pass
            if not queues:
                self._queues.pop(user_id, None)
            logger.info("SSE 用户连接断开 user_id=%s 剩余连接数=%s", user_id, len(queues))

    async def _start_listener(self) -> None:
        """启动 Redis Pub/Sub 监听任务（含自动重连循环，幂等：已运行时跳过）。"""
        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop(), name="sse-pubsub-listener")

    async def _listen_loop(self) -> None:
        """持续监听 Redis Pub/Sub 消息，异常时自动重连（指数退避）。"""
        backoff = self.RECONNECT_BACKOFF_BASE
        while self._running:
            try:
                redis_client = await AsyncRedisClient.get_client()
                self._pubsub = redis_client.pubsub()
                # 订阅模式通道：{prefix}:* 匹配所有用户推送通道
                await self._pubsub.psubscribe(f"{self.push_channel_prefix}:*")
                # 订阅系统广播通道
                await self._pubsub.subscribe(self.broadcast_channel)
                logger.info(
                    "SSE Pub/Sub 监听已启动 channels=%s:*,%s",
                    self.push_channel_prefix,
                    self.broadcast_channel,
                )
                # 连接成功，重置退避
                backoff = self.RECONNECT_BACKOFF_BASE

                async for message in self._pubsub.listen():
                    if message is None:
                        continue
                    await self._dispatch(message)
            except asyncio.CancelledError:
                logger.info("SSE Pub/Sub 监听任务已取消")
                return
            except Exception:
                logger.exception("SSE Pub/Sub 监听异常，%s秒后重连", backoff)

            # 清理失效连接后退避重试
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

    async def _dispatch(self, message: dict[str, Any]) -> None:
        """分发 Pub/Sub 消息到本地用户队列。

        Args:
            message: Redis Pub/Sub 消息字典，含 type、channel、data 等字段。
        """
        # 过滤订阅控制消息（subscribe/psubscribe 确认帧，data 为订阅计数而非业务数据）
        if message.get("type") in ("subscribe", "psubscribe", "unsubscribe", "punsubscribe"):
            return

        channel = message.get("channel", "")
        data = message.get("data")

        if data is None:
            return

        # 客户端开启 decode_responses=True 时 channel 为 str，未开启时为 bytes
        if isinstance(channel, bytes):
            channel_str = channel.decode("utf-8")
        elif isinstance(channel, str):
            channel_str = channel
        else:
            return

        # 系统广播：推送到所有本地队列
        if channel_str == self.broadcast_channel:
            await self._broadcast_to_all(data)
            return

        # 用户推送：从通道名解析 user_id
        if channel_str.startswith(f"{self.push_channel_prefix}:"):
            try:
                user_id_str = channel_str.split(":", 2)[-1]
                user_id = int(user_id_str)
            except (ValueError, IndexError):
                logger.warning("无法解析Pub/Sub通道用户ID channel=%s", channel_str)
                return

            await self._push_to_user(user_id, data)

    @staticmethod
    def _decode(data: Any) -> Any:
        """解码 Pub/Sub 消息体（bytes/str JSON -> 对象，解析失败退化为字符串）。"""
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

    @staticmethod
    def _enqueue(queue: asyncio.Queue, user_id: int, data: Any) -> None:
        """将消息放入单个队列，队列满时丢弃最旧消息腾位。"""
        try:
            queue.put_nowait(data)
            logger.debug(
                "SSE事件已入队 user_id=%s kind=%s queue_backlog=%s",
                user_id,
                data.get("kind") if isinstance(data, dict) else type(data).__name__,
                queue.qsize(),
            )
        except asyncio.QueueFull:
            logger.warning(
                "SSE 用户队列已满 user_id=%s queue_size=%s，丢弃旧消息（客户端消费过慢）",
                user_id,
                queue.maxsize,
            )
            try:
                queue.get_nowait()
                queue.put_nowait(data)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    async def _push_to_user(self, user_id: int, data: Any) -> None:
        """将消息推送到指定用户的本地所有队列（多标签页各自收到完整副本）。

        Args:
            user_id: 目标用户ID。
            data: 消息数据（JSON 字符串或字典）。
        """
        queues = self._queues.get(user_id)
        if not queues:
            # 关键排查点：用户不在本实例属正常（多实例下由持有连接的实例投递），
            # debug 级记录以便区分“不在本实例”与“在本实例但未收到”
            logger.debug("SSE推送目标用户不在本实例，跳过 user_id=%s local_users=%s", user_id, len(self._queues))
            return

        payload = self._decode(data)
        logger.debug(
            "SSE推送分发到本地队列 user_id=%s local_queues=%s kind=%s message_id=%s",
            user_id,
            len(queues),
            payload.get("kind") if isinstance(payload, dict) else type(payload).__name__,
            payload.get("message", {}).get("id") if isinstance(payload, dict) else None,
        )
        for queue in queues:
            self._enqueue(queue, user_id, payload)

    async def _broadcast_to_all(self, data: Any) -> None:
        """将系统广播消息推送到所有本地用户队列。

        Args:
            data: 广播消息数据。
        """
        payload = self._decode(data)
        total_conn = sum(len(queues) for queues in self._queues.values())
        logger.info(
            "SSE系统广播分发 kind=%s local_users=%s local_connections=%s",
            payload.get("kind") if isinstance(payload, dict) else type(payload).__name__,
            len(self._queues),
            total_conn,
        )
        for user_id, queues in self._queues.items():
            for queue in queues:
                self._enqueue(queue, user_id, payload)

    async def shutdown(self) -> None:
        """关闭 SSE 管理器，停止监听任务并清理连接。"""
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
                logger.exception("关闭Pub/Sub连接失败")
            self._pubsub = None

        # 清空所有队列映射（队列对象交由各 SSE 生成器的 finally 自然结束）
        async with self._lock:
            self._queues.clear()

        logger.info("SSE 管理器已关闭")


sse_manager = SSEManager()
