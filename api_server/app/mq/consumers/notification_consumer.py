"""通知投递消费者模块。

消费 notification.deliver.queue 队列（由 Outbox Relay 投递），
将通知事件写入 MySQL message 表，并通过 Redis Pub/Sub 广播到 SSE 连接所在实例。

流程:
    1. 从 MQ 消息中解析 notification.created 事件。
    2. 写入 message 表（异步 DB 会话），获取自增 message_id。
    3. 查询未读总数。
    4. 封装 SSE 事件并通过 Redis PUBLISH 广播。
    5. ACK MQ 消息。

幂等性: 不依赖去重表；若 MQ 重投导致重复写 message，MySQL 多条独立记录不冲突，
    前端通过 message_id 去重合并。
"""

import logging
import time

from app.db.async_session import AsyncSessionLocal
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.repositories.message_repository import message_repository
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)


class NotificationConsumer(BaseConsumer):
    """通知投递消费者，消费 notification.deliver.queue。"""

    queue_name = QueueName.NOTIFICATION_DELIVER

    async def handle_message(self, message: MQMessage) -> None:
        """处理通知投递事件：写 MySQL + Redis Pub/Sub 广播。

        日志埋点（排查链路: mq_message_id 即 outbox event_id，与 message_id 三段可串联）:
            - 通知消费开始 / 通知已落库 / 通知已投递 三条 INFO 贯穿全程，均带双 ID 与耗时。

        Args:
            message: 入站消息对象，payload 含 recipient_id、type、title、content 等字段。

        Raises:
            ValueError: payload 缺少必要字段时抛出。
        """
        payload = message.payload
        recipient_id = payload.get("recipient_id")
        msg_type = payload.get("type")
        title = payload.get("title", "")
        content = payload.get("content", "")
        from_user_id = payload.get("from_user_id")
        related_id = payload.get("related_id")
        related_type = payload.get("related_type")

        if recipient_id is None or msg_type is None:
            raise ValueError(f"通知事件缺少必要字段 recipient_id={recipient_id} type={msg_type}")

        recipient_id = int(recipient_id)
        msg_type = int(msg_type)

        started_at = time.monotonic()
        logger.info(
            "通知消费开始 mq_message_id=%s recipient_id=%s type=%s routing_key=%s",
            message.message_id,
            recipient_id,
            msg_type,
            message.routing_key,
        )

        # 1. 写入 MySQL message 表
        async with AsyncSessionLocal() as db:
            msg = await message_repository.create(
                db,
                user_id=recipient_id,
                msg_type=msg_type,
                title=title,
                content=content,
                from_user_id=int(from_user_id) if from_user_id else None,
                related_id=int(related_id) if related_id else None,
                related_type=int(related_type) if related_type else None,
            )
            await db.commit()
            await db.refresh(msg)
            # ID映射：mq_message_id(=outbox event_id) -> message.id(DB自增)
            logger.info(
                "通知已落库 message_id=%s mq_message_id=%s recipient_id=%s db_elapsed_ms=%d",
                msg.id,
                message.message_id,
                recipient_id,
                (time.monotonic() - started_at) * 1000,
            )

            # 2. 复用 service 转换逻辑构造消息体，保证 SSE 与 REST 响应字段完全一致
            message_response = (await notification_service.to_responses(db, [msg]))[0]

            # 3. 查询未读总数
            unread_total = await message_repository.get_unread_count(db, recipient_id)

        # 4. 封装 SSE 事件（消息体按 alias 序列化，与 REST 响应字段完全一致）
        sse_event = {
            "kind": "message",
            "message": message_response.model_dump(mode="json", by_alias=True),
            "unread_total": unread_total,
        }

        # 5. Redis Pub/Sub 广播（跨实例扇出）
        await notification_service.publish_to_user(recipient_id, sse_event)

        logger.info(
            "通知已投递 message_id=%s mq_message_id=%s recipient_id=%s type=%s unread_total=%s total_elapsed_ms=%d",
            msg.id,
            message.message_id,
            recipient_id,
            msg_type,
            unread_total,
            (time.monotonic() - started_at) * 1000,
        )
