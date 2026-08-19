"""通知业务逻辑层。

负责消息通知的创建、查询、标记已读、删除等业务编排。
写路径通过 Transactional Outbox 保证一致性；读路径支持增量查询与历史翻页。
"""

import json
import logging
import time
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.message import (
    MESSAGE_TYPE_COMMENT,
    MESSAGE_TYPE_DM,
    MESSAGE_TYPE_FOLLOW,
    MESSAGE_TYPE_INTERVIEW,
    MESSAGE_TYPE_LIKE,
    MESSAGE_TYPE_SYSTEM,
    Message,
)
from app.redis.async_client import AsyncRedisClient
from app.repositories.message_repository import message_repository, sync_message_repository
from app.schemas.message import FromUserInfo, MessageListResponse, MessageResponse, RelatedInfo, UnreadCountResponse

logger = logging.getLogger(__name__)

# 消息类型 -> 类型名称映射
TYPE_NAME_MAP: dict[int, str] = {
    MESSAGE_TYPE_SYSTEM: "system",
    MESSAGE_TYPE_COMMENT: "comment",
    MESSAGE_TYPE_LIKE: "like",
    MESSAGE_TYPE_FOLLOW: "follow",
    MESSAGE_TYPE_INTERVIEW: "interview",
    MESSAGE_TYPE_DM: "dm",
}

# 关联实体类型 -> 类型名称映射
RELATED_TYPE_NAME_MAP: dict[int, str] = {
    1: "post",
    2: "report",
    3: "user",
}


class NotificationService:
    """通知业务逻辑层（异步），编排消息的创建、查询、标记已读与删除。"""

    # ------------------------------------------------------------------
    # 写路径（同步，与业务操作同事务）
    # ------------------------------------------------------------------

    def create_notification(
        self,
        db: Session,
        recipient_id: int,
        msg_type: int,
        title: str,
        content: str,
        from_user_id: int | None = None,
        related_id: int | None = None,
        related_type: int | None = None,
    ) -> Message:
        """在业务事务内创建通知消息（同步，与业务操作同Session）。

        Args:
            db: 数据库同步会话（必须与业务操作共用）。
            recipient_id: 消息接收者用户ID。
            msg_type: 消息类型。
            title: 消息标题。
            content: 消息内容。
            from_user_id: 消息触发者用户ID。
            related_id: 关联实体ID。
            related_type: 关联实体类型。

        Returns:
            创建的Message对象（含自增ID）。
        """
        return sync_message_repository.create(
            db,
            user_id=recipient_id,
            msg_type=msg_type,
            title=title,
            content=content,
            from_user_id=from_user_id,
            related_id=related_id,
            related_type=related_type,
        )

    def get_unread_count_sync(self, db: Session, user_id: int) -> int:
        """同步获取用户未读消息总数。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。

        Returns:
            未读消息数量。
        """
        return sync_message_repository.get_unread_count(db, user_id)

    # ------------------------------------------------------------------
    # 读路径（异步，供SSE和REST接口使用）
    # ------------------------------------------------------------------

    async def get_list_since_id(
        self, db: AsyncSession, user_id: int, since_id: int | None, limit: int = 10
    ) -> MessageListResponse:
        """增量查询消息列表（since_id 模式）。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            since_id: 增量起点，NULL 表示首次访问。
            limit: 返回条数上限（服务端强制 clamp 到 [1, 10]）。

        Returns:
            MessageListResponse: 含消息列表与未读总数。
        """
        messages = await message_repository.get_since_id(db, user_id, since_id, limit)
        unread_total = await message_repository.get_unread_count(db, user_id)
        items = await self.to_responses(db, messages)
        return MessageListResponse(items=items, unread_total=unread_total)

    async def get_list_cursor(
        self, db: AsyncSession, user_id: int, cursor: int = 0, size: int = 20, msg_type: int | None = None
    ) -> MessageListResponse:
        """历史翻页查询消息列表（cursor 模式）。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            cursor: 上一页最后一条消息ID，首页传0。
            size: 每页条数。
            msg_type: 按类型过滤。

        Returns:
            MessageListResponse: 含消息列表、下一页游标与未读总数。
        """
        messages = await message_repository.get_by_cursor(db, user_id, cursor, size, msg_type)
        unread_total = await message_repository.get_unread_count(db, user_id)

        next_cursor = None
        if messages:
            next_cursor = messages[-1].id

        items = await self.to_responses(db, messages)
        return MessageListResponse(items=items, next_cursor=next_cursor, unread_total=unread_total)

    async def get_unread_count(self, db: AsyncSession, user_id: int) -> UnreadCountResponse:
        """获取用户未读计数（含分类汇总）。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。

        Returns:
            UnreadCountResponse: 含总数与分类汇总。
        """
        total = await message_repository.get_unread_count(db, user_id)
        by_type_raw = await message_repository.get_unread_count_by_type(db, user_id)
        by_type = {TYPE_NAME_MAP.get(k, str(k)): v for k, v in by_type_raw.items()}
        return UnreadCountResponse(total=total, by_type=by_type)

    async def get_message(self, db: AsyncSession, user_id: int, message_id: int) -> Message | None:
        """查询单条消息（防越权校验归属）。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            message_id: 消息ID。

        Returns:
            Message对象，不存在或不属于该用户返回None。
        """
        return await message_repository.get_by_id(db, user_id, message_id)

    async def get_message_detail(self, db: AsyncSession, user_id: int, message_id: int) -> MessageResponse | None:
        """查询单条消息详情，未读时顺带标记已读（幂等）。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            message_id: 消息ID。

        Returns:
            MessageResponse: 消息详情；消息不存在或不属于该用户返回None。
        """
        message = await message_repository.get_by_id(db, user_id, message_id)
        if message is None:
            return None

        if not message.is_read:
            await message_repository.mark_read(db, user_id, message_id)
            # mark_read 内部已 commit，重新加载以获取最新已读状态
            message = await message_repository.get_by_id(db, user_id, message_id)
            if message is None:
                return None

        return (await self.to_responses(db, [message]))[0]

    async def mark_read(self, db: AsyncSession, user_id: int, message_id: int) -> bool:
        """标记单条消息为已读。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            message_id: 消息ID。

        Returns:
            是否成功标记。
        """
        return await message_repository.mark_read(db, user_id, message_id)

    async def mark_all_read(self, db: AsyncSession, user_id: int) -> int:
        """标记所有消息为已读。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。

        Returns:
            被标记为已读的消息数量。
        """
        return await message_repository.mark_all_read(db, user_id)

    async def delete_message(self, db: AsyncSession, user_id: int, message_id: int) -> bool:
        """删除单条消息。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            message_id: 消息ID。

        Returns:
            是否成功删除。
        """
        return await message_repository.delete(db, user_id, message_id)

    # ------------------------------------------------------------------
    # Pub/Sub 推送
    # ------------------------------------------------------------------

    async def publish_to_user(self, user_id: int, event_data: dict) -> None:
        """通过 Redis Pub/Sub 向指定用户推送 SSE 事件。

        日志埋点:
            - publish 返回 receivers（接收到本消息的实例订阅数），
              receivers=0 意味着没有任何 API 实例在监听推送通道（SSE 监听全部异常），
              置 WARNING 便于发现监听集体失效；消息本身不丢失，用户重连后走补偿拉取。
            - event_kind/message_id 与消费端日志串联。

        Args:
            user_id: 目标用户ID。
            event_data: 事件数据字典（含 kind、message 等字段）。
        """
        started_at = time.monotonic()
        channel = f"{settings.NOTIFY_PUSH_CHANNEL_PREFIX}:{user_id}"
        # 提取轻量上下文（不序列化整个消息体，避免日志膨胀）
        event_kind = event_data.get("kind") if isinstance(event_data, dict) else None
        message_id = None
        if isinstance(event_data, dict) and isinstance(event_data.get("message"), dict):
            message_id = event_data["message"].get("id")
        try:
            redis_client = await AsyncRedisClient.get_client()
            receivers = await redis_client.publish(
                channel, json.dumps(event_data, ensure_ascii=False, default=str)
            )
            if receivers == 0:
                logger.warning(
                    "SSE推送无实例接收（监听可能全部失效）user_id=%s channel=%s event_kind=%s message_id=%s",
                    user_id,
                    channel,
                    event_kind,
                    message_id,
                )
            else:
                logger.info(
                    "SSE推送已发布 user_id=%s channel=%s event_kind=%s message_id=%s receivers=%s elapsed_ms=%d",
                    user_id,
                    channel,
                    event_kind,
                    message_id,
                    receivers,
                    (time.monotonic() - started_at) * 1000,
                )
        except Exception:
            # 发布失败不阻断业务（通知已落库，用户重连时补偿拉取可取回）
            logger.exception(
                "SSE推送发布失败 user_id=%s channel=%s event_kind=%s message_id=%s",
                user_id,
                channel,
                event_kind,
                message_id,
            )

    async def publish_broadcast(self, event_data: dict) -> None:
        """通过 Redis Pub/Sub 广播系统消息。

        Args:
            event_data: 广播事件数据字典。
        """
        started_at = time.monotonic()
        channel = settings.NOTIFY_BROADCAST_CHANNEL
        try:
            redis_client = await AsyncRedisClient.get_client()
            receivers = await redis_client.publish(
                channel, json.dumps(event_data, ensure_ascii=False, default=str)
            )
            level = logger.warning if receivers == 0 else logger.info
            level(
                "SSE广播已发布 channel=%s receivers=%s elapsed_ms=%d",
                channel,
                receivers,
                (time.monotonic() - started_at) * 1000,
            )
        except Exception:
            logger.exception("SSE广播发布失败 channel=%s", channel)

    # ------------------------------------------------------------------
    # 消息 -> 响应模型转换
    # ------------------------------------------------------------------

    async def to_responses(self, db: AsyncSession, messages: Sequence[Message]) -> list[MessageResponse]:
        """将消息列表转换为响应模型（含发送者信息）。

        公开方法：REST 接口与 NotificationConsumer 共用，保证 SSE 与 REST 字段完全一致。
        发送者信息通过 IN 单次批量查询获取，避免 N+1。

        Args:
            db: 数据库异步会话。
            messages: 消息ORM对象列表。

        Returns:
            MessageResponse 列表。
        """
        from app.repositories.user_repository import UserRepository

        user_repo = UserRepository()

        # 批量查询所有发送者（IN 单次查询，避免逐条 N+1）
        from_user_ids = list({m.from_user_id for m in messages if m.from_user_id})
        users = await user_repo.get_users_by_ids(db, from_user_ids) if from_user_ids else []
        user_map: dict[int, dict] = {
            u.id: {"id": u.id, "nickname": u.nickname, "avatar": u.avatar} for u in users
        }

        items = []
        for m in messages:
            from_user = None
            if m.from_user_id and m.from_user_id in user_map:
                u = user_map[m.from_user_id]
                from_user = FromUserInfo(id=u["id"], nickname=u["nickname"], avatar=u["avatar"])

            related = None
            if m.related_id is not None and m.related_type is not None:
                related = RelatedInfo(
                    id=m.related_id,
                    type=m.related_type,
                    type_name=RELATED_TYPE_NAME_MAP.get(m.related_type),
                )

            items.append(
                MessageResponse(
                    id=m.id,
                    type=m.type,
                    type_name=TYPE_NAME_MAP.get(m.type, str(m.type)),
                    title=m.title,
                    content=m.content,
                    from_user=from_user,
                    related=related,
                    created_at=m.created_at,
                    is_read=bool(m.is_read),
                )
            )

        return items


notification_service = NotificationService()