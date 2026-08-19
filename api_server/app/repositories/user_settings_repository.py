"""用户设置数据访问层（同步），封装 user_settings 表操作。"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.user_settings import UserSettings


class UserSettingsRepository:
    """用户设置数据访问层，负责user_settings表的CRUD（同步）。"""

    def get_by_user_id(self, db: Session, user_id: int) -> UserSettings | None:
        """根据用户ID查询设置，不存在返回None。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。

        Returns:
            UserSettings对象，不存在返回None。
        """
        stmt = select(UserSettings).where(UserSettings.user_id == user_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_or_create(self, db: Session, user_id: int) -> UserSettings:
        """获取或创建用户设置（保障每个用户必有设置记录）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。

        Returns:
            UserSettings对象。
        """
        settings = self.get_by_user_id(db, user_id)
        if settings is None:
            settings = UserSettings(user_id=user_id)
            db.add(settings)
            db.flush()
        return settings

    def update(self, db: Session, user_id: int, update_data: dict) -> None:
        """更新用户设置字段（仅更新update_data中提交的字段）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。
            update_data: 待更新字段字典。
        """
        db.execute(
            update(UserSettings).where(UserSettings.user_id == user_id).values(**update_data)
        )


user_settings_repository = UserSettingsRepository()