"""简历数据访问层（同步）。

服务端回调/Worker 均通过同步会话操作 resume 与 resume_work_experience 表
（Worker 内经 asyncio.to_thread 包装，与项目既有消费者模式一致）。
"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.models.resume import (
    RESUME_STATUS_ERROR,
    RESUME_STATUS_PARSING,
    RESUME_STATUS_READY,
    Resume,
)
from app.models.resume_work_experience import ResumeWorkExperience


class ResumeRepository:
    """简历数据访问层，封装简历与工作经历CRUD（同步）。"""

    def find_by_user_file_hash(self, db: Session, user_id: int, file_hash: str) -> Resume | None:
        """按用户+文件哈希查询未删除简历（去重命中）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            file_hash: 文件SHA256哈希。

        Returns:
            Resume对象，未命中返回None。
        """
        stmt = select(Resume).where(
            Resume.user_id == user_id,
            Resume.file_hash == file_hash,
            Resume.is_deleted == 0,
        )
        return db.execute(stmt).scalars().first()

    def count_active_by_user(self, db: Session, user_id: int) -> int:
        """统计用户未删除简历数量（份数上限校验）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。

        Returns:
            未删除简历总数。
        """
        stmt = select(func.count()).where(Resume.user_id == user_id, Resume.is_deleted == 0)
        return db.execute(stmt).scalar_one() or 0

    def create(
        self,
        db: Session,
        user_id: int,
        file_name: str,
        file_url: str,
        file_size: int,
        file_hash: str,
    ) -> Resume:
        """创建简历记录（初始状态为解析中）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            file_name: 原始文件名。
            file_url: 文件访问URL。
            file_size: 文件大小（字节）。
            file_hash: 文件SHA256哈希（去重键，创建即非空）。

        Returns:
            创建的Resume对象（含自增ID）。
        """
        resume = Resume(
            user_id=user_id,
            file_name=file_name,
            file_url=file_url,
            file_size=file_size,
            file_hash=file_hash,
            status=0,
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
        return resume

    def get_by_id(self, db: Session, resume_id: int) -> Resume | None:
        """按ID查询简历（含已软删除）。

        Args:
            db: 数据库同步会话。
            resume_id: 简历ID。

        Returns:
            Resume对象，不存在返回None。
        """
        return db.get(Resume, resume_id)

    def list_by_user(
        self, db: Session, user_id: int, offset: int = 0, limit: int = 20
    ) -> Sequence[Resume]:
        """分页查询用户未删除简历（按ID倒序）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            offset: 偏移量。
            limit: 每页条数。

        Returns:
            Resume列表。
        """
        stmt = (
            select(Resume)
            .where(Resume.user_id == user_id, Resume.is_deleted == 0)
            .order_by(desc(Resume.id))
            .offset(offset)
            .limit(limit)
        )
        return db.execute(stmt).scalars().all()

    def count_by_user(self, db: Session, user_id: int) -> int:
        """统计用户未删除简历总数（分页用）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。

        Returns:
            未删除简历总数。
        """
        stmt = select(func.count()).where(Resume.user_id == user_id, Resume.is_deleted == 0)
        return db.execute(stmt).scalar_one() or 0

    def save_parsed_result(
        self,
        db: Session,
        resume_id: int,
        name: str | None,
        skills: list[str] | None,
        education: list[dict] | None,
        projects: list[dict] | None,
        work_experiences: list[dict],
    ) -> None:
        """原子写入解析结果：更新简历解析字段并替换工作经历，置状态为就绪。

        同一事务内先删后插工作经历，避免状态与明细不一致的中间态。

        Args:
            db: 数据库同步会话。
            resume_id: 简历ID。
            name: 解析出的姓名。
            skills: 技能列表。
            education: 教育经历列表。
            projects: 项目经历列表。
            work_experiences: 工作经历列表（dict含company/role/duration/description）。
        """
        resume = db.get(Resume, resume_id)
        if resume is None:
            raise ValueError(f"简历不存在: resume_id={resume_id}")
        resume.parsed_name = name
        resume.parsed_skills = skills or []
        resume.parsed_education = education or []
        resume.parsed_projects = projects or []
        resume.error_message = None
        resume.status = RESUME_STATUS_READY

        # 先删旧工作经历，再插入新解析结果（同事务，原子）
        db.execute(delete(ResumeWorkExperience).where(ResumeWorkExperience.resume_id == resume_id))
        for idx, item in enumerate(work_experiences):
            # company/role/duration 表列为 NOT NULL：LLM 显式 null 时需归一为空串，
            # 否则违反约束导致整个解析结果落库失败（误判 status=2）
            db.add(
                ResumeWorkExperience(
                    resume_id=resume_id,
                    company=item.get("company") or "",
                    role=item.get("role") or "",
                    duration=item.get("duration") or "",
                    description=item.get("description"),
                    sort_order=idx,
                )
            )
        db.commit()

    def mark_parse_failed(self, db: Session, resume_id: int, error_message: str) -> None:
        """将简历标记为解析失败（状态2）并记录失败原因。

        Args:
            db: 数据库同步会话。
            resume_id: 简历ID。
            error_message: 失败原因（截断到字段长度）。
        """
        resume = db.get(Resume, resume_id)
        if resume is None:
            return
        resume.status = RESUME_STATUS_ERROR
        resume.error_message = (error_message or "")[:512]
        db.commit()

    def refresh_source(
        self,
        db: Session,
        resume_id: int,
        file_name: str,
        file_url: str,
        file_size: int,
        reset_for_reparse: bool = False,
    ) -> None:
        """刷新简历来源文件信息（去重复用时指向本次新上传的有效COS对象）。

        旧 file_url 可能随上传记录删除而失效（COS对象已删，解析404），
        命中去重复用时必须刷新为最新对象地址。

        Args:
            db: 数据库同步会话。
            resume_id: 简历ID。
            file_name: 最新原始文件名。
            file_url: 最新COS公开访问URL。
            file_size: 最新文件大小（字节）。
            reset_for_reparse: 是否同时重置状态为解析中并清空错误信息（重新调度前）。
        """
        resume = db.get(Resume, resume_id)
        if resume is None:
            return
        resume.file_name = file_name
        resume.file_url = file_url
        resume.file_size = file_size
        if reset_for_reparse:
            resume.status = RESUME_STATUS_PARSING
            resume.error_message = None
        db.commit()

    def soft_delete_by_id(self, db: Session, user_id: int, resume_id: int) -> Resume | None:
        """按用户+ID软删除简历（独立删除接口 DELETE /resumes/{id}）。

        软删仅置标记并释放 file_hash 唯一约束，保留行供面试上下文追溯（蓝图§3.6）；
        COS对象/上传记录/缓存/分析锁的物理清理由服务层联动完成。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID（归属校验）。
            resume_id: 简历ID。

        Returns:
            被软删除的Resume对象；不存在或已删除/非本人返回None。
        """
        resume = db.get(Resume, resume_id)
        if resume is None or resume.user_id != user_id or resume.is_deleted:
            return None
        resume.is_deleted = 1
        resume.deleted_at = datetime.now()
        resume.file_hash = None  # 释放唯一约束，允许之后重新上传同一文件
        db.commit()
        return resume

    def reset_for_retry(self, db: Session, resume_id: int) -> None:
        """将失败简历重置为解析中状态并清空错误信息（一键重试前置）。

        Args:
            db: 数据库同步会话。
            resume_id: 简历ID。
        """
        resume = db.get(Resume, resume_id)
        if resume is None:
            return
        resume.status = RESUME_STATUS_PARSING
        resume.error_message = None
        db.commit()

    def soft_delete_by_file_url(self, db: Session, user_id: int, file_url: str) -> int:
        """按用户+文件URL软删除简历（删除上传记录时联动，防悬空简历行）。

        置 is_deleted=1 并清空 file_hash 释放 uk_user_file_hash 唯一约束，
        允许用户删除后重新上传同一文件（模型注释既定设计）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            file_url: 简历来源文件URL（与上传记录 cos_url 一致）。

        Returns:
            被软删除的简历条数。
        """
        stmt = select(Resume).where(
            Resume.user_id == user_id,
            Resume.file_url == file_url,
            Resume.is_deleted == 0,
        )
        resumes = list(db.execute(stmt).scalars().all())
        now = datetime.now()
        for resume in resumes:
            resume.is_deleted = 1
            resume.deleted_at = now
            resume.file_hash = None  # 释放唯一约束，允许重新上传同一文件
        db.commit()
        return len(resumes)


resume_repository = ResumeRepository()
