"""SSE（Server-Sent Events）连接管理器模块。

管理所有 SSE 长连接的用户队列，通过 Redis Pub/Sub 实现跨实例广播：
    - 每个 API 实例维护本地 SSE 连接池（同一用户可存在多个队列，支持多标签页/多端）。
    - 所有实例订阅 Redis Pub/Sub 通道（{prefix}:* 模式 + 广播通道），
      收到消息后查本地队列，仅持有目标用户连接的实例才实际写入 SSE 流。
    - 支持系统广播通道。
    - 监听基础设施（订阅/重连/解码）复用 RedisPubSubListener 基类，
      订阅在应用启动阶段由 main.py 显式 start() 建立，时机确定化。
"""

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.services.redis_pubsub import RedisPubSubListener

logger = logging.getLogger(__name__)


class SSEManager(RedisPubSubListener):
    """SSE 连接管理器（单例），维护用户 -> 队列列表 的映射。

    职责：
        - 建立/断开 SSE 连接时维护本地队列映射（每连接独立队列，多标签页互不干扰）。
        - 基于 RedisPubSubListener 订阅 Redis Pub/Sub，收到消息后推送到本地对应队列。
        - shutdown 时清理本地队列映射。
    """

    def __init__(self) -> None:
        """初始化 SSE 管理器。"""
        super().__init__()
        # 用户 -> 队列列表：同一用户多个标签页/端各持有独立队列
        self._queues: dict[int, list[asyncio.Queue]] = {}
        self._queues_lock = asyncio.Lock()

    @property
    def push_channel_prefix(self) -> str:
        """用户推送通道前缀（来自配置，如 notify:push -> notify:push:100）。"""
        return settings.NOTIFY_PUSH_CHANNEL_PREFIX

    @property
    def broadcast_channel(self) -> str:
        """系统广播通道名（来自配置）。"""
        return settings.NOTIFY_BROADCAST_CHANNEL

    @property
    def pattern_channels(self) -> list[str]:
        """订阅的模式通道：{prefix}:* 匹配所有用户推送通道。"""
        return [f"{self.push_channel_prefix}:*"]

    @property
    def exact_channels(self) -> list[str]:
        """订阅的精确通道：系统广播通道。"""
        return [self.broadcast_channel]

    async def connect(self, user_id: int) -> asyncio.Queue:
        """为用户建立一条 SSE 连接，注册独立队列并确保监听已启动。

        同一用户多次调用（多标签页/多端）返回不同队列实例，消息会复制到每个队列。

        Args:
            user_id: 用户唯一标识。

        Returns:
            本次连接专属的 asyncio.Queue 实例，SSE 端点从此队列读取事件。
        """
        # 幂等确保监听已启动（应用启动阶段已通过 start() 拉起，此处兜底保障）
        await self.start()
        async with self._queues_lock:
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
        async with self._queues_lock:
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

    async def on_message(self, channel: str, payload: Any) -> None:
        """处理一条 Pub/Sub 业务消息，分发给本地用户队列。

        Args:
            channel: 已解码的通道名。
            payload: 已解码的消息负载。
        """
        # 系统广播：推送到所有本地队列
        if channel == self.broadcast_channel:
            try:
                await self._broadcast_to_all(payload)
            except Exception:
                logger.exception("SSE系统广播处理异常 channel=%s", channel)
            return

        # 用户推送：从通道名解析 user_id
        if channel.startswith(f"{self.push_channel_prefix}:"):
            try:
                user_id = int(channel.split(":", 2)[-1])
            except (ValueError, IndexError):
                logger.warning("无法解析Pub/Sub通道用户ID channel=%s", channel)
                return

            # session_kicked 事件记录 INFO 日志以便排查
            if isinstance(payload, dict) and payload.get("kind") == "session_kicked":
                logger.info("SSE Pub/Sub 收到 session_kicked user_id=%s channel=%s", user_id, channel)

            try:
                await self._push_to_user(user_id, payload)
            except Exception:
                logger.exception("SSE用户推送处理异常 user_id=%s channel=%s", user_id, channel)

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

    async def _push_to_user(self, user_id: int, payload: Any) -> None:
        """将消息推送到指定用户的本地所有队列（多标签页各自收到完整副本）。

        Args:
            user_id: 目标用户ID。
            payload: 已解码的消息负载。
        """
        queues = self._queues.get(user_id)
        if not queues:
            # 用户不在本实例属正常（多实例下由持有连接的实例投递）；
            # session_kicked 事件需要 INFO 级以便排查
            kind = payload.get("kind") if isinstance(payload, dict) else None
            if kind == "session_kicked":
                logger.info("SSE推送 session_kicked 目标用户不在本实例，跳过 user_id=%s", user_id)
            else:
                logger.debug("SSE推送目标用户不在本实例，跳过 user_id=%s local_users=%s", user_id, len(self._queues))
            return

        kind = payload.get("kind") if isinstance(payload, dict) else None
        logger.debug(
            "SSE推送分发到本地队列 user_id=%s local_queues=%s kind=%s message_id=%s",
            user_id,
            len(queues),
            kind,
            payload.get("message", {}).get("id")
            if isinstance(payload, dict) and isinstance(payload.get("message"), dict)
            else None,
        )
        if kind == "session_kicked":
            logger.info("SSE推送 session_kicked 已分发到本地队列 user_id=%s queues=%s", user_id, len(queues))
        for queue in queues:
            self._enqueue(queue, user_id, payload)

    async def _broadcast_to_all(self, payload: Any) -> None:
        """将系统广播消息推送到所有本地用户队列。

        Args:
            payload: 已解码的广播消息负载。
        """
        total_conn = sum(len(queues) for queues in self._queues.values())
        logger.info(
            "SSE系统广播分发 kind=%s local_users=%s local_connections=%s",
            payload.get("kind") if isinstance(payload, dict) else type(payload).__name__,
            len(self._queues),
            total_conn,
        )
        for user_id, queues in list(self._queues.items()):
            for queue in queues:
                self._enqueue(queue, user_id, payload)

    async def shutdown(self) -> None:
        """关闭 SSE 管理器：停止监听任务并清理本地队列映射。"""
        await super().shutdown()
        async with self._queues_lock:
            self._queues.clear()
        logger.info("SSE 管理器已关闭")


sse_manager = SSEManager()