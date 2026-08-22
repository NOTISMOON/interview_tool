"""简历表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RESUME_STATUS_PARSING = 0
RESUME_STATUS_READY = 1
RESUME_STATUS_ERROR = 2


class Resume(Base):
    """简历ORM模型，映射 resume 表。

    去重设计（见简历上传分析蓝图 §4.1/§3.2）:
        - file_hash 记录文件 SHA256，创建即非空（回调内先算好再插入），
          配合 uk_user_file_hash 唯一约束实现"同一用户同一文件仅一份"。
        - is_deleted/deleted_at 支持软删除；删除时将 file_hash 置空以释放唯一约束，
          允许"删除后重新上传同一文件"。
    """

    __tablename__ = "resume"
    __table_args__ = (
        Index("idx_user_id", "user_id"),
        Index("idx_user_status", "user_id", "status"),
        UniqueConstraint("user_id", "file_hash", name="uk_user_file_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="用户ID")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="文件存储地址")
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="文件大小(字节)")
    file_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="文件SHA256哈希，用于去重（软删除后置空）"
    )
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="0-解析中 1-就绪 2-错误"
    )
    parsed_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="解析出的姓名")
    parsed_skills: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="解析出的技能列表")
    parsed_education: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="解析出的教育经历数组"
    )
    parsed_projects: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="AI解析出的项目经历数组（含 name/description/tech_stack）"
    )
    error_message: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="解析失败原因"
    )
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="软删除标记 0-否 1-是",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="软删除时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )