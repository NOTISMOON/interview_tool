"""帖子标签关联表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostTag(Base):
    """帖子标签关联ORM模型，映射 post_tag 表。

    索引说明: 当前 ORM 未定义二级索引（历史迁移 f15581dc7487 已删除
        uk_post_tag/idx_tag，如需请经 DDL 补充）。主键 id 自增。
    """

    __tablename__ = "post_tag"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="帖子ID")
    tag: Mapped[str] = mapped_column(String(32), nullable=False, comment="标签名")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )