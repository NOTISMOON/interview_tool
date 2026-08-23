"""私信 WebSocket 连接管理器模块（单例）。

管理私信 WS 长连接：
- 每实例维护 user_id -> 连接列表 的内存映射（同一用户多标签页多连接）。
- 通过 Redis Pub/Sub（chat:push:*）实现跨实例消息路由：
    - 发送实例将实时消息 publish 到目标用户通道，所有实例订阅该模式通道；
    - 收到消息后仅本实例持有目标用户连接的实例实际推送，其它实例静默跳过。
- Pub/Sub 监听异常时自动重连（指数退避，沿用 sse_manager 模式）。

发布语义（供 WS 接收处理器调用）：
    publish_to_user(receiver_id, data)：将实时消息广播到接收方所有在在线连接。
"""

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis
from starlette.websockets import WebSocket

from app.core.config import settings
from app.redis.async_client import AsyncRedisClient

logger = logging.getLogger(__name__)

# 私信实时推送通道前缀（config 若无此配置则用默认值，保证与 sse_manager 的 notify:* 隔离）
_CHAT_PUSH_PREFIX = "chat:push"


class ChatConnectionManager:
    """私信 WS 连接管理器（单例）。

    职责：
        - 建立/断开连接时维护本地 user_id -> [WebSocket] 映射。
        - 订阅 Redis Pub/Sub 通道 chat:push:*，收到实时消息按路由分发到对应用户的本地连接。
        - 断线自动重连（指数退避，封顶60秒）。
        - shutdown 清理监听资源。
    """

    # Pub/Sub 断线重连退避基数（秒），指数翻倍封顶60秒
    RECONNECT_BACKOFF_BASE = 2
    RECONNECT_BACKOFF_MAX = 60

    def __init__(self) -> None:
        """初始化连接管理器。"""
        self._connections: dict[int, list[WebSocket]] = {}
        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._running = False

    @property
    def push_channel_prefix(self) -> str:
        """私信推送通道前缀（chat:push:100）。"""
        return _CHAT_PUSH_PREFIX

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """登记一条 WS 连接，并确保 Pub/Sub 监听已启动。

        Args:
            user_id: 用户唯一标识。
            websocket: 已接受握手的 WebSocket 连接对象。
        """
        async with self._lock:
            if not self._running or self._listener_task is None or self._listener_task.done():
                await self._start_listener()
            self._connections.setdefault(user_id, []).append(websocket)
            logger.info(
                "私信WS连接建立 user_id=%s 当前连接数=%s",
                user_id,
                len(self._connections[user_id]),
            )

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """断开一条 WS 连接，仅移除传入的连接实例（不影响同用户其他连接）。

        Args:
            user_id: 用户唯一标识。
            websocket: 待移除的连接对象。
        """
        async with self._lock:
            conns = self._connections.get(user_id)
            if conns is None:
                return
            try:
                conns.remove(websocket)
            except ValueError:
                pass
            if not conns:
                self._connections.pop(user_id, None)
            logger.info("私信WS连接断开 user_id=%s 剩余连接数=%s", user_id, len(conns))

    async def send_to_connections(
        self, user_id: int, data: dict[str, Any], exclude: WebSocket | None = None
    ) -> int:
        """将数据推送到指定用户的本地所有在线连接（多标签页各收一份副本）。

        Args:
            user_id: 目标用户ID。
            data: 待推送数据（JSON 可序列化）。
            exclude: 可选，排除的连接（如发送者自身）。

        Returns:
            实际推送成功的连接数。
        """
        conns = self._connections.get(user_id) or []
        sent = 0
        payload = json.dumps(data, ensure_ascii=False, default=str)
        for conn in list(conns):
            if conn is exclude:
                continue
            try:
                await conn.send_text(payload)
                sent += 1
            except Exception:
                logger.warning("私信WS推送失败，移除失效连接 user_id=%s", user_id)
                await self.disconnect(user_id, conn)
        return sent

    async def publish_to_user(self, receiver_id: int, data: dict[str, Any]) -> None:
        """跨实例发布私信实时事件到目标用户通道。

        所有 API 实例订阅 chat:push:*，收到后由持有该用户连接的实例实际推送。

        Args:
            receiver_id: 接收方用户ID。
            data: 待广播数据。

        Raises:
            aioredis.RedisError: Redis 发布失败时抛出。
        """
        redis_client = await AsyncRedisClient.get_client()
        channel = f"{self.push_channel_prefix}:{receiver_id}"
        await redis_client.publish(channel, json.dumps(data, ensure_ascii=False, default=str))

    async def user_online_count(self, user_id: int) -> int:
        """查询某用户在当前实例的在线连接数。

        Args:
            user_id: 用户唯一标识。

        Returns:
            本实例持有的在线连接数。
        """
        return len(self._connections.get(user_id) or [])

    # ------------------------------------------------------------------
    # 内部：Pub/Sub 监听
    # ------------------------------------------------------------------

    async def _start_listener(self) -> None:
        """启动 Redis Pub/Sub 监听任务（幂等）。"""
        if self._running:
            return
        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop(), name="chat-ws-pubsub-listener")

    async def _listen_loop(self) -> None:
        """持续监听 Redis Pub/Sub 消息，异常时自动重连（指数退避）。"""
        backoff = self.RECONNECT_BACKOFF_BASE
        while self._running:
            try:
                redis_client = await AsyncRedisClient.get_client()
                self._pubsub = redis_client.pubsub()
                await self._pubsub.psubscribe(f"{self.push_channel_prefix}:*")
                logger.info("私信WS Pub/Sub 监听已启动 channels=%s:*", self.push_channel_prefix)
                backoff = self.RECONNECT_BACKOFF_BASE
                async for message in self._pubsub.listen():
                    if message is None:
                        continue
                    await self._dispatch(message)
            except asyncio.CancelledError:
                logger.info("私信WS Pub/Sub 监听任务已取消")
                return
            except Exception:
                logger.exception("私信WS Pub/Sub 监听异常，%s秒后重连", backoff)

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
        """分发 Pub/Sub 消息到本地目标用户连接。

        Args:
            message: Redis Pub/Sub 消息字典。
        """
        if message.get("type") in ("subscribe", "psubscribe", "unsubscribe", "punsubscribe"):
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

        if not channel_str.startswith(f"{self.push_channel_prefix}:"):
            return
        try:
            user_id_str = channel_str.split(":", 2)[-1]
            user_id = int(user_id_str)
        except (ValueError, IndexError):
            logger.warning("无法解析私信WS通道用户ID channel=%s", channel_str)
            return

        payload = self._decode(data)
        local_conns = len(self._connections.get(user_id) or [])
        if local_conns == 0:
            # 多实例下用户连接不在本实例属正常，debug 记录便于排查
            logger.debug("私信推送目标不在本实例，跳过 user_id=%s local_connections=%s", user_id, local_conns)
            return
        await self.send_to_connections(user_id, payload)

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
        """关闭连接管理器，停止监听任务并清理资源。"""
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
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

        async with self._lock:
            for conns in self._connections.values():
                for conn in list(conns):
                    try:
                        await conn.close()
                    except Exception:
                        pass
            self._connections.clear()
        logger.info("私信WS连接管理器已关闭")


# 私信连接管理器单例
chat_connection_manager = ChatConnectionManager()