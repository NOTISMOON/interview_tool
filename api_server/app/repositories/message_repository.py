"""消息通知数据访问层。

包含两个类:
    - SyncMessageRepository: 同步实现，供写路径（通知写入，与业务操作同事务）使用。
    - MessageRepository: 异步实现，供 NotificationConsumer 和 SSE 连接补偿查询使用。
"""

import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.message import MESSAGE_TYPE_SYSTEM, Message

logger = logging.getLogger(__name__)


class SyncMessageRepository:
    """消息通知数据访问层（同步），写路径与业务操作同事务保证原子性。"""

    def create(
        self,
        db: Session,
        user_id: int,
        msg_type: int,
        title: str,
        content: str,
        from_user_id: int | None = None,
        related_id: int | None = None,
        related_type: int | None = None,
    ) -> Message:
        """创建一条消息通知（在当前事务内）。

        Args:
            db: 数据库同步会话（必须与业务操作同一会话）。
            user_id: 消息接收者用户ID。
            msg_type: 消息类型（1-系统 2-评论 3-点赞 4-关注 5-面试 6-私信）。
            title: 消息标题。
            content: 消息内容。
            from_user_id: 消息触发者用户ID（系统消息为空）。
            related_id: 关联实体ID。
            related_type: 关联实体类型（1-帖子 2-报告 3-用户）。

        Returns:
            创建的Message对象（含自增ID）。
        """
        message = Message(
            user_id=user_id,
            type=msg_type,
            title=title,
            content=content,
            from_user_id=from_user_id,
            related_id=related_id,
            related_type=related_type,
        )
        db.add(message)
        db.flush()
        return message

    def get_unread_count(self, db: Session, user_id: int) -> int:
        """获取用户未读消息总数。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。

        Returns:
            未读消息数量。
        """
        stmt = select(func.count()).where(Message.user_id == user_id, Message.is_read == 0)
        result = db.execute(stmt)
        return result.scalar_one() or 0

    def get_unread_count_by_type(self, db: Session, user_id: int) -> dict[int, int]:
        """获取用户按类型分组的未读消息数量。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。

        Returns:
            类型ID -> 未读数量的映射字典。
        """
        stmt = (
            select(Message.type, func.count())
            .where(Message.user_id == user_id, Message.is_read == 0)
            .group_by(Message.type)
        )
        rows = db.execute(stmt).all()
        return {row[0]: row[1] for row in rows}

    def mark_all_read(self, db: Session, user_id: int) -> int:
        """将用户所有未读消息标记为已读。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。

        Returns:
            被标记为已读的消息数量。
        """
        now = datetime.now()
        result = db.execute(
            update(Message)
            .where(Message.user_id == user_id, Message.is_read == 0)
            .values(is_read=1, read_at=now)
        )
        return result.rowcount or 0


class MessageRepository:
    """消息通知数据访问层（异步），供Consumer和SSE补偿查询使用。"""

    async def create(
        self,
        db: AsyncSession,
        user_id: int,
        msg_type: int,
        title: str,
        content: str,
        from_user_id: int | None = None,
        related_id: int | None = None,
        related_type: int | None = None,
    ) -> Message:
        """异步创建一条消息通知。

        Args:
            db: 数据库异步会话。
            user_id: 消息接收者用户ID。
            msg_type: 消息类型。
            title: 消息标题。
            content: 消息内容。
            from_user_id: 消息触发者用户ID。
            related_id: 关联实体ID。
            related_type: 关联实体类型。

        Returns:
            创建的Message对象（含自增ID）。
        """
        message = Message(
            user_id=user_id,
            type=msg_type,
            title=title,
            content=content,
            from_user_id=from_user_id,
            related_id=related_id,
            related_type=related_type,
        )
        db.add(message)
        await db.flush()
        return message

    async def get_unread_count(self, db: AsyncSession, user_id: int) -> int:
        """异步获取用户未读消息总数。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。

        Returns:
            未读消息数量。
        """
        stmt = select(func.count()).where(Message.user_id == user_id, Message.is_read == 0)
        result = await db.execute(stmt)
        return result.scalar_one() or 0

    async def get_unread_count_by_type(self, db: AsyncSession, user_id: int) -> dict[int, int]:
        """异步获取用户按类型分组的未读消息数量。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。

        Returns:
            类型ID -> 未读数量的映射字典。
        """
        stmt = (
            select(Message.type, func.count())
            .where(Message.user_id == user_id, Message.is_read == 0)
            .group_by(Message.type)
        )
        rows = (await db.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}

    async def get_by_id(self, db: AsyncSession, user_id: int, message_id: int) -> Message | None:
        """按ID查询单条消息（防越权：仅返回属于该用户的消息）。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            message_id: 消息ID。

        Returns:
            Message对象，不存在或不属于该用户时返回None。
        """
        stmt = select(Message).where(Message.id == message_id, Message.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_since_id(
        self, db: AsyncSession, user_id: int, since_id: int | None, limit: int = 10
    ) -> Sequence[Message]:
        """增量查询消息：返回 id > since_id 的最新消息（最多 limit 条）。

        用于 SSE 建立/重连补偿和前端轮询降级。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            since_id: 增量起点，NULL 表示首次访问（拉最新 limit 条）。
            limit: 返回条数上限，服务端强制 clamp 到 [1, 10]。

        Returns:
            消息列表，按 id DESC 排序（最新在前）。
        """
        effective_limit = max(1, min(limit, 10))
        stmt = select(Message).where(Message.user_id == user_id)
        if since_id is not None:
            stmt = stmt.where(Message.id > since_id)
        stmt = stmt.order_by(desc(Message.id)).limit(effective_limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_by_cursor(
        self, db: AsyncSession, user_id: int, cursor: int = 0, size: int = 20, msg_type: int | None = None
    ) -> Sequence[Message]:
        """历史翻页查询：按游标分页获取消息列表。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。
            cursor: 上一页最后一条消息的ID，首页传0。
            size: 每页条数，clamp 到 [1, 50]。
            msg_type: 按类型过滤，None 表示全部。

        Returns:
            消息列表，按 id DESC 排序。
        """
        effective_size = max(1, min(size, 50))
        stmt = select(Message).where(Message.user_id == user_id)
        if cursor > 0:
            stmt = stmt.where(Message.id < cursor)
        if msg_type is not None:
            stmt = stmt.where(Message.type == msg_type)
        stmt = stmt.order_by(desc(Message.id)).limit(effective_size)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def mark_read(self, db: AsyncSession, user_id: int, message_id: int) -> bool:
        """将单条消息标记为已读。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID（防越权：只标记自己的消息）。
            message_id: 消息ID。

        Returns:
            是否成功标记（消息不存在或已读返回False）。
        """
        now = datetime.now()
        result = await db.execute(
            update(Message)
            .where(Message.id == message_id, Message.user_id == user_id, Message.is_read == 0)
            .values(is_read=1, read_at=now)
        )
        await db.commit()
        return result.rowcount > 0

    async def mark_all_read(self, db: AsyncSession, user_id: int) -> int:
        """将用户所有未读消息标记为已读。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID。

        Returns:
            被标记为已读的消息数量。
        """
        now = datetime.now()
        result = await db.execute(
            update(Message)
            .where(Message.user_id == user_id, Message.is_read == 0)
            .values(is_read=1, read_at=now)
        )
        await db.commit()
        return result.rowcount or 0

    async def delete(self, db: AsyncSession, user_id: int, message_id: int) -> bool:
        """删除单条消息（物理删除）。

        Args:
            db: 数据库异步会话。
            user_id: 用户ID（防越权）。
            message_id: 消息ID。

        Returns:
            是否成功删除。
        """
        from sqlalchemy import delete

        result = await db.execute(
            delete(Message).where(Message.id == message_id, Message.user_id == user_id)
        )
        await db.commit()
        return result.rowcount > 0


sync_message_repository = SyncMessageRepository()
message_repository = MessageRepository()