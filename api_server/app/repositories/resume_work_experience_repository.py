"""简历工作经历数据访问层（同步）。"""

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resume_work_experience import ResumeWorkExperience


class ResumeWorkExperienceRepository:
    """简历工作经历数据访问层（同步）。"""

    def list_by_resume(self, db: Session, resume_id: int) -> Sequence[ResumeWorkExperience]:
        """查询指定简历的全部工作经历（按sort_order排序）。

        Args:
            db: 数据库同步会话。
            resume_id: 简历ID。

        Returns:
            ResumeWorkExperience列表。
        """
        stmt = (
            select(ResumeWorkExperience)
            .where(ResumeWorkExperience.resume_id == resume_id)
            .order_by(ResumeWorkExperience.sort_order.asc())
        )
        return db.execute(stmt).scalars().all()


resume_work_experience_repository = ResumeWorkExperienceRepository()
