"""私信消息表ORM模型。

字段与《私信功能文档.md》保持一致：
- client_msg_id：客户端UUID幂等键，唯一索引兜底去重（at-least-once + 幂等消化）。
- receiver_id：接收方冗余，便于未读数/消息中心按接收方聚合查询。
- content_type：1=文本 2=图片 3=文件。
- seq：同会话内单调递增序号（写路径用 Redis Stream 消费时按序落库，保序）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DmMessage(Base):
    """私信消息ORM模型，映射 dm_message 表。"""

    __tablename__ = "dm_message"
    __table_args__ = (
        Index("idx_conversation_created", "conversation_id", "created_at"),
        Index("idx_conversation_unread", "conversation_id", "is_read", "created_at"),
        Index("idx_from_user", "from_user_id"),
        Index("idx_client_msg", "client_msg_id", unique=True),
        Index("idx_conversation_seq", "conversation_id", "seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关联会话ID")
    from_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="发送者用户ID")
    receiver_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="接收方用户ID（冗余）")
    client_msg_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="客户端UUID幂等键")
    content_type: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), comment="1-文本 2-图片 3-文件"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="同会话内自增序号")
    is_read: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="0-未读 1-已读"
    )
    deleted_by_user1: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="消息是否被 user1 删除 0-否 1-是"
    )
    deleted_by_user2: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="消息是否被 user2 删除 0-否 1-是"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="发送时间"
    )