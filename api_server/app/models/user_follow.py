"""用户关注关系表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserFollow(Base):
    """用户关注关系ORM模型，映射 user_follow 表。

    索引说明: 当前 ORM 未定义二级索引（历史迁移 f15581dc7487 已删除
        uk_follower_following/idx_follower_created/idx_following_created，
        防重复关注由服务层保证，如需请经 DDL 补充）。
    """

    __tablename__ = "user_follow"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    follower_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关注者用户ID")
    following_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="被关注者用户ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="关注时间",
    )
