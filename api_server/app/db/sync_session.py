"""数据库同步会话管理模块。

提供同步数据库会话的创建与依赖注入，适用于普通业务（增删改查、简单查询）。
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.MYSQL_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db() -> Generator[Session, None, None]:
    """获取数据库同步会话（依赖注入用）。

    每次请求创建一个新的会话，请求结束后自动关闭。

    Yields:
        SQLAlchemy 同步会话对象。
    """
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()