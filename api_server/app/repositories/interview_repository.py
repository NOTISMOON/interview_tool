"""面试会话数据访问层（同步）。

面试交互链路为同步 HTTP（文档§3.4），API 进程内经同步会话操作
interview 表；逐题落库与冗余计数更新均在 service 层单事务内编排。
"""

from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.interview import (
    INTERVIEW_STATUS_COMPLETED,
    INTERVIEW_STATUS_IN_PROGRESS,
    Interview,
)


class InterviewRepository:
    """面试会话数据访问层，封装 interview 表CRUD（同步）。"""

    def list_by_user(
        self, db: Session, user_id: int, offset: int = 0, limit: int = 20
    ) -> list[Interview]:
        """分页查询用户面试记录（按ID倒序，含进行中/已完成/已中断）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            offset: 偏移量。
            limit: 每页条数。

        Returns:
            Interview列表。
        """
        stmt = (
            select(Interview)
            .where(Interview.user_id == user_id)
            .order_by(desc(Interview.id))
            .offset(offset)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    def count_by_user(self, db: Session, user_id: int) -> int:
        """统计用户面试记录总数（分页用）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。

        Returns:
            面试记录总数。
        """
        stmt = select(func.count()).where(Interview.user_id == user_id)
        return db.execute(stmt).scalar_one() or 0

    def create(self, db: Session, user_id: int, resume_id: int, interview_type: int) -> Interview:
        """创建面试会话记录（status=0 进行中）。

        Args:
            db: 数据库同步会话。
            user_id: 当前用户ID。
            resume_id: 使用的简历ID。
            interview_type: 面试类型 1-完整 2-快速。

        Returns:
            创建的Interview对象（含自增ID，即 session_id）。
        """
        interview = Interview(
            user_id=user_id,
            resume_id=resume_id,
            type=interview_type,
            status=INTERVIEW_STATUS_IN_PROGRESS,
        )
        db.add(interview)
        db.commit()
        db.refresh(interview)
        return interview

    def get_by_id(self, db: Session, interview_id: int) -> Interview | None:
        """按ID查询面试会话。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。

        Returns:
            Interview对象，不存在返回None。
        """
        return db.get(Interview, interview_id)

    def update_progress(
        self,
        db: Session,
        interview_id: int,
        current_question_index: int | None = None,
        follow_up_count: int | None = None,
    ) -> None:
        """更新面试推进冗余计数（与逐题落库同事务，§14.2）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。
            current_question_index: 当前基础题号（追问期间保持父题题号）。
            follow_up_count: 全场追问总次数。
        """
        interview = db.get(Interview, interview_id)
        if interview is None:
            return
        if current_question_index is not None:
            interview.current_question_index = current_question_index
        if follow_up_count is not None:
            interview.follow_up_count = follow_up_count
        db.flush()

    def finish(
        self,
        db: Session,
        interview_id: int,
        total_score: float,
        total_duration: int | None = None,
        follow_up_count: int | None = None,
    ) -> None:
        """标记面试完成（status=1 + 总分冗余回写 + 完成时间，§14.4）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。
            total_score: 面试总分（百分制）。
            total_duration: 面试总时长（秒）。
            follow_up_count: 全场追问总次数。
        """
        interview = db.get(Interview, interview_id)
        if interview is None:
            return
        interview.status = INTERVIEW_STATUS_COMPLETED
        interview.total_score = total_score
        interview.interview_time = datetime.now()
        if total_duration is not None:
            interview.total_duration = total_duration
        if follow_up_count is not None:
            interview.follow_up_count = follow_up_count
        db.flush()

    def abort(self, db: Session, interview_id: int) -> None:
        """标记面试中断（status=2，已答题目与评分保留，§21）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。
        """
        interview = db.get(Interview, interview_id)
        if interview is None:
            return
        interview.status = 2
        db.flush()


interview_repository = InterviewRepository()
