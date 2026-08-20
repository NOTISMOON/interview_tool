"""面试报告表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InterviewReport(Base):
    """面试报告ORM模型，映射 interview_report 表。"""

    __tablename__ = "interview_report"
    __table_args__ = (
        Index("uk_interview_id", "interview_id", unique=True),
        Index("idx_user_id", "user_id"),
        Index("idx_user_score", "user_id", "total_score"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关联面试ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="用户ID")
    total_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, comment="总分")
    summary: Mapped[str] = mapped_column(Text, nullable=False, comment="总结")
    strengths: Mapped[dict] = mapped_column(JSON, nullable=False, comment="优势列表")
    weaknesses: Mapped[dict] = mapped_column(JSON, nullable=False, comment="不足列表")
    suggestions: Mapped[dict] = mapped_column(JSON, nullable=False, comment="建议列表")
    question_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="题目数量"
    )
    follow_up_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="追问次数（冗余）"
    )
    total_duration: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="面试总时长(秒)")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )