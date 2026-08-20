"""面试题目表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

QUESTION_TYPE_TECHNICAL = 1
QUESTION_TYPE_PROJECT = 2
QUESTION_TYPE_BEHAVIORAL = 3
CATEGORY_TECH_BASIC = 1
CATEGORY_PROJECT_EXPERIENCE = 2
CATEGORY_COMPREHENSIVE = 3
CATEGORY_ARCHITECTURE = 4


class InterviewQuestion(Base):
    """面试题目ORM模型，映射 interview_question 表。"""

    __tablename__ = "interview_question"
    __table_args__ = (
        Index("idx_interview_id", "interview_id"),
        Index("idx_interview_no", "interview_id", "question_no"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关联面试ID")
    question_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="题号")
    question_type: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-技术题 2-项目题 3-行为题")
    category: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="题目维度 1-技术基础 2-项目经验 3-综合素质 4-架构设计"
    )
    is_follow_up: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="是否追问题 0-否 1-是"
    )
    parent_question_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="父题目ID（追问关联）"
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False, comment="题目内容")
    user_answer: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用户回答文本")
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="语音回答文件地址")
    answer_duration: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="回答时长(秒)")
    thinking_duration: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="思考时长(秒)")
    ai_score: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="AI评分 1-5")
    ai_comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AI评价")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )