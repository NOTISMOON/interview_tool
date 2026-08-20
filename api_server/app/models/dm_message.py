"""私信消息表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DmMessage(Base):
    """私信消息ORM模型，映射 dm_message 表。"""

    __tablename__ = "dm_message"
    __table_args__ = (
        Index("idx_conversation_created", "conversation_id", "created_at"),
        Index("idx_conversation_unread", "conversation_id", "is_read", "created_at"),
        Index("idx_from_user", "from_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关联会话ID")
    from_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="发送者用户ID")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    is_read: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="0-未读 1-已读"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="发送时间"
    )