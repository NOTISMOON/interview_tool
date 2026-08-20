"""Feed Push消费者模块。

消费 social.feed.push.queue 队列，当帖子创建时，Push到粉丝的Feed收件箱。

Push流程:
    1. 从关注SET取出粉丝列表
    2. 大V（粉丝>1万）跳过Push，粉丝自行Pull
    3. 批量ZADD post_id到粉丝 feed:inbox:user:{follower_id}

幂等性: ZADD天然幂等，重复消费无副作用。
"""

import asyncio
import logging
from typing import Any

from app.cache.feed_cache import BIG_V_FOLLOWER_THRESHOLD, feed_cache
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.redis.sync_client import SyncRedisClient

logger = logging.getLogger(__name__)

ROUTING_POST_CREATED = "social.post.created"


class FeedPushConsumer(BaseConsumer):
    """Feed Push消费者，消费帖子创建事件并Push到粉丝Feed。"""

    queue_name = QueueName.SOCIAL_FEED_PUSH

    async def handle_message(self, message: MQMessage) -> None:
        """处理帖子创建事件：Push到粉丝Feed收件箱。

        Args:
            message: 入站消息对象。

        Raises:
            ValueError: 未知routing_key时抛出，进入死信队列。
        """
        if message.routing_key != ROUTING_POST_CREATED:
            raise ValueError(f"未知routing_key: {message.routing_key} message_id={message.message_id}")

        await self._on_post_created(message.payload)

    async def _on_post_created(self, payload: dict[str, Any]) -> None:
        """处理帖子创建事件：批量Push到粉丝Feed。

        Args:
            payload: 含post_id、author_id、created_at_ms的事件负载。
        """
        post_id = int(payload["post_id"])
        author_id = int(payload["author_id"])
        created_at_ms = int(payload.get("created_at_ms", 0))

        # 从DB获取粉丝列表
        from app.repositories.user_repository import sync_user_repository as follow_repo
        from app.db.sync_session import SyncSessionLocal

        db = SyncSessionLocal()
        try:
            follower_ids = follow_repo.get_follower_ids(db, author_id)
            follower_count = len(follower_ids)
            if follower_count > BIG_V_FOLLOWER_THRESHOLD:
                logger.info(
                    "大V帖子跳过Push author_id=%s post_id=%s follower_count=%s",
                    author_id,
                    post_id,
                    follower_count,
                )
                return

            # feed_cache.batch_push_post 为同步方法（同步Redis Pipeline），
            # 通过 to_thread 避免阻塞事件循环
            sync_client = SyncRedisClient.get_client()
            await asyncio.to_thread(
                feed_cache.batch_push_post,
                sync_client,
                follower_ids,
                post_id,
                created_at_ms,
            )

            logger.info(
                "Feed Push完成 post_id=%s author_id=%s pushed_to=%s",
                post_id,
                author_id,
                len(follower_ids),
            )
        finally:
            db.close()