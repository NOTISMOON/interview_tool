"""帖子点赞表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostLike(Base):
    """帖子点赞ORM模型，映射 post_like 表。

    索引说明: 当前 ORM 未定义二级索引（历史迁移 f15581dc7487 已删除
        uk_post_user/idx_user_id，防重复点赞由服务层捕获 IntegrityError 保证，
        如需请经 DDL 补充）。主键 id 自增。
    """

    __tablename__ = "post_like"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="帖子ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="点赞用户ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="点赞时间"
    )