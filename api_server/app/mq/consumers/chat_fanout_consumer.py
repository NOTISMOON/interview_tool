"""私信扇出消费者模块。

消费 chat.fanout.queue 队列（由 Outbox Relay 投递 chat.message.sent 事件），
将有新私信的副作用扇出到接收方：
    1. 未读数：Redis HINCRBY unread:{receiver_id} {conversation_id} 1。
    2. 实时推送：经 chat_connection_manager.publish_to_user 广播到接收方在线 WS
       （跨实例由持有连接的实例实际推送）。

事件载荷（由 chat_repository.insert_outbox 写入）：
    conversation_id / from_user_id / receiver_id / client_msg_id / seq

幂等性：HINCRBY 非幂等，但 Outbox Relay at-least-once + 消费端 BaseConsumer
处理失败 reject 进入（本队列未配DLX）丢弃，正常路径无重复；如需严格幂等
可由调用侧以 client_msg_id 判重（当前私信写缓冲已用 client_msg_id 幂等保证单次落库，
故扇出事件实际单次，此处依赖该前置约束）。
"""

import asyncio
import json
import logging
import time

import redis.asyncio as aioredis

from app.db.async_session import AsyncSessionLocal
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.redis.async_client import AsyncRedisClient
from app.services.chat_connection_manager import chat_connection_manager
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

# 未读数 HASH 键前缀：unread:{user_id}，field=conversation_id，value=未读数
UNREAD_KEY_PREFIX = "unread:"


class ChatMessageFanoutConsumer(BaseConsumer):
    """私信扇出消费者：维护未读数并推送接收方（WS + SSE 双通道）。"""

    queue_name = QueueName.CHAT_FANOUT

    async def handle_message(self, message: MQMessage) -> None:
        """处理聊天消息落库事件：更新未读数 + 推送对端。

        双通道推送：
            - WS（chat:push:*）：聊天页实时收到新消息气泡。
            - SSE（notify:push:*）：消息中心/任意打开 SSE 的页面实时刷新未读数。

        Args:
            message: 入站消息对象，payload 含 receiver_id/conversation_id 等。

        Raises:
            ValueError: payload 缺少 receiver_id 时抛出。
        """
        payload = message.payload
        receiver_id = payload.get("receiver_id")
        conversation_id = payload.get("conversation_id")
        from_user_id = payload.get("from_user_id")
        seq = payload.get("seq")
        client_msg_id = payload.get("client_msg_id")

        if receiver_id is None or conversation_id is None:
            raise ValueError(f"私信扇出事件缺少必要字段 receiver_id={receiver_id} conversation_id={conversation_id}")

        receiver_id = int(receiver_id)
        conversation_id = int(conversation_id)
        started_at = time.monotonic()

        redis_client: aioredis.Redis = await AsyncRedisClient.get_client()
        unread_key = f"{UNREAD_KEY_PREFIX}{receiver_id}"
        # Hash 未读数自增；hash 存在性/过期由读路径惰性处理
        await redis_client.hincrby(unread_key, str(conversation_id), 1)

        # 跨实例推送实时新消息到接收方在线 WS（聊天页即时气泡）
        await chat_connection_manager.publish_to_user(
            receiver_id,
            {
                "action": "new_message",
                "conversation_id": conversation_id,
                "from_user_id": from_user_id,
                "client_msg_id": client_msg_id,
                "seq": seq,
            },
        )

        # 计算含私信的最新总未读，并经 SSE 通道推送，使消息中心/页面实时刷新未读数
        try:
            async with AsyncSessionLocal() as db:
                unread = await notification_service.get_unread_count(db, receiver_id)
            await notification_service.publish_to_user(
                receiver_id,
                {
                    "kind": "unread_count",
                    "total": unread.total,
                    "by_type": unread.by_type,
                },
            )
        except Exception:
            # 未读推送失败不阻断（未读已写入 Redis，刷新时仍会取到）
            logger.exception("私信扇出SSE未读推送失败 receiver_id=%s", receiver_id)

        logger.info(
            "私信扇出完成 mq_message_id=%s receiver_id=%s conv=%s unread_incr=1 elapsed_ms=%d",
            message.message_id,
            receiver_id,
            conversation_id,
            (time.monotonic() - started_at) * 1000,
        )