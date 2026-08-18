"""用户认证方式表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserAuth(Base):
    """用户认证方式ORM模型，映射 user_auth 表（provider: 1-邮箱 2-GitHub 3-QQ 4-微信）。"""

    __tablename__ = "user_auth"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="关联user表")
    provider: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-邮箱 2-GitHub 3-QQ(预留) 4-微信(预留)")
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="第三方平台用户唯一标识")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="绑定时间"
    )
