"""用户关注关系表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserFollow(Base):
    """用户关注关系ORM模型，映射 user_follow 表。

    索引设计（对称覆盖两个方向的列表查询）:
        - uk_follower_following(follower_id, following_id): 唯一约束，防重复关注
        - idx_follower_created(follower_id, created_at DESC): 关注列表按时间查询
        - idx_following_created(following_id, created_at DESC): 粉丝列表按时间查询
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
