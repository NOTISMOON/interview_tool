"""面试会话表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

INTERVIEW_TYPE_FULL = 1
INTERVIEW_TYPE_QUICK = 2
INTERVIEW_STATUS_IN_PROGRESS = 0
INTERVIEW_STATUS_COMPLETED = 1
INTERVIEW_STATUS_INTERRUPTED = 2


class Interview(Base):
    """面试会话ORM模型，映射 interview 表。"""

    __tablename__ = "interview"
    __table_args__ = (
        Index("idx_user_id", "user_id"),
        Index("idx_user_status", "user_id", "status"),
        Index("idx_resume_id", "resume_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="用户ID")
    resume_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="使用的简历ID")
    type: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), comment="1-完整面试 2-快速面试"
    )
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="0-进行中 1-已完成 2-已中断"
    )
    current_question_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="当前题目索引"
    )
    total_score: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="面试总分"
    )
    total_duration: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="面试总时长(秒)")
    follow_up_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="追问次数（冗余计数）"
    )
    device_check_passed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="设备检测是否通过"
    )
    interview_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="面试完成时间")
    is_deleted: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="软删除标记 0-正常 1-已删除"
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