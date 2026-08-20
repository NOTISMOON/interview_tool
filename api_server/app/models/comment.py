"""社区评论表ORM模型（类抖音扁平模型）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 评论状态常量
COMMENT_STATUS_DELETED = 0
COMMENT_STATUS_NORMAL = 1


class Comment(Base):
    """评论ORM模型，映射 comment 表。

    数据库层面不区分"评论"和"回复"，都是 comment 记录。
    区别只在于 root_id 和 reply_user_id：
        - 一级评论: root_id IS NULL, reply_user_id IS NULL
        - 回复:     root_id = 一级评论ID, reply_user_id = 被回复者ID

    索引设计（DB层）:
        - PRIMARY KEY(id): 主键
        - idx_post_root(post_id, root_id, created_at): 帖子评论列表 + 回复列表
        - idx_author_id(author_id): 查某用户的评论
        - idx_root_created(root_id, created_at): 某条一级评论的回复列表
    """

    __tablename__ = "comment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属帖子ID")
    root_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="根评论ID（NULL=一级评论；非NULL=属于该根评论的回复线程）"
    )
    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="评论者ID")
    reply_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="被回复者ID（NULL=一级评论；非NULL=前端展示'回复 @xxx'）"
    )
    content: Mapped[str] = mapped_column(String(1000), nullable=False, comment="评论内容")
    likes_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="点赞数"
    )
    reply_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="回复数（仅 root_id IS NULL 的一级评论维护，冗余计数）",
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
        comment="编辑时间",
    )