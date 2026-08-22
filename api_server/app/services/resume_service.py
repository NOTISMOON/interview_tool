"""简历业务服务层（同步）。

编排「上传回调 → SHA256 去重 → 简历创建（份数上限6 + 唯一约束竞态回查）→
分析调度（Redis锁 + Outbox事件投递）」同步快速路径，以及简历列表/详情查询。

设计对齐《简历上传分析功能文档》§3.2/§3.3：
    - 去重：回调内服务端一次 COS GET 计算 SHA256，创建即去重；
    - 并发竞态：插入放 IntegrityError try/except 内，冲突后回查复用；
    - 调度：查状态 → SET NX EX 抢锁 → Outbox 写事件（事务原子），失败必释放锁。
"""

import hashlib
import logging
from datetime import datetime

import redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cos import build_cos_url, cos_client, cos_key_from_url
from app.models.resume import (
    RESUME_STATUS_ERROR,
    RESUME_STATUS_PARSING,
    RESUME_STATUS_READY,
    Resume,
)
from app.redis import resume_lock
from app.repositories.outbox_repository import sync_outbox_repository
from app.repositories.resume_repository import resume_repository
from app.repositories.resume_work_experience_repository import (
    resume_work_experience_repository,
)
from app.repositories.upload_repository import upload_repository
from app.schemas.resume import ResumeListResponse, ResumeOut

logger = logging.getLogger(__name__)

# 每用户未删除简历份数上限（蓝图已定）
MAX_ACTIVE_RESUMES = 6


class ResumeLimitExceededError(Exception):
    """简历数量已达上限（路由层转409）。"""

class ResumeNotFoundError(Exception):
    """简历不存在或无权访问（路由层转404）。"""

class ResumeNotRetryableError(Exception):
    """简历不满足重试条件（路由层转409，仅失败简历可重试）。"""


class ResumeService:
    """简历业务编排层（同步）：去重创建 + 分析调度 + 查询。"""

    # ------------------------------------------------------------------
    # 上传回调联动：去重 + 创建 + 调度
    # ------------------------------------------------------------------

    def on_resume_uploaded(
        self,
        db: Session,
        cache_client: redis.Redis,
        user_id: int,
        cos_key: str,
        file_name: str,
        file_size: int,
    ) -> dict:
        """简历上传回调联动入口：去重创建记录并调度AI分析。

        流程（蓝图§3.2）: COS GET 下载文件计算SHA256 → 按 (user_id, file_hash)
        查未删除简历 → 命中复用（就绪直接返回 / 非就绪重新调度自愈）→
        未命中校验份数上限后插入（IntegrityError 回查复用）→ 调度分析。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端（分析锁）。
            user_id: 当前用户ID。
            cos_key: COS对象Key。
            file_name: 原始文件名。
            file_size: 文件大小（字节）。

        Returns:
            {"resume_id": int, "created": bool, "status": int, "scheduled": bool}

        Raises:
            ResumeLimitExceededError: 未删除简历数已达上限6。
            CosError: COS下载失败。
        """
        # 1. 下载文件内容计算SHA256（同地域 ≤10MB，毫秒~秒级）
        content = cos_client.get_object_bytes(cos_key)
        if content is None:
            raise ResumeNotFoundError("简历文件不存在")
        file_hash = hashlib.sha256(content).hexdigest()

        # 2. 去重查询（仅看未删除记录）
        existing = resume_repository.find_by_user_file_hash(db, user_id, file_hash)
        if existing is not None:
            # 命中复用：不占新名额；刷新来源指向本次新上传的有效COS对象
            # （旧 file_url 可能已随上传记录删除而失效，解析会404），
            # 已就绪仅刷新指针；非就绪（解析中/失败）重置状态后重新调度自愈。
            is_ready = existing.status == RESUME_STATUS_READY
            resume_repository.refresh_source(
                db,
                existing.id,
                file_name=file_name,
                file_url=build_cos_url(cos_key),
                file_size=file_size,
                reset_for_reparse=not is_ready,
            )
            scheduled = self._schedule_analysis(db, cache_client, existing, cos_key)
            logger.info(
                "简历去重命中复用: user_id=%s resume_id=%s status=%s scheduled=%s",
                user_id, existing.id, existing.status, scheduled,
            )
            return {
                "resume_id": existing.id,
                "created": False,
                "status": existing.status,
                "scheduled": scheduled,
            }

        # 3. 份数上限校验（仅统计未删除记录）
        active_count = resume_repository.count_active_by_user(db, user_id)
        if active_count >= MAX_ACTIVE_RESUMES:
            raise ResumeLimitExceededError(f"简历数量已达上限（{MAX_ACTIVE_RESUMES}），请删除后再上传")

        # 4. 插入新简历（IntegrityError 竞态回查复用，蓝图§5.1）
        try:
            resume = resume_repository.create(
                db,
                user_id=user_id,
                file_name=file_name,
                file_url=build_cos_url(cos_key),
                file_size=file_size,
                file_hash=file_hash,
            )
        except IntegrityError:
            # 并发上传同一文件：唯一约束冲突 → 回滚后回查复用先建记录
            db.rollback()
            winner = resume_repository.find_by_user_file_hash(db, user_id, file_hash)
            if winner is None:
                raise
            logger.info("简历并发竞态回查复用: user_id=%s resume_id=%s", user_id, winner.id)
            scheduled = self._schedule_analysis(db, cache_client, winner, cos_key)
            return {
                "resume_id": winner.id,
                "created": False,
                "status": winner.status,
                "scheduled": scheduled,
            }

        # 5. 调度AI分析（锁 + Outbox）
        scheduled = self._schedule_analysis(db, cache_client, resume, cos_key)
        logger.info(
            "简历创建完成并调度分析: user_id=%s resume_id=%s scheduled=%s",
            user_id, resume.id, scheduled,
        )
        return {
            "resume_id": resume.id,
            "created": True,
            "status": RESUME_STATUS_PARSING,
            "scheduled": scheduled,
        }

    def _schedule_analysis(
        self, db: Session, cache_client: redis.Redis, resume: Resume, cos_key: str = ""
    ) -> bool:
        """调度AI分析任务：查状态 → 抢Redis锁 → Outbox写事件（蓝图§3.3）。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            resume: 简历ORM对象。
            cos_key: 本次上传的COS对象Key（Worker下载依据；缺省时由其从file_url反解）。

        Returns:
            是否成功投递分析任务（已就绪或锁被持有时返回False）。
        """
        # 已就绪 → 跳过
        if resume.status == RESUME_STATUS_READY:
            return False

        task_uuid = resume_lock.generate_task_uuid(resume.id)
        # 抢锁失败 → 已有任务在执行，不重复投递
        if not resume_lock.acquire_sync(cache_client, resume.id, task_uuid):
            logger.info("简历分析锁被持有，跳过调度: resume_id=%s", resume.id)
            return False

        try:
            # 写Outbox事件并提交（会话可能已隐式开启事务，统一commit收口）
            sync_outbox_repository.insert_event(
                db,
                event_type="resume.parse",
                aggregate_type="resume",
                aggregate_id=str(resume.id),
                payload={
                    "resume_id": resume.id,
                    "user_id": resume.user_id,
                    "task_uuid": task_uuid,
                    "cos_key": cos_key,
                    "file_name": resume.file_name,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            db.commit()
            return True
        except Exception:
            # 投递失败必释放锁，避免死锁阻塞后续重试（蓝图§5.2）
            db.rollback()
            resume_lock.release_sync(cache_client, resume.id, task_uuid)
            logger.exception("简历分析调度失败: resume_id=%s", resume.id)
            raise

    # ------------------------------------------------------------------
    # 简历查询（列表/详情）
    # ------------------------------------------------------------------

    def list_resumes(
        self, db: Session, user_id: int, page: int = 1, page_size: int = 20
    ) -> ResumeListResponse:
        """分页查询当前用户未删除简历（按ID倒序，含工作经历）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            page: 页码（从1开始）。
            page_size: 页大小。

        Returns:
            ResumeListResponse: 简历列表 + 总数 + 分页信息。
        """
        offset = (page - 1) * page_size
        rows = resume_repository.list_by_user(db, user_id, offset, page_size)
        total = resume_repository.count_by_user(db, user_id)
        items = [self._to_out(db, r) for r in rows]
        return ResumeListResponse(items=items, total=total, page=page, page_size=page_size)

    def get_resume(self, db: Session, user_id: int, resume_id: int) -> ResumeOut:
        """查询简历详情（强制归属校验，仅本人可读，蓝图§5.3）。

        Args:
            db: 数据库同步会话。
            user_id: 当前用户ID（归属校验）。
            resume_id: 简历ID。

        Returns:
            ResumeOut: 简历详情。

        Raises:
            ResumeNotFoundError: 简历不存在、已删除或不属于当前用户。
        """
        resume = resume_repository.get_by_id(db, resume_id)
        if resume is None or resume.user_id != user_id or resume.is_deleted:
            raise ResumeNotFoundError("简历不存在")
        return self._to_out(db, resume)

    # ------------------------------------------------------------------
    # 简历删除（独立接口 DELETE /resumes/{id}，蓝图§3.6）
    # ------------------------------------------------------------------

    def delete_resume(self, db: Session, cache_client: redis.Redis, user_id: int, resume_id: int) -> None:
        """软删除简历并联动清理下游资源（可重复删除，幂等）。

        软删 resume（is_deleted=1、file_hash 置空以释放唯一约束）；
        物理删除关联 upload_records 记录；删除 COS 对象；清理分析结果/状态缓存；
        无条件释放分析锁，避免阻塞后续重新上传（蓝图§3.6 删除流程）。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端（缓存与锁）。
            user_id: 当前用户ID（归属校验）。
            resume_id: 简历ID。

        Raises:
            ResumeNotFoundError: 简历不存在、已删除或不属于当前用户。
            CosError: COS 删除失败。
        """
        resume = resume_repository.soft_delete_by_id(db, user_id, resume_id)
        if resume is None:
            raise ResumeNotFoundError("简历不存在")

        # 关联上传记录物理删除 + COS对象删除（幂等：文件不存在视为成功）
        records = upload_repository.list_by_user_and_cos_url(db, user_id, resume.file_url or "")
        for record in records:
            cos_client.delete_object(record.cos_key)
        upload_repository.delete_by_ids(db, [r.id for r in records])

        # 清理分析结果/状态缓存
        cache_client.delete(
            f"resume:analysis:{resume_id}",
            f"resume:analysis:status:{resume_id}",
        )
        # 无条件释放分析锁（防残留锁值阻塞后续上传）
        resume_lock.delete_sync(cache_client, resume_id)
        logger.info(
            "简历已删除: user_id=%s resume_id=%s removed_upload_records=%s",
            user_id, resume_id, len(records),
        )

    # ------------------------------------------------------------------
    # 简历失败一键重试（POST /resumes/{id}/retry，蓝图§3.5/§4）
    # ------------------------------------------------------------------

    def retry_analysis(self, db: Session, cache_client: redis.Redis, user_id: int, resume_id: int) -> ResumeOut:
        """对失败（status=2）简历一键重试：重置状态并重新调度分析。

        仅 status=2 可重试：重置为解析中 → 无条件清除残留锁 → 重新调度
        （抢锁 + 写 Outbox 事件）。就绪/解析中记录返回409，避免误操作。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端（锁）。
            user_id: 当前用户ID（归属校验）。
            resume_id: 简历ID。

        Returns:
            ResumeOut: 重试触发后的简历详情（status=0 解析中）。

        Raises:
            ResumeNotFoundError: 简历不存在、已删除或不属于当前用户。
            ResumeNotRetryableError: 简历非失败态（status != 2）。
        """
        resume = resume_repository.get_by_id(db, resume_id)
        if resume is None or resume.user_id != user_id or resume.is_deleted:
            raise ResumeNotFoundError("简历不存在")
        if resume.status != RESUME_STATUS_ERROR:
            raise ResumeNotRetryableError("仅解析失败的简历可重试")

        # 清残留锁并重置状态为解析中（Worker 下载依据 cos_key 由 file_url 反解）
        resume_lock.delete_sync(cache_client, resume_id)
        resume_repository.reset_for_retry(db, resume_id)

        # 重新调度（file_url 为公开链接，Worker 用 cos_key_from_url 反解下载）
        cos_key = cos_key_from_url(resume.file_url or "")
        scheduled = self._schedule_analysis(db, cache_client, resume, cos_key)
        logger.info(
            "简历失败重试已调度: user_id=%s resume_id=%s scheduled=%s",
            user_id, resume_id, scheduled,
        )
        return self._to_out(db, resume)

    def _to_out(self, db: Session, resume: Resume) -> ResumeOut:
        """将Resume ORM对象转响应模型（附带工作经历与预签名访问URL）。

        Args:
            db: 数据库同步会话。
            resume: 简历ORM对象。

        Returns:
            ResumeOut响应模型。
        """
        works = resume_work_experience_repository.list_by_resume(db, resume.id)
        return ResumeOut(
            id=resume.id,
            user_id=resume.user_id,
            file_name=resume.file_name,
            file_url=resume.file_url,
            file_size=resume.file_size,
            status=resume.status,
            parsed_name=resume.parsed_name,
            parsed_skills=resume.parsed_skills,
            parsed_education=resume.parsed_education,
            parsed_projects=resume.parsed_projects,
            error_message=resume.error_message,
            created_at=resume.created_at or datetime.now(),
            updated_at=resume.updated_at or datetime.now(),
            work_experiences=works,
        )


resume_service = ResumeService()
