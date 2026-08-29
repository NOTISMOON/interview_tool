"""数据库同步会话管理模块。

提供同步数据库会话的创建与依赖注入，适用于普通业务（增删改查、简单查询）。
"""

from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.MYSQL_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_sync_session_timezone(dbapi_connection, connection_record) -> None:
    """连接建立时将会话时区设为北京时间（UTC+8）。

    MySQL 服务器时区可能为 UTC，而业务统一按北京时间写入/读取
    （CURRENT_TIMESTAMP 由 MySQL 生成），必须设置会话时区保证一致。

    Args:
        dbapi_connection: 原始 DBAPI 连接对象。
        connection_record: 连接池记录。
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET time_zone = '+08:00'")
    finally:
        cursor.close()


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
