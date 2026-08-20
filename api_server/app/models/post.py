"""社区帖子表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 帖子状态常量
POST_STATUS_DELETED = 0
POST_STATUS_NORMAL = 1


class Post(Base):
    """帖子ORM模型，映射 post 表。

    索引设计（DB层）:
        - PRIMARY KEY(id): 主键
        - idx_author_id(author_id): 查某用户发的帖子
        - idx_status_pinned(status, is_pinned DESC, created_at DESC): 社区首页置顶优先
        - idx_status_hot(status, is_hot DESC, likes_count DESC): 热门排序
        - idx_created_at(status, created_at DESC): 最新排序
    """

    __tablename__ = "post"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="作者 ID")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="帖子标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="帖子正文")
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="标签列表（展示用冗余缓存）")
    likes_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="点赞数"
    )
    comments_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="评论数"
    )
    views_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="浏览数"
    )
    is_pinned: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="是否置顶 0-否 1-是"
    )
    is_hot: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="是否热门 0-否 1-是"
    )
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="0-删除 1-正常",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )