"""数据库ORM基类模块。"""

from sqlalchemy import DeclarativeBase
class Base(DeclarativeBase):
    """SQLAlchemy ORM 声明式基类，所有模型继承此类。"""
    pass