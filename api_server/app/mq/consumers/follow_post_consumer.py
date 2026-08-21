"""关注动态通知消费者模块。

消费 social.follow.post.notify.queue 队列，当关注的用户发布新帖子时，
为粉丝创建通知消息并通过 Redis Pub/Sub 推送实时提醒。

流程:
    1. 从 MQ 消息中解析 post.created 事件（含 post_id、author_id、title）。
    2. 从数据库查询作者的粉丝列表。
    3. 对每个粉丝（上限 1000 人）创建通知消息。
    4. 通过 Redis Pub/Sub 广播通知到 SSE 连接。

大V（粉丝>1000）跳过通知，避免写放大。粉丝可通过 Feed 动态流获取帖子。
"""

import asyncio
import logging
import time
from typing import Any

from app.db.sync_session import SyncSessionLocal
from app.models.message import MESSAGE_TYPE_FOLLOW_POST, RELATED_TYPE_POST
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.repositories.user_repository import sync_user_repository
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

ROUTING_POST_CREATED = "social.post.created"

# 单次通知粉丝上限：防止大V刷爆通知表
MAX_FOLLOWER_NOTIFY = 1000


class FollowPostNotifyConsumer(BaseConsumer):
    """关注动态通知消费者，消费 post.created 事件并为粉丝创建通知。"""

    queue_name = QueueName.SOCIAL_FOLLOW_POST_NOTIFY

    async def handle_message(self, message: MQMessage) -> None:
        """处理帖子创建事件：为粉丝创建关注动态通知。

        Args:
            message: 入站消息对象。

        Raises:
            ValueError: 未知routing_key时抛出，进入死信队列。
        """
        if message.routing_key != ROUTING_POST_CREATED:
            raise ValueError(f"未知routing_key: {message.routing_key} message_id={message.message_id}")
        await self._on_post_created(message.payload)

    async def _on_post_created(self, payload: dict[str, Any]) -> None:
        """处理帖子创建事件：为作者的粉丝创建通知。

        Args:
            payload: 含post_id、author_id、title的事件负载。
        """
        post_id = int(payload["post_id"])
        author_id = int(payload["author_id"])
        title = payload.get("title", "")
        started_at = time.monotonic()
        logger.info("关注动态通知开始 post_id=%s author_id=%s", post_id, author_id)

        # 1. 获取作者粉丝列表（同步DB操作，通过to_thread避免阻塞事件循环）
        follower_ids = await asyncio.to_thread(self._get_follower_ids, author_id)
        if not follower_ids:
            logger.info("作者无粉丝，跳过通知 post_id=%s author_id=%s", post_id, author_id)
            return

        # 截断大V粉丝列表
        if len(follower_ids) > MAX_FOLLOWER_NOTIFY:
            logger.info("粉丝数超限截断 post_id=%s author_id=%s count=%s", post_id, author_id, len(follower_ids))
            follower_ids = follower_ids[:MAX_FOLLOWER_NOTIFY]

        # 2. 获取作者昵称
        author_nickname = await asyncio.to_thread(self._get_author_nickname, author_id)

        # 3. 逐条创建通知 + 推送SSE
        notified_count = 0
        for follower_id in follower_ids:
            try:
                await self._notify_follower(follower_id, author_id, author_nickname, post_id, title)
                notified_count += 1
            except Exception:
                logger.exception("通知粉丝失败 follower_id=%s post_id=%s", follower_id, post_id)

        logger.info(
            "关注动态通知完成 post_id=%s author_id=%s notified=%s/%s elapsed_ms=%d",
            post_id, author_id, notified_count, len(follower_ids),
            (time.monotonic() - started_at) * 1000,
        )

    def _get_follower_ids(self, author_id: int) -> list[int]:
        """同步查询作者粉丝ID列表。

        Args:
            author_id: 作者用户ID。

        Returns:
            粉丝ID列表。
        """
        db = SyncSessionLocal()
        try:
            return sync_user_repository.get_follower_ids(db, author_id)
        finally:
            db.close()

    def _get_author_nickname(self, author_id: int) -> str:
        """同步查询作者昵称。

        Args:
            author_id: 作者用户ID。

        Returns:
            作者昵称，查询失败返回默认值。
        """
        db = SyncSessionLocal()
        try:
            author = sync_user_repository.get_by_id(db, author_id)
            return author.nickname if author else "未知用户"
        except Exception:
            logger.exception("查询作者信息失败 author_id=%s", author_id)
            return "未知用户"
        finally:
            db.close()

    async def _notify_follower(
        self,
        follower_id: int,
        author_id: int,
        author_nickname: str,
        post_id: int,
        post_title: str,
    ) -> None:
        """为单个粉丝创建通知并推送SSE。

        Args:
            follower_id: 粉丝用户ID。
            author_id: 帖子作者用户ID。
            author_nickname: 作者昵称。
            post_id: 帖子ID。
            post_title: 帖子标题。
        """
        # 同步创建通知（DB操作）
        message_id = await asyncio.to_thread(
            self._create_notification_sync,
            follower_id, author_id, author_nickname, post_id, post_title,
        )
        if message_id is None:
            return

        # 异步推送SSE
        try:
            from app.db.async_session import AsyncSessionLocal
            from app.repositories.message_repository import message_repository

            async with AsyncSessionLocal() as async_db:
                # 查询最新创建的这条通知
                msg = await message_repository.get_by_id(async_db, follower_id, message_id)
                if msg is None:
                    return
                unread_total = await message_repository.get_unread_count(async_db, follower_id)
                message_response = (await notification_service.to_responses(async_db, [msg]))[0]
                sse_event = {
                    "kind": "message",
                    "message": message_response.model_dump(mode="json", by_alias=True),
                    "unread_total": unread_total,
                }
                await notification_service.publish_to_user(follower_id, sse_event)
        except Exception:
            logger.exception("SSE推送失败 follower_id=%s post_id=%s", follower_id, post_id)

    def _create_notification_sync(
        self,
        follower_id: int,
        author_id: int,
        author_nickname: str,
        post_id: int,
        post_title: str,
    ) -> int | None:
        """同步创建通知消息（DB事务内）。

        Args:
            follower_id: 粉丝用户ID。
            author_id: 帖子作者用户ID。
            author_nickname: 作者昵称。
            post_id: 帖子ID。
            post_title: 帖子标题。

        Returns:
            创建的消息ID，失败返回None。
        """
        db = SyncSessionLocal()
        try:
            msg = notification_service.create_notification(
                db=db,
                recipient_id=follower_id,
                msg_type=MESSAGE_TYPE_FOLLOW_POST,
                title="关注动态",
                content=f"你关注的 {author_nickname} 发布了新帖子《{post_title}》",
                from_user_id=author_id,
                related_id=post_id,
                related_type=RELATED_TYPE_POST,
            )
            db.commit()
            return msg.id
        except Exception:
            db.rollback()
            logger.exception("创建通知失败 follower_id=%s", follower_id)
            return None
        finally:
            db.close()