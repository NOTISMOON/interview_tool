"""帖子点赞表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostLike(Base):
    """帖子点赞ORM模型，映射 post_like 表。

    索引设计（DB层）:
        - PRIMARY KEY(id): 主键
        - uk_post_user(post_id, user_id): 唯一索引，防止重复点赞 + 查帖子点赞列表
        - idx_user_id(user_id): 查某用户点赞过的帖子
    """

    __tablename__ = "post_like"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="帖子ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="点赞用户ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="点赞时间"
    )