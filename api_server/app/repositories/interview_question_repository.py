"""面试题目数据访问层（同步）。

题目排序约定（DDL 注释）：追问题与父题目同 question_no，靠 is_follow_up
区分；面试发问顺序 = ORDER BY question_no ASC, is_follow_up ASC, id ASC
（基础题按题号推进，追问题紧随其父题之后发问）。
"""

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.interview_question import InterviewQuestion

# 发问顺序排序键（基础题按题号、追问题紧随父题）
_ORDER = (
    InterviewQuestion.question_no.asc(),
    InterviewQuestion.is_follow_up.asc(),
    InterviewQuestion.id.asc(),
)


class InterviewQuestionRepository:
    """面试题目数据访问层，封装 interview_question 表CRUD（同步）。"""

    def bulk_create(self, db: Session, interview_id: int, questions: Sequence[dict]) -> list[InterviewQuestion]:
        """批量落库预生成基础题（创建面试时一次性写入，§7.2）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。
            questions: 题目字典列表（question_no/question_type/category/question_text）。

        Returns:
            创建的InterviewQuestion列表（按传入顺序）。
        """
        rows = [InterviewQuestion(interview_id=interview_id, **q) for q in questions]
        db.add_all(rows)
        db.flush()
        return rows

    def list_by_interview(self, db: Session, interview_id: int) -> Sequence[InterviewQuestion]:
        """按发问顺序查询面试全部题目（Checkpoint 重建 / 报告组装用）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。

        Returns:
            按发问顺序排列的InterviewQuestion列表。
        """
        stmt = select(InterviewQuestion).where(InterviewQuestion.interview_id == interview_id).order_by(*_ORDER)
        return db.execute(stmt).scalars().all()

    def count_base(self, db: Session, interview_id: int) -> int:
        """统计基础题数量（终止条件与追问上限判定用，§10/§12.1）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。

        Returns:
            基础题（is_follow_up=0）总数。
        """
        stmt = (
            select(func.count())
            .where(InterviewQuestion.interview_id == interview_id)
            .where(InterviewQuestion.is_follow_up == 0)
        )
        return db.execute(stmt).scalar_one() or 0

    def count_answered(self, db: Session, interview_id: int) -> int:
        """统计已答题目数量（含追问，Checkpoint 冗余字段）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。

        Returns:
            已有回答（user_answer 非空）的题目总数。
        """
        stmt = (
            select(func.count())
            .where(InterviewQuestion.interview_id == interview_id)
            .where(InterviewQuestion.user_answer.is_not(None))
        )
        return db.execute(stmt).scalar_one() or 0

    def count_follow_up_by_parent(self, db: Session, parent_question_id: int) -> int:
        """统计某基础题已产生的追问次数（每题最多追问1次，§10）。

        Args:
            db: 数据库同步会话。
            parent_question_id: 父题目ID。

        Returns:
            该基础题的追问题数量。
        """
        stmt = (
            select(func.count())
            .where(InterviewQuestion.parent_question_id == parent_question_id)
            .where(InterviewQuestion.is_follow_up == 1)
        )
        return db.execute(stmt).scalar_one() or 0

    def count_follow_up_total(self, db: Session, interview_id: int) -> int:
        """统计全场追问总数（上限=基础题数，§10）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。

        Returns:
            全场追问题总数。
        """
        stmt = (
            select(func.count())
            .where(InterviewQuestion.interview_id == interview_id)
            .where(InterviewQuestion.is_follow_up == 1)
        )
        return db.execute(stmt).scalar_one() or 0

    def create_follow_up(
        self,
        db: Session,
        interview_id: int,
        question_no: int,
        question_type: int,
        category: int | None,
        parent_question_id: int,
        question_text: str,
    ) -> InterviewQuestion:
        """落库追问题（is_follow_up=1，与父题同题号，§11）。

        与逐题分析结果落库同事务（§14.2）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。
            question_no: 父题目题号（追问题与父题同号）。
            question_type: 父题目题型。
            category: 父题目维度。
            parent_question_id: 父题目ID。
            question_text: 追问内容（分析输出预生成）。

        Returns:
            创建的InterviewQuestion对象（含自增ID）。
        """
        row = InterviewQuestion(
            interview_id=interview_id,
            question_no=question_no,
            question_type=question_type,
            category=category,
            is_follow_up=1,
            parent_question_id=parent_question_id,
            question_text=question_text,
        )
        db.add(row)
        db.flush()
        return row

    def save_analysis(
        self,
        db: Session,
        question_id: int,
        user_answer: str,
        ai_score: int,
        ai_comment: str,
        answer_duration: int | None = None,
    ) -> None:
        """落库单题回答与AI分析结果（逐题持久化，§14.1/§14.2）。

        Args:
            db: 数据库同步会话。
            question_id: 题目ID。
            user_answer: 用户回答文本。
            ai_score: AI综合评分 1-5。
            ai_comment: AI评价。
            answer_duration: 回答时长（秒，可选）。
        """
        question = db.get(InterviewQuestion, question_id)
        if question is None:
            return
        question.user_answer = user_answer
        question.ai_score = ai_score
        question.ai_comment = ai_comment
        if answer_duration is not None:
            question.answer_duration = answer_duration
        db.flush()

    def get_by_id(self, db: Session, question_id: int) -> InterviewQuestion | None:
        """按ID查询单题。

        Args:
            db: 数据库同步会话。
            question_id: 题目ID。

        Returns:
            InterviewQuestion对象，不存在返回None。
        """
        return db.get(InterviewQuestion, question_id)


interview_question_repository = InterviewQuestionRepository()
