"""面试报告数据访问层（同步）。

报告与 interview 1:1（uk_interview_id），生成成功后落库；
重试路径按唯一约束幂等（先删后插或 upsert）。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview_report import InterviewReport


class InterviewReportRepository:
    """面试报告数据访问层，封装 interview_report 表CRUD（同步）。"""

    def get_by_interview(self, db: Session, interview_id: int) -> InterviewReport | None:
        """查询面试报告（未生成返回None，报告接口据此返回generating）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。

        Returns:
            InterviewReport对象，不存在返回None。
        """
        stmt = select(InterviewReport).where(InterviewReport.interview_id == interview_id)
        return db.execute(stmt).scalars().first()

    def upsert(self, db: Session, **fields) -> InterviewReport:
        """插入或替换面试报告（regenerate 手动重试路径，uk_interview_id 幂等）。

        Args:
            db: 数据库同步会话。
            **fields: 报告字段（interview_id/user_id/total_score/summary等）。

        Returns:
            落库后的InterviewReport对象。
        """
        interview_id = fields["interview_id"]
        existing = self.get_by_interview(db, interview_id)
        if existing is not None:
            # 重试路径：整条替换，保证报告内容与最新一次生成一致
            for key, value in fields.items():
                setattr(existing, key, value)
            db.flush()
            db.commit()
            db.refresh(existing)
            return existing
        row = InterviewReport(**fields)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


interview_report_repository = InterviewReportRepository()
