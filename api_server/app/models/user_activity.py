"""用户动态表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 动态类型常量：1-点赞 2-评论 3-关注 4-发帖
ACTIVITY_TYPE_FOLLOW = 3


class UserActivity(Base):
    """用户动态ORM模型，映射 user_activity 表。

    索引设计:
        - idx_user_created(user_id, created_at DESC): 个人主页动态列表按时间倒序
    """

    __tablename__ = "user_activity"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="产生动态的用户")
    type: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-点赞 2-评论 3-关注 4-发帖")
    content: Mapped[str] = mapped_column(String(512), nullable=False, comment="动态描述")
    related_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="关联实体 ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
