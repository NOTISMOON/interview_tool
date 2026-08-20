"""简历工作经历表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResumeWorkExperience(Base):
    """简历工作经历ORM模型，映射 resume_work_experience 表。"""

    __tablename__ = "resume_work_experience"
    __table_args__ = (Index("idx_resume_id", "resume_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关联简历ID")
    company: Mapped[str] = mapped_column(String(128), nullable=False, comment="公司名称")
    role: Mapped[str] = mapped_column(String(128), nullable=False, comment="职位")
    duration: Mapped[str] = mapped_column(String(64), nullable=False, comment="任职时间")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="工作描述")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment="排序")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )