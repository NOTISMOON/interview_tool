"""API公共依赖模块，提供数据库会话、认证等依赖注入。"""

from typing import Generator


def get_db() -> Generator:
    """获取数据库同步会话（占位，待数据库会话管理实现后完善）。

    Yields:
        数据库会话对象。
    """
    pass