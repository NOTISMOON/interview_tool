"""数据库异步会话管理模块。

提供异步数据库会话的创建与依赖注入，适用于Agent业务（高并发、异步IO、多任务协作）。
"""

from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

async_engine = create_async_engine(
    settings.MYSQL_ASYNC_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={
        "ssl": False,  # aiomysql 在 Windows 上通过 caching_sha2_password 认证时需关闭 SSL
        "charset": "utf8mb4",
    },
)


@event.listens_for(async_engine.sync_engine, "connect")
def _set_async_session_timezone(dbapi_connection, connection_record) -> None:
    """连接建立时将会话时区设为北京时间（UTC+8）。

    与同步引擎保持一致，保证 CURRENT_TIMESTAMP 与 Python datetime.now()
    均按北京时间生成，避免前后端 8 小时偏差。

    Args:
        dbapi_connection: 原始 DBAPI 连接对象。
        connection_record: 连接池记录。
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET time_zone = '+08:00'")
    finally:
        cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    class_=AsyncSession,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库异步会话（依赖注入用）。

    每次请求创建一个新的异步会话，请求结束后自动关闭。

    Yields:
        SQLAlchemy 异步会话对象。
    """
    async with AsyncSessionLocal() as session:
        yield session