"""私信 WebSocket 连接管理器模块（单例）。

管理私信 WS 长连接：
- 每实例维护 user_id -> 连接列表 的内存映射（同一用户多标签页多连接）。
- 通过 Redis Pub/Sub（chat:push:*）实现跨实例消息路由：
    - 发送实例将实时消息 publish 到目标用户通道，所有实例订阅该模式通道；
    - 收到消息后仅本实例持有目标用户连接的实例实际推送，其它实例静默跳过。
- 监听基础设施（订阅/重连/解码）复用 RedisPubSubListener 基类，
  订阅在应用启动阶段由 main.py 显式 start() 建立，时机确定化。

发布语义（供 WS 接收处理器调用）：
    publish_to_user(receiver_id, data)：将实时消息广播到接收方所有在线连接。
"""

import asyncio
import json
import logging
from typing import Any

from starlette.websockets import WebSocket

from app.redis.async_client import AsyncRedisClient
from app.services.redis_pubsub import RedisPubSubListener

logger = logging.getLogger(__name__)

# 私信实时推送通道前缀（与 sse_manager 的 notify:* 隔离）
_CHAT_PUSH_PREFIX = "chat:push"


class ChatConnectionManager(RedisPubSubListener):
    """私信 WS 连接管理器（单例）。

    职责：
        - 建立/断开连接时维护本地 user_id -> [WebSocket] 映射。
        - 订阅 Redis Pub/Sub 通道 chat:push:*，收到实时消息按路由分发到对应用户的本地连接。
        - shutdown 清理监听资源与本地连接。
    """

    def __init__(self) -> None:
        """初始化连接管理器。"""
        super().__init__()
        self._connections: dict[int, list[WebSocket]] = {}
        self._connections_lock = asyncio.Lock()

    @property
    def push_channel_prefix(self) -> str:
        """私信推送通道前缀（chat:push:100）。"""
        return _CHAT_PUSH_PREFIX

    @property
    def pattern_channels(self) -> list[str]:
        """订阅的模式通道：chat:push:* 匹配所有私信推送通道。"""
        return [f"{self.push_channel_prefix}:*"]

    @property
    def exact_channels(self) -> list[str]:
        """私信推送无精确通道，返回空列表。"""
        return []

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """登记一条 WS 连接，并确保 Pub/Sub 监听已启动。

        Args:
            user_id: 用户唯一标识。
            websocket: 已接受握手的 WebSocket 连接对象。
        """
        # 幂等确保监听已启动（应用启动阶段已通过 start() 拉起，此处兜底保障）
        await self.start()
        async with self._connections_lock:
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
        async with self._connections_lock:
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

    async def on_message(self, channel: str, payload: Any) -> None:
        """处理一条 Pub/Sub 私信推送消息，分发到对应用户的本地连接。

        Args:
            channel: 已解码的通道名。
            payload: 已解码的消息负载。
        """
        if not channel.startswith(f"{self.push_channel_prefix}:"):
            return
        try:
            user_id = int(channel.split(":", 2)[-1])
        except (ValueError, IndexError):
            logger.warning("无法解析私信WS通道用户ID channel=%s", channel)
            return

        local_conns = len(self._connections.get(user_id) or [])
        if local_conns == 0:
            # 多实例下用户连接不在本实例属正常，debug 记录便于排查
            logger.debug("私信推送目标不在本实例，跳过 user_id=%s local_connections=%s", user_id, local_conns)
            return
        if not isinstance(payload, dict):
            logger.warning("私信推送负载非对象，跳过 user_id=%s type=%s", user_id, type(payload).__name__)
            return
        await self.send_to_connections(user_id, payload)

    async def shutdown(self) -> None:
        """关闭连接管理器：停止监听任务并关闭本地所有连接。"""
        await super().shutdown()
        async with self._connections_lock:
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