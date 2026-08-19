"""文件上传记录表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 上传状态常量
UPLOAD_STATUS_PENDING = "pending"
UPLOAD_STATUS_COMPLETED = "completed"
UPLOAD_STATUS_FAILED = "failed"

# 文件用途常量
FILE_TYPE_RESUME = "resume"
FILE_TYPE_AVATAR = "avatar"


class UploadRecord(Base):
    """文件上传记录ORM模型，映射 upload_records 表。

    索引设计:
        - idx_user_id(user_id): 按用户查询上传记录
        - idx_user_type(user_id, file_type): 按用户+用途筛选（我的简历列表）
        - idx_status(status): 按状态筛选（后续异步处理扫描）
        - idx_created_at(created_at): 按时间排序
    """

    __tablename__ = "upload_records"
    __table_args__ = (
        Index("idx_user_id", "user_id"),
        Index("idx_user_type", "user_id", "file_type"),
        Index("idx_status", "status"),
        Index("idx_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="上传用户ID")
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="文件用途：resume/avatar")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小（字节）")
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, comment="MIME类型")
    cos_key: Mapped[str] = mapped_column(String(500), nullable=False, comment="COS对象Key")
    cos_url: Mapped[str] = mapped_column(String(1000), nullable=False, comment="COS访问URL")
    etag: Mapped[str] = mapped_column(String(100), nullable=False, comment="文件ETag")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'"), comment="状态：pending/completed/failed"
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="错误信息")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )
