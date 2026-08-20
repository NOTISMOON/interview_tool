"""Alembic环境配置，用于数据库迁移。"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 将项目根目录加入 sys.path，确保可以导入 app 模块
# env.py 位于 alembic/ 目录下，其父目录即 api_server 项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Alembic Config 对象
config = context.config

# 从应用配置中读取数据库URL，覆盖 alembic.ini 中的占位值
from app.core.config import settings

config.set_main_option("sqlalchemy.url", settings.MYSQL_URL)

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入所有模型的 metadata，用于 autogenerate 自动检测表结构变更
from app.db.base import Base
from app.models import (  # noqa: F401  # 确保所有模型被导入，Base.metadata 才能感知到
    Comment,
    DmConversation,
    DmMessage,
    Interview,
    InterviewQuestion,
    InterviewReport,
    Message,
    OutboxEvent,
    Post,
    PostFavorite,
    PostLike,
    PostTag,
    Resume,
    ResumeWorkExperience,
    UploadRecord,
    User,
    UserActivity,
    UserAuth,
    UserFollow,
    UserSettings,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式运行迁移（不连接数据库，生成SQL脚本）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式运行迁移（连接数据库，直接执行DDL）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()