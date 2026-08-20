"""评论缓存同步消费者模块。

消费 social.comment.cache.queue 队列（由Outbox Relay投递），将评论创建/删除
事件异步同步到Redis缓存（评论列表缓存失效、帖子评论数缓存等）。

幂等性: 缓存失效操作（DELETE）天然幂等，重复消费无害。

事件路由: 按消息routing_key分发（social.comment.created / social.comment.deleted），
与outbox event_type一一对应。
"""

import logging
from typing import Any

import redis.asyncio as aioredis

from app.cache.comment_cache import comment_cache
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.redis.async_client import AsyncRedisClient

logger = logging.getLogger(__name__)

# routing_key常量
ROUTING_COMMENT_CREATED = "social.comment.created"
ROUTING_COMMENT_DELETED = "social.comment.deleted"


class CommentCacheSyncConsumer(BaseConsumer):
    """评论缓存同步消费者，消费评论事件并维护Redis缓存。"""

    queue_name = QueueName.SOCIAL_COMMENT_CACHE

    async def handle_message(self, message: MQMessage) -> None:
        """按routing_key分发到对应事件处理器。

        Args:
            message: 入站消息对象（payload为outbox_event.payload原样透传）。

        Raises:
            ValueError: 未知routing_key或payload缺少必要字段时抛出，进入死信队列。
        """
        payload = message.payload
        if message.routing_key == ROUTING_COMMENT_CREATED:
            await self._on_comment_created(payload)
        elif message.routing_key == ROUTING_COMMENT_DELETED:
            await self._on_comment_deleted(payload)
        else:
            raise ValueError(f"未知routing_key: {message.routing_key} message_id={message.message_id}")

    async def _on_comment_created(self, payload: dict[str, Any]) -> None:
        """处理评论创建事件：失效帖子评论列表缓存。

        Args:
            payload: 含post_id、comment_id的事件负载。
        """
        post_id = int(payload["post_id"])
        comment_id = int(payload["comment_id"])
        is_reply = bool(payload.get("is_reply", False))

        client = await AsyncRedisClient.get_client()

        # 失效帖子评论列表缓存（新评论导致列表变化）
        comment_cache.invalidate_list(client, post_id)

        logger.info(
            "评论创建事件缓存同步完成 comment_id=%s post_id=%s is_reply=%s",
            comment_id,
            post_id,
            is_reply,
        )

    async def _on_comment_deleted(self, payload: dict[str, Any]) -> None:
        """处理评论删除事件：失效帖子评论列表缓存。

        Args:
            payload: 含post_id、comment_id的事件负载。
        """
        post_id = int(payload["post_id"])
        comment_id = int(payload["comment_id"])

        client = await AsyncRedisClient.get_client()

        # 失效帖子评论列表缓存
        comment_cache.invalidate_list(client, post_id)

        logger.info(
            "评论删除事件缓存同步完成 comment_id=%s post_id=%s",
            comment_id,
            post_id,
        )