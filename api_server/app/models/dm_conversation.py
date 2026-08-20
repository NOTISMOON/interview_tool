"""私信会话表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DmConversation(Base):
    """私信会话ORM模型，映射 dm_conversation 表。"""

    __tablename__ = "dm_conversation"
    __table_args__ = (
        Index("uk_user_pair", "user1_id", "user2_id", unique=True),
        Index("idx_user2", "user2_id", "last_message_at"),
        Index("idx_user1_last", "user1_id", "last_message_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user1_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="较小用户ID")
    user2_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="另一用户ID")
    last_message: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="最后一条消息摘要")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最后消息时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )