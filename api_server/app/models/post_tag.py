"""帖子标签关联表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostTag(Base):
    """帖子标签关联ORM模型，映射 post_tag 表。

    索引设计（DB层）:
        - PRIMARY KEY(id): 主键
        - uk_post_tag(post_id, tag): 唯一索引，同一帖子不重复打同一标签
        - idx_tag(tag, created_at DESC): 按标签筛选帖子，按时间倒序
    """

    __tablename__ = "post_tag"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="帖子ID")
    tag: Mapped[str] = mapped_column(String(32), nullable=False, comment="标签名")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )