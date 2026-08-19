"""用户设置表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserSettings(Base):
    """用户设置ORM模型，映射 user_settings 表（与user一对一）。"""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, comment="用户ID")
    email_notify: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"), comment="邮件通知 0-关 1-开")
    push_notify: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"), comment="推送通知")
    sound_enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"), comment="声音提示")
    public_profile: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment="公开个人主页")
    visibility_gender: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), comment="性别可见 0-不可见 1-可见"
    )
    visibility_birthday: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), comment="生日可见 0-不可见 1-可见"
    )
    visibility_bio: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), comment="简介可见 0-不可见 1-可见"
    )
    visibility_location: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), comment="所在地可见 0-不可见 1-可见"
    )
    visibility_phone: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="手机号可见 0-不可见 1-可见"
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