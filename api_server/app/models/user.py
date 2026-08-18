"""用户表ORM模型。"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """用户ORM模型，映射 user 表。"""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, comment="邮箱（OAuth用户可能为空）"
    )
    nickname: Mapped[str] = mapped_column(String(64), nullable=False, comment="用户昵称")
    avatar: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="头像URL")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="仅邮箱注册用户有值")
    gender: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment="0-未设置 1-男 2-女")
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生日")
    bio: Mapped[str] = mapped_column(String(512), nullable=False, server_default=text(""), comment="个人简介")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="手机号")
    location: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="所在地")
    profile_visibility: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="资料可见性 0-公开 1-仅关注者 2-仅自己",
    )
    following_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment="关注数")
    followers_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment="粉丝数")
    posts_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment="发帖数")
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), comment="0-禁用 1-正常 2-注销"
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
