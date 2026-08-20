"""帖子收藏表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostFavorite(Base):
    """帖子收藏ORM模型，映射 post_favorite 表。

    索引设计（DB层）:
        - PRIMARY KEY(id): 主键
        - uk_post_user(post_id, user_id): 唯一索引，防止重复收藏
        - idx_user_id(user_id, created_at DESC): 用户收藏列表按时间倒序
    """

    __tablename__ = "post_favorite"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="帖子ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="收藏用户ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="收藏时间"
    )