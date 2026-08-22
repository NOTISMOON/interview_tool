"""面试业务消费者模块。

    - InterviewResumeParseConsumer: 简历AI分析Worker（蓝图§3.4）。
      消费 interview.resume.parse.queue：锁校验 → COS下载 → LangGraph解析 →
      单事务落库 → 释放锁 → 缓存失效 → 完成通知；失败置 status=2 并通知可重试。
    - InterviewReportConsumer: 面试报告生成消费者（骨架，待后续里程碑接入）。
"""

import asyncio
import logging
import time

from app.cos import build_cos_url, cos_key_from_url
from app.db.sync_session import SyncSessionLocal
from app.llm.schemas.resume import ResumeExtraction
from app.llm.workflow import parse_resume
from app.models.message import MESSAGE_TYPE_SYSTEM, RELATED_TYPE_RESUME
from app.models.resume import RESUME_STATUS_READY, Resume
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.redis import resume_lock
from app.redis.async_client import AsyncRedisClient
from app.repositories.resume_repository import resume_repository
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

# 简历分析结果缓存键（写路径失效，蓝图§5.8）
_RESULT_CACHE_KEY = "resume:analysis:{resume_id}"
_STATUS_CACHE_KEY = "resume:analysis:status:{resume_id}"


class InterviewResumeParseConsumer(BaseConsumer):
    """简历解析任务消费者（独立Worker进程内运行，蓝图§5.6）。

    消费 resume.parse 事件，payload 含 resume_id / user_id / task_uuid / cos_key。
    task_uuid 为调度侧写入的分析锁值，提交结果前校验一致以防锁过期后重复写入。
    """

    queue_name = QueueName.INTERVIEW_RESUME_PARSE

    async def handle_message(self, message: MQMessage) -> None:
        """处理简历解析任务：锁校验→下载→解析→落库→通知。

        失败不向外抛（内部消化置 status=2），避免消息 reject 循环；
        锁释放放 finally，异常路径必释放（蓝图§5.2）。

        Args:
            message: 入站消息对象，payload 含 resume_id/user_id/task_uuid/cos_key。
        """
        payload = message.payload
        resume_id = int(payload["resume_id"])
        user_id = int(payload["user_id"])
        task_uuid = str(payload.get("task_uuid", ""))
        started_at = time.monotonic()
        logger.info(
            "简历分析任务开始 resume_id=%s user_id=%s task_uuid=%s message_id=%s",
            resume_id, user_id, task_uuid, message.message_id,
        )

        # 1. 加载简历行（软删除/已就绪直接跳过，幂等）
        resume = await asyncio.to_thread(self._load_resume, resume_id)
        if resume is None or resume.is_deleted:
            logger.info("简历不存在或已删除，跳过分析 resume_id=%s", resume_id)
            return
        if resume.status == RESUME_STATUS_READY:
            logger.info("简历已就绪，跳过重复分析 resume_id=%s", resume_id)
            return

        # 2. 锁校验：值等于本任务 task_uuid，或锁过期后重新认领（自愈）
        redis_client = await AsyncRedisClient.get_client()
        if not await self._ensure_lock(redis_client, resume_id, task_uuid):
            logger.warning("分析锁被其他任务持有，本任务跳过 resume_id=%s", resume_id)
            return

        try:
            # 3. 确定文件公开访问地址（.pdf/.docx 均直连线上链接，需 COS 桶对 resumes/* 公读）
            #    优先用本次调度携带的 cos_key 构建地址：它是刚通过回调校验的有效对象；
            #    resume.file_url 可能已随上传记录删除而失效（历史bug：404）
            cos_key = str(payload.get("cos_key") or "") or cos_key_from_url(resume.file_url or "")
            file_url = build_cos_url(cos_key) if cos_key else resume.file_url
            if not file_url:
                raise ValueError("简历缺少公开访问地址 file_url")

            # 4. LangGraph 工作流解析（文本提取 + LLM结构化提取，重IO走线程池）
            extraction = await asyncio.to_thread(parse_resume, cos_key, file_url)

            # 5. 提交前二次校验锁（防分析期间锁过期被新任务接管）
            if not await resume_lock.verify_async(redis_client, resume_id, task_uuid):
                raise RuntimeError("分析锁已失效（可能被新任务接管），放弃写入")

            # 6. 单事务写入解析结果 + 工作经历 + status=1
            await asyncio.to_thread(self._save_result, resume_id, extraction)

            # 7. 失效结果缓存（写路径失效，蓝图§5.8）
            await redis_client.delete(
                _RESULT_CACHE_KEY.format(resume_id=resume_id),
                _STATUS_CACHE_KEY.format(resume_id=resume_id),
            )

            # 8. 完成/失败通知（对齐 follow_post_consumer 模式）
            await self._notify(user_id, resume_id, success=True)

            logger.info(
                "简历分析完成 resume_id=%s elapsed_ms=%d",
                resume_id, (time.monotonic() - started_at) * 1000,
            )
        except Exception as exc:
            # 失败：置status=2 + error_message + 失败通知（蓝图§3.4失败分支）
            logger.exception("简历分析失败 resume_id=%s", resume_id)
            try:
                await asyncio.to_thread(
                    self._mark_failed, resume_id, f"{type(exc).__name__}: {exc}"
                )
                await self._notify(user_id, resume_id, success=False)
            except Exception:
                logger.exception("记录分析失败状态/通知异常 resume_id=%s", resume_id)
        finally:
            # 必释放锁（compare-and-del，仅删自己的锁）
            await resume_lock.release_async(redis_client, resume_id, task_uuid)

    # ------------------------------------------------------------------
    # 同步DB操作（经 asyncio.to_thread 调用，避免阻塞事件循环）
    # ------------------------------------------------------------------

    @staticmethod
    def _load_resume(resume_id: int) -> Resume | None:
        """同步查询简历记录。

        Args:
            resume_id: 简历ID。

        Returns:
            Resume对象，不存在返回None。
        """
        db = SyncSessionLocal()
        try:
            return resume_repository.get_by_id(db, resume_id)
        finally:
            db.close()

    @staticmethod
    def _save_result(resume_id: int, extraction: ResumeExtraction) -> None:
        """同步单事务写入解析结果与工作经历。

        Args:
            resume_id: 简历ID。
            extraction: LLM结构化提取结果。

        Raises:
            ValueError: 简历不存在。
        """
        db = SyncSessionLocal()
        try:
            resume_repository.save_parsed_result(
                db,
                resume_id=resume_id,
                name=extraction.name,
                skills=list(extraction.skills),
                education=[item.model_dump() for item in extraction.education],
                projects=[item.model_dump() for item in extraction.projects],
                work_experiences=[item.model_dump() for item in extraction.work_experience],
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _mark_failed(resume_id: int, error_message: str) -> None:
        """同步标记简历解析失败。

        Args:
            resume_id: 简历ID。
            error_message: 失败原因（截断512）。
        """
        db = SyncSessionLocal()
        try:
            resume_repository.mark_parse_failed(db, resume_id, error_message)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 锁与通知
    # ------------------------------------------------------------------

    @staticmethod
    async def _ensure_lock(redis_client, resume_id: int, task_uuid: str) -> bool:
        """校验或重新认领分析锁。

        锁值匹配（正常路径）或锁已过期时用本任务uuid重新抢锁（自愈路径），
        二者均失败说明有其他任务持有锁，跳过本任务。

        Args:
            redis_client: 异步Redis客户端。
            resume_id: 简历ID。
            task_uuid: 本任务标识。

        Returns:
            是否取得锁执行权。
        """
        if await resume_lock.verify_async(redis_client, resume_id, task_uuid):
            return True
        return await resume_lock.acquire_async(redis_client, resume_id, task_uuid)

    async def _notify(self, user_id: int, resume_id: int, *, success: bool) -> None:
        """创建系统通知并通过SSE推送（完成/失败，蓝图§3.5）。

        通知不携带分析结果（内部数据仅供面试模块消费），失败通知提示可重试。

        Args:
            user_id: 接收通知的用户ID。
            resume_id: 简历ID。
            success: 分析是否成功。
        """
        content = (
            "简历 AI 分析已完成" if success else "简历 AI 分析失败，请重新上传或重试"
        )
        message_id = await asyncio.to_thread(
            self._create_notification_sync, user_id, resume_id, content
        )
        if message_id is None:
            return
        # SSE实时推送（失败仅记日志，用户重连后走补偿拉取）
        try:
            from app.db.async_session import AsyncSessionLocal
            from app.repositories.message_repository import message_repository

            async with AsyncSessionLocal() as async_db:
                msg = await message_repository.get_by_id(async_db, user_id, message_id)
                if msg is None:
                    return
                unread_total = await message_repository.get_unread_count(async_db, user_id)
                message_response = (await notification_service.to_responses(async_db, [msg]))[0]
                sse_event = {
                    "kind": "message",
                    "message": message_response.model_dump(mode="json", by_alias=True),
                    "unread_total": unread_total,
                }
                await notification_service.publish_to_user(user_id, sse_event)
        except Exception:
            logger.exception("简历分析通知SSE推送失败 user_id=%s resume_id=%s", user_id, resume_id)

    @staticmethod
    def _create_notification_sync(user_id: int, resume_id: int, content: str) -> int | None:
        """同步创建系统通知消息（新开同步会话独立提交）。

        Args:
            user_id: 接收用户ID。
            resume_id: 关联简历ID。
            content: 通知内容。

        Returns:
            消息ID，失败返回None。
        """
        db = SyncSessionLocal()
        try:
            msg = notification_service.create_notification(
                db=db,
                recipient_id=user_id,
                msg_type=MESSAGE_TYPE_SYSTEM,
                title="简历分析",
                content=content,
                related_id=resume_id,
                related_type=RELATED_TYPE_RESUME,
            )
            db.commit()
            return msg.id
        except Exception:
            db.rollback()
            logger.exception("创建简历分析通知失败 user_id=%s resume_id=%s", user_id, resume_id)
            return None
        finally:
            db.close()


class InterviewReportConsumer(BaseConsumer):
    """面试报告生成消费者。

    消费 interview.report.queue 队列消息，
    根据负载中的 interview_id 调用 AI 服务生成面试综合报告（后续里程碑接入）。
    """

    queue_name = QueueName.INTERVIEW_REPORT_GENERATE

    async def handle_message(self, message: MQMessage) -> None:
        """处理面试报告生成任务（骨架，待接入AI报告服务）。

        Args:
            message: 入站消息对象，payload 含 interview_id。
        """
        interview_id = message.payload.get("interview_id")
        logger.info(
            "开始生成面试报告 interview_id=%s message_id=%s",
            interview_id,
            message.message_id,
        )
