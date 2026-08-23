"""私信数据访问层（异步，Agent 业务）。

供流消费端批量落库 Worker 使用：
    - batch_insert_messages：批量 INSERT dm_message，用 client_msg_id 唯一索引做幂等
      （INSERT IGNORE 冲突自动跳过，不重复落库）。
    - update_conversation_tail：批量/单条更新 dm_conversation 的最后消息摘要。
    - insert_outbox：与消息落库同一异步事务写入 chat.message.sent Outbox 事件。
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dm_conversation import DmConversation
from app.models.dm_message import DmMessage
from app.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)

# 内容类型常量（与 schemas/chat.py 保持一致）
CONTENT_TYPE_TEXT = 1

# 会话摘要截断长度（与 dm_conversation.last_message 列宽对齐）
_CONVERSATION_PREVIEW_LEN = 490


class ChatRepository:
    """私信数据访问层（异步），封装批量落库与 Outbox 事件写入。"""

    async def batch_insert_messages(
        self,
        db: AsyncSession,
        messages: list[dict[str, Any]],
    ) -> int:
        """批量插入私信消息（INSERT IGNORE 幂等去重）。

        使用 dm_message.client_msg_id 唯一索引：重复消费重投时 INSERT IGNORE
        自动跳过冲突行，天然 at-least-once + 幂等消化。

        Args:
            db: 数据库异步会话。
            messages: 待插入消息字典列表，每项含
                conversation_id/from_user_id/receiver_id/client_msg_id/content_type/content/seq。

        Returns:
            实际插入的消息条数。

        Raises:
            Exception: 数据库写入失败时抛出。
        """
        insert_sql = text(
            "INSERT IGNORE INTO dm_message "
            "(conversation_id, from_user_id, receiver_id, client_msg_id, content_type, content, seq, is_read) "
            "VALUES (:conversation_id, :from_user_id, :receiver_id, :client_msg_id, :content_type, "
            ":content, :seq, 0)"
        )
        for msg in messages:
            await db.execute(
                insert_sql,
                {
                    "conversation_id": msg["conversation_id"],
                    "from_user_id": msg["from_user_id"],
                    "receiver_id": msg["receiver_id"],
                    "client_msg_id": msg["client_msg_id"],
                    "content_type": msg.get("content_type", CONTENT_TYPE_TEXT),
                    "content": msg["content"],
                    "seq": msg["seq"],
                },
            )
        return len(messages)

    async def update_conversation_tail(
        self,
        db: AsyncSession,
        conversation_id: int,
        preview: str,
        last_message_id: int,
    ) -> None:
        """更新会话的最后消息摘要与最后消息时间（时间用 DB 当前时间兜底）。

        会话由最后消息驱动排序；last_message_id 由消息自增ID回填。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。
            preview: 最后一条消息摘要。
            last_message_id: 最后一条消息ID（dm_message.id）。
        """
        await db.execute(
            text(
                "UPDATE dm_conversation SET last_message = :preview, last_message_id = :lid, "
                "last_message_at = CURRENT_TIMESTAMP WHERE id = :cid"
            ),
            {"preview": preview[: _CONVERSATION_PREVIEW_LEN], "lid": last_message_id, "cid": conversation_id},
        )

    async def insert_outbox(
        self,
        db: AsyncSession,
        conversation_id: int,
        from_user_id: int,
        receiver_id: int,
        client_msg_id: str,
        seq: int,
    ) -> None:
        """在消息落库的同一事务内写入 chat.message.sent Outbox 事件。

        事件必须与业务写入同事务提交，保证「消息落库成功」与「扇出触发」原子，
        避免消息已存但扇出丢失或反之。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。
            from_user_id: 发送方。
            receiver_id: 接收方。
            client_msg_id: 消息幂等键。
            seq: 消息序号。
        """
        event = OutboxEvent(
            event_type="chat.message.sent",
            aggregate_type="chat",
            aggregate_id=str(conversation_id),
            payload={
                "conversation_id": conversation_id,
                "from_user_id": from_user_id,
                "receiver_id": receiver_id,
                "client_msg_id": client_msg_id,
                "seq": seq,
            },
        )
        db.add(event)

    # ------------------------------------------------------------------
    # 读路径（M3）
    # ------------------------------------------------------------------

    async def list_conversations(self, db: AsyncSession, user_id: int) -> list[DmConversation]:
        """查询当前用户的所有会话（按最后消息时间倒序）。

        会话为双向数据，user_id 可能落在 user1_id 或 user2_id。

        Args:
            db: 数据库异步会话。
            user_id: 当前用户ID。

        Returns:
            会话列表（按 last_message_at DESC 排序）。
        """
        result = await db.execute(
            text(
                "SELECT * FROM dm_conversation WHERE user1_id = :uid OR user2_id = :uid "
                "ORDER BY COALESCE(last_message_at, updated_at) DESC LIMIT 50"
            ),
            {"uid": user_id},
        )
        rows = result.mappings().all()
        return [DmConversation(**dict(row)) for row in rows]

    async def get_conversation(
        self, db: AsyncSession, conversation_id: int, user_id: int
    ) -> DmConversation | None:
        """按ID查询会话（校验当前用户为会话成员之一，防越权）。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。
            user_id: 当前用户ID。

        Returns:
            会话对象；不存在或非成员时返回 None。
        """
        stmt = text(
            "SELECT * FROM dm_conversation WHERE id = :cid AND (user1_id = :uid OR user2_id = :uid)"
        )
        result = await db.execute(stmt, {"cid": conversation_id, "uid": user_id})
        row = result.mappings().first()
        return DmConversation(**dict(row)) if row else None

    async def get_or_create_conversation(
        self, db: AsyncSession, user_id: int, other_id: int
    ) -> DmConversation:
        """获取或创建与另一用户的会话（user1<user2 规范化，防并发重复创建）。

        Args:
            db: 数据库异步会话。
            user_id: 当前用户ID。
            other_id: 对方用户ID。

        Returns:
            会话对象（新建则含已 flush 的 ID）。
        """
        u1, u2 = sorted([user_id, other_id])
        stmt = text(
            "SELECT * FROM dm_conversation WHERE user1_id = :u1 AND user2_id = :u2"
        )
        result = await db.execute(stmt, {"u1": u1, "u2": u2})
        row = result.mappings().first()
        if row:
            return DmConversation(**dict(row))
        conv = DmConversation(user1_id=u1, user2_id=u2)
        db.add(conv)
        # flush 触发 INSERT，autoincrement 主键回填到 ORM 实例（无需 refresh，
        # 避免 async engine 下 refresh 触发 pre_ping 的 Greenlet 异常）
        await db.flush()
        return conv

    async def list_messages(
        self, db: AsyncSession, conversation_id: int, cursor: int, size: int
    ) -> list[DmMessage]:
        """按游标分页查询会话消息（按 seq DESC，最新在前）。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。
            cursor: 上一页最后一条消息的 seq，首页传 0（或超大值取最新）。
            size: 每页条数（clamp 到 [1,50]）。

        Returns:
            消息列表（按 seq DESC）。
        """
        effective = max(1, min(size, 50))
        # cursor<=0 表示取最新一页；否则取 seq < cursor 的历史页
        sql = (
            "SELECT * FROM dm_message WHERE conversation_id = :cid "
            "AND (:cur <= 0 OR seq < :cur) ORDER BY seq DESC LIMIT :sz"
        )
        result = await db.execute(
            text(sql),
            {"cid": conversation_id, "cur": cursor, "sz": effective},
        )
        return [DmMessage(**dict(row)) for row in result.mappings().all()]

    async def mark_conversation_read(self, db: AsyncSession, conversation_id: int, user_id: int) -> int:
        """将会话中发给当前用户（receiver_id=user_id）的未读消息标记为已读。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。
            user_id: 当前用户ID。

        Returns:
            被标记为已读的消息数量。
        """
        result = await db.execute(
            text(
                "UPDATE dm_message SET is_read = 1 WHERE conversation_id = :cid "
                "AND receiver_id = :uid AND is_read = 0"
            ),
            {"cid": conversation_id, "uid": user_id},
        )
        return result.rowcount or 0

    async def count_conversation_unread(
        self, db: AsyncSession, conversation_id: int, user_id: int
    ) -> int:
        """统计会话中发给当前用户的未读消息数（DB 兜底）。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。
            user_id: 当前用户ID（接收方）。

        Returns:
            未读消息数量。
        """
        result = await db.execute(
            text(
                "SELECT COUNT(*) FROM dm_message WHERE conversation_id = :cid "
                "AND receiver_id = :uid AND is_read = 0"
            ),
            {"cid": conversation_id, "uid": user_id},
        )
        return int(result.scalar() or 0)

    async def get_conversation_by_pair(
        self, db: AsyncSession, user_id: int, other_id: int
    ) -> DmConversation | None:
        """按用户对（规范化）查询会话，返回 DmConversation 或 None。

        Args:
            db: 数据库异步会话。
            user_id: 当前用户ID。
            other_id: 对方用户ID。

        Returns:
            会话对象；不存在时返回 None。
        """
        u1, u2 = sorted([user_id, other_id])
        result = await db.execute(
            text("SELECT * FROM dm_conversation WHERE user1_id = :u1 AND user2_id = :u2"),
            {"u1": u1, "u2": u2},
        )
        row = result.mappings().first()
        return DmConversation(**dict(row)) if row else None


chat_repository = ChatRepository()