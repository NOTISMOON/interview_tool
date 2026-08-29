"""评论点赞ORM模型，记录用户对评论的点赞关系。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommentLike(Base):
    """评论点赞ORM模型，映射 comment_like 表。

    comment_id + user_id 唯一索引防止重复点赞。
    """

    __tablename__ = "comment_like"
    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="uk_comment_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="评论ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="点赞用户ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="点赞时间"
    )