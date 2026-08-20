"""互动缓存同步消费者模块。

消费 social.interaction.cache.queue 队列，将点赞/收藏事件异步同步到Redis缓存。

事件路由:
    social.post.liked       → 更新点赞SET缓存
    social.post.unliked     → 失效点赞SET缓存
    social.post.favorited   → 更新收藏SET缓存
    social.post.unfavorited → 失效收藏SET缓存

幂等性: Redis SET操作（SADD/SREM）天然幂等，重复消费无副作用。
"""

import logging
from typing import Any

from app.cache.interaction_cache import interaction_cache
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.redis.async_client import AsyncRedisClient

logger = logging.getLogger(__name__)

ROUTING_LIKED = "social.post.liked"
ROUTING_UNLIKED = "social.post.unliked"
ROUTING_FAVORITED = "social.post.favorited"
ROUTING_UNFAVORITED = "social.post.unfavorited"


class InteractionCacheSyncConsumer(BaseConsumer):
    """互动缓存同步消费者，消费点赞/收藏事件并维护Redis缓存。"""

    queue_name = QueueName.SOCIAL_INTERACTION_CACHE

    async def handle_message(self, message: MQMessage) -> None:
        """按routing_key分发到对应事件处理器。

        Args:
            message: 入站消息对象。

        Raises:
            ValueError: 未知routing_key时抛出，进入死信队列。
        """
        payload = message.payload
        routing_key = message.routing_key

        if routing_key == ROUTING_LIKED:
            await self._on_liked(payload)
        elif routing_key == ROUTING_UNLIKED:
            await self._on_unliked(payload)
        elif routing_key == ROUTING_FAVORITED:
            await self._on_favorited(payload)
        elif routing_key == ROUTING_UNFAVORITED:
            await self._on_unfavorited(payload)
        else:
            raise ValueError(f"未知routing_key: {routing_key} message_id={message.message_id}")

    async def _on_liked(self, payload: dict[str, Any]) -> None:
        """处理点赞事件：更新Redis点赞SET。

        Args:
            payload: 含post_id、user_id的事件负载。
        """
        post_id = int(payload["post_id"])
        user_id = int(payload["user_id"])

        client = await AsyncRedisClient.get_client()
        interaction_cache.add_like(client, post_id, user_id)

        logger.info("点赞事件缓存同步完成 post_id=%s user_id=%s", post_id, user_id)

    async def _on_unliked(self, payload: dict[str, Any]) -> None:
        """处理取消点赞事件：移除Redis点赞SET。

        Args:
            payload: 含post_id、user_id的事件负载。
        """
        post_id = int(payload["post_id"])
        user_id = int(payload["user_id"])

        client = await AsyncRedisClient.get_client()
        interaction_cache.remove_like(client, post_id, user_id)

        logger.info("取消点赞事件缓存同步完成 post_id=%s user_id=%s", post_id, user_id)

    async def _on_favorited(self, payload: dict[str, Any]) -> None:
        """处理收藏事件：更新Redis收藏SET。

        Args:
            payload: 含post_id、user_id的事件负载。
        """
        post_id = int(payload["post_id"])
        user_id = int(payload["user_id"])

        client = await AsyncRedisClient.get_client()
        interaction_cache.add_favorite(client, post_id, user_id)

        logger.info("收藏事件缓存同步完成 post_id=%s user_id=%s", post_id, user_id)

    async def _on_unfavorited(self, payload: dict[str, Any]) -> None:
        """处理取消收藏事件：移除Redis收藏SET。

        Args:
            payload: 含post_id、user_id的事件负载。
        """
        post_id = int(payload["post_id"])
        user_id = int(payload["user_id"])

        client = await AsyncRedisClient.get_client()
        interaction_cache.remove_favorite(client, post_id, user_id)

        logger.info("取消收藏事件缓存同步完成 post_id=%s user_id=%s", post_id, user_id)