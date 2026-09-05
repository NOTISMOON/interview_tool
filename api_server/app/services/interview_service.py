"""面试业务服务层（同步）。

编排《面试流程功能文档》主链路：
    创建面试（简历状态硬校验 + 操作锁内预生成基础题落库 + Checkpoint 初始化）
    → 提交回答（epoch 租约 → 状态版本 → 操作锁 → 幂等检查 → 单次合并 LLM
      分析 → 规则追问判定 → 逐题落库单事务）
    → 终止（全部答完/时长兜底 → phase=summarizing → 后台报告生成）
    → 报告查询/重试（generating/ready/failed + 惰性兜底触发）。

并发控制（§5 三层机制，校验顺序 §5.7：epoch 租约 → 状态版本 → 操作锁）：
    ① 操作锁 interview:lock:{id}：单次状态推进互斥，finally 必释放；
    ② 状态版本：question_index + phase 比对，不符 409 + 最新状态；
    ③ 客户端租约 epoch：写请求携带 epoch 不一致即 409（双开裁决）。

幂等（§5.9）：提交回答以 (session_id, question_index) 为幂等键，
已分析过的题直接返回既有结果，不重复调用 LLM。
"""

import json
import logging
from datetime import datetime

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.llm.schemas.interview import InterviewReportResult
from app.llm.workflow.interview import (
    ACTION_END,
    ACTION_FOLLOW_UP,
    correct_speech_text,
    generate_follow_up_stream,
    generate_questions,
    generate_report,
    invalidate_checkpoint,
    is_follow_up_none,
    run_fast_decision,
)
from app.models.interview import (
    INTERVIEW_STATUS_COMPLETED,
    INTERVIEW_STATUS_IN_PROGRESS,
    INTERVIEW_STATUS_INTERRUPTED,
    INTERVIEW_TYPE_FULL,
    Interview,
)
from app.models.interview_question import InterviewQuestion
from app.models.resume import (
    RESUME_STATUS_ERROR,
    RESUME_STATUS_PARSING,
    RESUME_STATUS_READY,
    Resume,
)
from app.redis import interview_session as isess
from app.repositories.interview_question_repository import interview_question_repository
from app.repositories.interview_repository import interview_repository
from app.repositories.interview_report_repository import interview_report_repository
from app.repositories.outbox_repository import sync_outbox_repository
from app.repositories.resume_repository import resume_repository
from app.repositories.resume_work_experience_repository import resume_work_experience_repository
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

# 简历分析结果缓存键（简历模块维护，面试模块读取，§17.3）
_RESUME_CACHE_KEY = "resume:analysis:{resume_id}"
_RESUME_CACHE_TTL = 7 * 24 * 3600

# 面试阶段常量（§6.2）
PHASE_NOT_STARTED = "not_started"
PHASE_ANSWERING = "answering"
PHASE_ANALYZING = "analyzing"
PHASE_SUMMARIZING = "summarizing"
PHASE_COMPLETED = "completed"
PHASE_ABORTED = "aborted"

# 时长兜底（§12.1）：超90分钟当前题答完直接进入Summary；超30分钟无活动判中断
MAX_INTERVIEW_MINUTES = 90
INACTIVITY_ABORT_MINUTES = 30
# 同题分析连续失败跳过阈值（§21）
MAX_ANALYSIS_FAILURES = 2
# 同题排队复用等待窗口（秒，T2.2）：等待首个请求完成本判题并复用其结果（略高于 LLM_TIMEOUT=120s）
WAIT_IN_FLIGHT_SECONDS = 130
# 同题排队复用轮询间隔（秒，T2.2）
WAIT_IN_FLIGHT_POLL_INTERVAL = 0.5
# 报告后台生成重试次数（§13.1）
MAX_REPORT_RETRIES = 3
# 报告生成前轮询补齐异步分析的等待上限（秒，§八决策4=可行：60s，超时带"待补充"）
REPORT_ANALYSIS_WAIT_SECONDS = 60
# 报告前补齐分析的轮询间隔（秒）
REPORT_ANALYSIS_POLL_INTERVAL = 0.5
# 基础题落库顺序（大众化四维度）：技术八股(1)→项目与社会实践(2)→架构设计(4)→综合素养(3)，
# 综合素养固定放最后（排序兜底，防 LLM 输出乱序）
CATEGORY_ORDER = {1: 0, 2: 1, 4: 2, 3: 3}


class InterviewNotFoundError(Exception):
    """面试不存在或无权访问（路由层转404）。"""


class ResumeNotReadyError(Exception):
    """简历未就绪（路由层转409，code区分analyzing/analysis_failed）。"""

    def __init__(self, code: str, message: str) -> None:
        """初始化异常。

        Args:
            code: 错误码 analyzing/analysis_failed。
            message: 面向用户的提示信息。
        """
        super().__init__(message)
        self.code = code


class InterviewConflictError(Exception):
    """并发冲突/状态不符（路由层转409并携带最新状态强制同步）。"""

    def __init__(self, reason: str, state: dict | None = None) -> None:
        """初始化异常。

        Args:
            reason: 冲突原因（epoch_mismatch/version_mismatch/busy/finished）。
            state: 最新面试状态（供前端强制同步）。
        """
        super().__init__(reason)
        self.reason = reason
        self.state = state


class InterviewService:
    """面试业务编排层（同步）：会话创建、回答推进、报告生成。"""

    # ------------------------------------------------------------------
    # 创建面试（§3）
    # ------------------------------------------------------------------

    def create_interview(
        self,
        db: Session,
        cache: redis.Redis,
        user_id: int,
        resume_id: int,
        interview_type: int,
        tab_id: str,
    ) -> dict:
        """创建面试会话：简历校验 → 预生成基础题 → 初始化 Checkpoint。

        流程（§3.3/§7.2）: 简历状态硬校验（就绪才可创建）→ 建 interview
        记录（id 即 session_id）→ 操作锁内 LLM 批量出题并落库 → 初始化
        Checkpoint → 注册创建方客户端租约（epoch=1）。LLM 失败删除会话
        记录返回 503（无脏数据，§21）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端（锁/租约/Checkpoint）。
            user_id: 当前用户ID。
            resume_id: 简历ID。
            interview_type: 面试类型 1-完整 2-快速。
            tab_id: 创建方标签页唯一标识。

        Returns:
            {"interview_id", "epoch", "status", "type", "total_questions",
             "current_question"}

        Raises:
            InterviewNotFoundError: 简历不存在/非本人/已删除。
            ResumeNotReadyError: 简历分析中或分析失败。
            Exception: LLM 出题失败（上层转503）。
        """
        # 1. 简历状态硬校验（§3.3）
        resume = resume_repository.get_by_id(db, resume_id)
        if resume is None or resume.user_id != user_id or resume.is_deleted == 1:
            raise InterviewNotFoundError("简历不存在")
        if resume.status == RESUME_STATUS_PARSING:
            raise ResumeNotReadyError("analyzing", "简历正在分析中，请稍后再试")
        if resume.status == RESUME_STATUS_ERROR:
            raise ResumeNotReadyError("analysis_failed", "简历分析失败，请重试或重新上传")

        # 2. 简历上下文（缓存优先，未命中回源MySQL并回写，§4）
        resume_context = self._load_resume_context(db, cache, resume)

        # 3. 创建会话记录（id 即 session_id，§3.2）
        interview = interview_repository.create(db, user_id, resume_id, interview_type)

        # 4. 操作锁内预生成基础题（§5.4：创建面试预生成题目也属状态推进）
        token = isess.generate_lock_token()
        if not isess.acquire_lock_sync(cache, interview.id, token):
            # 刚创建的会话id不可能有竞争，防御性兜底
            db.delete(interview)
            db.commit()
            raise InterviewConflictError("busy", None)
        try:
            result = generate_questions(resume_context, interview_type)
            # 落库顺序兜底：按维度排序（八股→项目→架构→综合，综合素养固定最后）
            ordered = sorted(result.questions, key=lambda q: CATEGORY_ORDER.get(q.category, 9))
            questions = [
                {
                    "question_no": idx + 1,
                    "question_type": q.question_type,
                    "category": q.category,
                    "question_text": q.question_text,
                }
                for idx, q in enumerate(ordered)
            ]
            if not questions:
                raise ValueError("LLM未生成任何题目")
            rows = interview_question_repository.bulk_create(db, interview.id, questions)
            db.commit()
        except Exception:
            db.rollback()
            # 无脏数据：删除会话记录后向上抛（§21：创建接口503）
            interview_repository_hard_delete(db, interview.id)
            logger.exception("基础题预生成失败: interview_id=%s", interview.id)
            raise
        finally:
            isess.release_lock_sync(cache, interview.id, token)

        # 5. 注册创建方客户端租约（epoch=1）
        epoch = isess.activate_client_sync(cache, interview.id, tab_id)

        # 6. 初始化 Checkpoint（§6.2）
        now = datetime.now().isoformat()
        first = rows[0]
        checkpoint = {
            "phase": PHASE_NOT_STARTED,
            "question_index": 1,
            "current_question_id": first.id,
            "current_question": first.question_text,
            "current_answer": "",
            "answered_count": 0,
            "base_question_count": len(rows),
            "total_follow_up_used": 0,
            "started_at": now,
            "last_activity_at": now,
            "epoch": epoch,
            "analysis_fail_count": 0,
            "report_fail_count": 0,
        }
        isess.save_checkpoint_sync(cache, interview.id, checkpoint)

        return {
            "interview_id": interview.id,
            "epoch": epoch,
            "status": interview.status,
            "type": interview.type,
            "total_questions": len(rows),
            "current_question": self._question_out(rows, 0),
        }

    # ------------------------------------------------------------------
    # 状态查询 / 刷新恢复（§15）
    # ------------------------------------------------------------------

    def get_state(
        self,
        db: Session,
        cache: redis.Redis,
        user_id: int,
        interview_id: int,
        tab_id: str | None = None,
    ) -> dict:
        """查询面试当前状态（刷新恢复/超时兜底轮询，§3.4）。

        携带 tab_id 时执行客户端租约激活（同标签页幂等返回当前 epoch，
        新标签页接管 epoch+1 并 SSE 广播 taken_over，§5.6）；
        Checkpoint 丢失时由 MySQL 逐题数据重建（§6.4）；
        超过30分钟无活动自动置为已中断（§21）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。
            tab_id: 客户端标签页标识（刷新恢复必传，轮询可不传）。

        Returns:
            状态字典（phase/question_index/epoch/current_question等）。

        Raises:
            InterviewNotFoundError: 面试不存在或无权访问。
        """
        interview = self._get_owned(db, user_id, interview_id)

        # 30分钟无活动 → 自动中断（§21）
        if interview.status == INTERVIEW_STATUS_IN_PROGRESS:
            self._check_inactivity(db, cache, interview)

        # 客户端租约激活（进入/刷新面试页时）
        epoch = None
        if tab_id:
            prev_epoch = isess.get_client_epoch_sync(cache, interview_id)
            epoch = isess.activate_client_sync(cache, interview_id, tab_id)
            if prev_epoch is not None and epoch != prev_epoch:
                # 新标签页接管：SSE 广播 taken_over（旧标签页降级只读，§16）。
                # 事件体携带新持有者 tab_id：广播按用户频道分发到所有连接，
                # 接管方自己也订阅同一频道，前端凭 tab_id 过滤避免自降级。
                self._publish_sse(
                    user_id,
                    {"kind": "interview:taken_over", "session_id": interview_id,
                     "epoch": epoch, "tab_id": tab_id},
                )

        state = self._build_state(db, cache, interview)
        if epoch is not None:
            state["epoch"] = epoch
        return state

    def start_interview(
        self, db: Session, cache: redis.Redis, user_id: int, interview_id: int
    ) -> dict:
        """设备检测通过后正式启动面试（草稿态 not_started → answering，§3）。

        幂等：若已处于 answering 直接返回当前状态；已完成/中断面试不可再启动。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。

        Returns:
            最新状态字典（phase=answering）。

        Raises:
            InterviewNotFoundError: 面试不存在或无权访问。
            InterviewConflictError: 面试已完成/中断（409）。
        """
        interview = self._get_owned(db, user_id, interview_id)
        if interview.status != INTERVIEW_STATUS_IN_PROGRESS:
            raise InterviewConflictError(
                "finished", self._build_state(db, cache, interview)
            )
        questions = list(interview_question_repository.list_by_interview(db, interview_id))
        checkpoint = self._load_or_rebuild_checkpoint(db, cache, interview, questions)
        if checkpoint.get("phase") == PHASE_NOT_STARTED:
            # 草稿态推进为作答态：定位首题（§6.4 与全量重建同逻辑，无已答题）。
            # started_at 必须在正式启动时重置为当前时间——若沿用创建时刻，
            # 用户隔 90 分钟后再进入会被 _elapsed_over_limit 误判超时，
            # 导致"答一题即截止并生成报告"（BUG3）。
            now_iso = datetime.now().isoformat()
            checkpoint["phase"] = PHASE_ANSWERING
            checkpoint["question_index"] = 1
            if questions:
                checkpoint["current_question_id"] = questions[0].id
                checkpoint["current_question"] = questions[0].question_text
            checkpoint["current_answer"] = ""
            checkpoint["started_at"] = now_iso
            checkpoint["last_activity_at"] = now_iso
            isess.save_checkpoint_sync(cache, interview.id, checkpoint)
            # T3.8：基础题按发问顺序入队（Redis List 镜像，备份/恢复防漏题）
            isess.init_queue(cache, interview.id, [q.id for q in questions])
            logger.info("面试正式启动: interview_id=%s", interview.id)
        state = self._state_from(db, interview, checkpoint, questions)
        state["epoch"] = isess.get_client_epoch_sync(cache, interview.id) or 1
        return state

    # ------------------------------------------------------------------
    # 提交回答（§8.4/§9/§10/§11/§12）
    # ------------------------------------------------------------------

    def submit_answer(
        self,
        db: Session,
        cache: redis.Redis,
        user_id: int,
        interview_id: int,
        question_index: int,
        answer: str,
        tab_epoch: int,
        answer_duration: int | None = None,
    ) -> dict:
        """提交回答（T3.2 受理化）：毫秒级"校验 + checkpoint analyzing + 投事件 + 秒回已受理"。

        判题/落库/推进全部由 Answer Consumer（interview.answer.submitted 队列）异步
        完成：请求线程不再调 LLM、不再写业务表。前端收到 accepted/phase=analyzing
        后进入轮询，等 checkpoint 推进（interview:judged SSE 加速）。

        校验顺序（§5.7 保留）: epoch 租约 → 幂等预检（已落库题直接返回既有结果，
        含面试已结束场景，超时重试安全，§5.9）→ 状态校验 → analyzing 去重 →
        版本校验 → 投递事件。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。
            question_index: 所答题目题序（状态版本token）。
            answer: 回答文本。
            tab_epoch: 客户端租约 epoch。
            answer_duration: 回答时长（秒，可选）。

        Returns:
            {"interview_id", "question_index", "analysis", "duplicated", "accepted",
             "phase", "next_question"}（accepted=True 表示已受理判题中）。

        Raises:
            InterviewNotFoundError: 面试不存在或无权访问。
            InterviewConflictError: epoch/版本不符或面试已结束（真冲突保留 409）。
        """
        interview = self._get_owned(db, user_id, interview_id)
        finished = interview.status != INTERVIEW_STATUS_IN_PROGRESS

        # ① epoch 租约校验（廉价校验先行，§5.7）。
        # 仅进行中面试需要双开裁决；已结束面试（租约已随清理流程删除）
        # 跳过本校验，直接走幂等路径，保证最后一题超时重试安全（§5.9）。
        if not finished:
            current_epoch = isess.get_client_epoch_sync(cache, interview_id)
            if current_epoch is None or current_epoch != tab_epoch:
                raise InterviewConflictError(
                    "epoch_mismatch", self._build_state(db, cache, interview)
                )

        # ①.5 幂等预检（§5.9）：已作答题直接返回既有结果（Consumer 已落库，不重跑）。
        questions = list(interview_question_repository.list_by_interview(db, interview_id))
        if 1 <= question_index <= len(questions):
            target = questions[question_index - 1]
            if target.user_answer is not None:
                checkpoint = self._load_or_rebuild_checkpoint(db, cache, interview, questions)
                return self._idempotent_response(
                    db, cache, interview, checkpoint, questions, target, question_index
                )

        # 状态校验：面试已结束且该题未答 → 不可受理
        if finished:
            raise InterviewConflictError(
                "finished", self._build_state(db, cache, interview)
            )

        # ② 同题已受理/判题中（analyzing 且题序一致）→ 返回已受理，前端轮询等待
        #    （不再重复投事件，避免重复判题；旧"409 busy"在提交链路消失，T3.5）。
        #    analyzing 残留超时（判题可能崩溃且事件已消费）→ 重新受理并重投事件。
        checkpoint = self._load_or_rebuild_checkpoint(db, cache, interview, questions)
        if checkpoint.get("phase") == PHASE_ANALYZING and checkpoint.get("question_index") == question_index:
            if self._analyzing_stale(checkpoint):
                logger.warning(
                    "analyzing 残留超时，重新受理重投 interview_id=%s question_index=%s",
                    interview_id, question_index,
                )
            else:
                return self._accepted_response(interview, question_index, checkpoint)

        # ③ 版本校验（§5.5）：题序必须与 Checkpoint 当前题一致
        if checkpoint["question_index"] != question_index:
            raise InterviewConflictError(
                "version_mismatch", self._state_from(db, interview, checkpoint, questions)
            )

        # ④ 置 analyzing（暂存 answer：供崩溃恢复/去重/前端轮询）→ 同一事务投递事件
        checkpoint.update(
            {
                "phase": PHASE_ANALYZING,
                "current_answer": answer,
                "epoch": tab_epoch,
                "last_activity_at": datetime.now().isoformat(),
            }
        )
        isess.save_checkpoint_sync(cache, interview_id, checkpoint)
        self._dispatch_answer_submitted(
            db, interview, target, question_index, answer, tab_epoch, answer_duration
        )
        db.commit()
        return self._accepted_response(interview, question_index, checkpoint)

    def _accepted_response(self, interview: Interview, question_index: int, checkpoint: dict) -> dict:
        """已受理响应（T3.2）：判题中，前端据此进入轮询等待。"""
        return {
            "interview_id": interview.id,
            "question_index": question_index,
            "analysis": {
                "score": 0,
                "comment": "判题中，稍后展示",
                "correctness": "",
                "technical_depth": 0,
                "completeness": 0,
                "logic": 0,
                "key_points": [],
                "weaknesses": [],
            },
            "duplicated": False,
            "accepted": True,
            "phase": PHASE_ANALYZING,
            "next_question": None,
        }

    def _analyzing_stale(self, checkpoint: dict) -> bool:
        """analyzing 残留判据：last_activity_at 距今超过处理窗口（判题可能已崩溃）。

        Args:
            checkpoint: Checkpoint状态。

        Returns:
            True=残留超时可重新受理。
        """
        from datetime import datetime as _dt

        last = checkpoint.get("last_activity_at")
        if not last:
            return True
        try:
            last_dt = _dt.fromisoformat(str(last))
        except ValueError:
            return True
        return (_dt.now() - last_dt).total_seconds() > WAIT_IN_FLIGHT_SECONDS

    def _dispatch_answer_submitted(
        self,
        db: Session,
        interview: Interview,
        target: "InterviewQuestion",
        question_index: int,
        answer: str,
        tab_epoch: int,
        answer_duration: int | None,
    ) -> None:
        """投递面试回答受理事件（T3.1，Transactional Outbox，与 analyzing 状态同事务）。

        由 Answer Consumer 消费：判题（Fast Decision）→ 追问生成 → user_answer/追问
        落库 → checkpoint 推进 → SSE。请求线程不等待，毫秒级返回已受理。

        Args:
            db: 数据库同步会话（当前事务内）。
            interview: 面试会话ORM对象。
            target: 当前题目ORM对象。
            question_index: 所答题目题序。
            answer: 回答文本。
            tab_epoch: 客户端租约epoch。
            answer_duration: 回答时长（秒）。
        """
        sync_outbox_repository.insert_event(
            db,
            event_type="interview.answer.submitted",
            aggregate_type="interview",
            aggregate_id=str(interview.id),
            payload={
                "interview_id": interview.id,
                "user_id": interview.user_id,
                "question_index": question_index,
                "question_id": target.id,
                "question_text": target.question_text,
                "answer": answer,
                "answer_duration": answer_duration,
                "tab_epoch": tab_epoch,
                "resume_id": interview.resume_id or 0,
                "priority_ref": f"interview:{interview.id}:q{question_index}",
            },
        )

    def process_answer_submitted(
        self,
        cache: redis.Redis,
        interview_id: int,
        question_index: int,
        answer: str,
        tab_epoch: int,
        answer_duration: int | None,
    ) -> bool:
        """T3.3 Answer Consumer 编排入口（独立DB会话，消费端经 asyncio.to_thread 执行）。

        判题（Fast Decision）→ 追问生成（即异步落库，T3.10）→ 短锁推进落库/checkpoint
        → SSE interview:judged。复用阶段二拆分的 _submit_no_lock（无锁判题 + 短锁推进），
        请求线程早已毫秒级返回"已受理"。

        Args:
            cache: 同步Redis客户端。
            interview_id: 面试会话ID。
            question_index: 所答题目题序。
            answer: 回答文本。
            tab_epoch: 客户端租约epoch。
            answer_duration: 回答时长（秒）。

        Returns:
            True=消费成功（含幂等跳过/冲突跳过）；False=业务处理失败（日志记录，
            由前端轮询超时重提/受理重投兜底恢复）。
        """
        db = SyncSessionLocal()
        try:
            interview = interview_repository.get_by_id(db, interview_id)
            if interview is None or interview.is_deleted == 1:
                logger.warning(
                    "回答事件面试不存在/已删除，跳过 interview_id=%s", interview_id
                )
                return True

            # 幂等（T3.5）：该题已落库（重复投递/受理重投）→ 跳过，不重复判题
            questions = list(interview_question_repository.list_by_interview(db, interview_id))
            if (
                1 <= question_index <= len(questions)
                and questions[question_index - 1].user_answer is not None
            ):
                logger.info(
                    "回答事件幂等跳过 interview_id=%s question_index=%s",
                    interview_id, question_index,
                )
                return True

            # 编排（复用阶段二拆分：无锁判题 + 短锁推进）
            result = self._submit_no_lock(
                db, cache, interview, question_index, answer, tab_epoch, answer_duration
            )

            # SSE 判题完成（前端轮询兜底，SSE 加速进入下一题，T3.4）
            # 事件携带下一题数据：前端无需再额外请求状态即可直接进入下一题，
            # 网络面板不再出现"像轮询"的 getInterviewState 请求（SSE 为主通道）
            edged = result.get("next_question")
            self._publish_sse(
                interview.user_id,
                {
                    "kind": "interview:judged",
                    "session_id": interview_id,
                    "question_index": question_index,
                    "phase": result.get("phase"),
                    "next_question": edged,
                },
            )
            return True
        except InterviewConflictError as exc:
            # 版本/状态已变（并发推进/中断等）：视为幂等跳过，不判失败
            logger.info(
                "回答事件消费冲突跳过 interview_id=%s question_index=%s reason=%s",
                interview_id, question_index, exc.reason,
            )
            return True
        except Exception:
            logger.exception(
                "回答事件消费失败 interview_id=%s question_index=%s",
                interview_id, question_index,
            )
            return False
        finally:
            db.close()

    def _submit_no_lock(
        self,
        db: Session,
        cache: redis.Redis,
        interview: Interview,
        question_index: int,
        answer: str,
        tab_epoch: int,
        answer_duration: int | None,
    ) -> dict:
        """T2.1 无锁段编排：判题/追问在无锁状态下执行，锁内仅毫秒级推进。

        与旧 _advance_with_lock 的差异：
            - Fast Decision 与追问规则判定移出操作锁（LLM 最长 120s 不再持锁）；
            - 操作锁只在 _persist_and_advance_locked 中持有（版本复校 + 单事务
              落库 + checkpoint 推进，毫秒级写）；
            - 同题并发由入口 processing 互斥标记（T2.2）拦截，不再 409 busy，
              排队者等待首请求完成并复用其结果。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。
            question_index: 所答题目题序。
            answer: 回答文本。
            tab_epoch: 客户端租约epoch。
            answer_duration: 回答时长（秒）。

        Returns:
            提交回答响应字典。

        Raises:
            InterviewConflictError: 版本不符或推进锁竞争（409，调用方清 processing）。
        """
        interview_id = interview.id
        questions = list(interview_question_repository.list_by_interview(db, interview_id))
        checkpoint = self._load_or_rebuild_checkpoint(db, cache, interview, questions)

        # 越界防御
        if question_index < 1 or question_index > len(questions):
            raise InterviewConflictError("version_mismatch", self._state_from(db, interview, checkpoint, questions))
        target = questions[question_index - 1]

        # 幂等检查（§5.9，并发窗口二次兜底）：该题已作答 → 直接返回既有结果
        if target.user_answer is not None:
            return self._idempotent_response(db, cache, interview, checkpoint, questions, target, question_index)

        # 状态版本校验（§5.5，乐观；锁内推进段还会复校）
        if checkpoint["question_index"] != question_index:
            raise InterviewConflictError(
                "version_mismatch", self._state_from(db, interview, checkpoint, questions)
            )

        # 写入 analyzing 状态（崩溃后可凭未落库题目重试，§21；processing 标记 TTL 兜底）
        checkpoint.update(
            {
                "phase": PHASE_ANALYZING,
                "current_answer": answer,
                "epoch": tab_epoch,
                "last_activity_at": datetime.now().isoformat(),
            }
        )
        isess.save_checkpoint_sync(cache, interview_id, checkpoint)

        # 无锁判题（规则判问尽 + 单次流式 LLM 产出追问，LLM 在消费端执行不持锁，T2.1/P1）
        follow_up_text, corrected_answer = self._judge_no_lock(
            db, cache, interview, checkpoint, target, question_index, answer
        )

        # 短持锁推进（毫秒级：锁内版本复校 + 单事务落库/推进 + checkpoint）
        token = isess.generate_lock_token()
        if not isess.acquire_lock_sync(cache, interview_id, token):
            # 推进锁竞争（abort/删除等并发，窗口极小）：交还调用方清理标记，前端幂等重试
            raise InterviewConflictError("busy", self._build_state(db, cache, interview))
        try:
            return self._persist_and_advance_locked(
                db, cache, interview, checkpoint, questions, target, question_index,
                tab_epoch, answer_duration, follow_up_text, corrected_answer,
            )
        finally:
            isess.release_lock_sync(cache, interview_id, token)

    def _judge_no_lock(
        self,
        db: Session,
        cache: redis.Redis,
        interview: Interview,
        checkpoint: dict,
        target: InterviewQuestion,
        question_index: int,
        answer: str,
    ) -> tuple[str | None, str]:
        """P1 判题链：规则判问尽 + 单次流式 LLM 产出追问（只读 DB，不持操作锁）。

        与旧 run_fast_decision 判定链的差异：
            - end/下一基础 由规则判定（unanswered_base_after / 时长 / 追问上限），不依赖 LLM；
            - 可追问候选时，单个 LLM 以【流式】输出追问文本或 NONE（回答质量判断隐含
              在输出中），Consumer 边收集边经 SSE judge_stream 推送前端打字机（P1）；
            - 判题前统一经优化后的纠错 LLM 做最小文本规整（不区分语音/键盘，混合输入安全）。

        LLM 连续失败 2 次跳过追问继续（§21）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。
            checkpoint: 当前Checkpoint状态。
            target: 当前题目ORM。
            question_index: 所答题目题序。
            answer: 回答文本。

        Returns:
            (follow_up_text, corrected_answer)；follow_up_text 为空=无追问（走下一基础/结束）。

        Raises:
            Exception: 流式追问 LLM 失败且未达跳过阈值（调用方接管，前端可重试）。
        """
        interview_id = interview.id
        resume = resume_repository.get_by_id(db, interview.resume_id)
        resume_context = self._load_resume_context(db, cache, resume)

        # 统一文本规整（语音转写+键盘修正混合输入无法二分，不做 voice 条件判断）：
        # 每次判题前经优化后的纠错 LLM 做最小规整（无识别错误特征则原样返回，P1）
        corrected_answer = correct_speech_text(target.question_text, answer, resume_context)

        # 基础题快照与计数（规则判定是否问尽 / 追问上限，§10/§12）
        questions = list(interview_question_repository.list_by_interview(db, interview_id))
        base_questions = [
            {
                "question_no": q.question_no,
                "question_id": q.id,
                "question_type": q.question_type,
                "category": q.category,
                "question_text": q.question_text,
            }
            for q in questions
            if q.is_follow_up == 0
        ]
        base_count = len(base_questions)
        total_follow_up_now = interview_question_repository.count_follow_up_total(db, interview_id)
        unanswered_base_after = len(
            [q for q in base_questions if q["question_no"] > target.question_no and q["question_no"] <= base_count]
        )
        elapsed_over = self._elapsed_over_limit(cache, interview_id, checkpoint, MAX_INTERVIEW_MINUTES)

        # 规则：可追问候选（未超时 / 全场追问未达上限 / 本基础题尚未追问过）
        follow_up_text: str | None = None
        parent = target if target.is_follow_up == 0 else self._find_parent(questions, target)
        per_base = (
            interview_question_repository.count_follow_up_by_parent(db, parent.id)
            if parent is not None else 1
        )
        can_follow_up = (
            not elapsed_over
            and per_base < 1
            and total_follow_up_now < base_count
            and bool(corrected_answer.strip())
        )

        try:
            if can_follow_up:
                # 单次流式 LLM：追问文本或 NONE（回答质量判断隐含在输出中）
                follow_up_text = self._stream_follow_up(
                    cache, interview, target.question_text, corrected_answer, resume_context
                )
            checkpoint["analysis_fail_count"] = 0
            # 无锁段同样落 Checkpoint：失败计数归零需持久化（推进段以最新 load 为准，T2.1）
            isess.save_checkpoint_sync(cache, interview_id, checkpoint)
        except Exception:
            checkpoint["analysis_fail_count"] = int(checkpoint.get("analysis_fail_count", 0)) + 1
            if checkpoint["analysis_fail_count"] >= MAX_ANALYSIS_FAILURES:
                # 连续2次追问生成失败：跳过追问并继续（§21），不留死锁态
                logger.exception(
                    "追问生成连续失败跳过: interview_id=%s question_index=%s",
                    interview_id, question_index,
                )
                follow_up_text = None
                isess.save_checkpoint_sync(cache, interview_id, checkpoint)
            else:
                # 回退 phase=answering 允许重试（§21），异常向上抛（调用方清 processing 标记）
                checkpoint["phase"] = PHASE_ANSWERING
                isess.save_checkpoint_sync(cache, interview_id, checkpoint)
                raise

        return follow_up_text, corrected_answer

    def _stream_follow_up(
        self,
        cache: redis.Redis,
        interview: Interview,
        question: str,
        answer: str,
        resume_context: dict,
    ) -> str | None:
        """流式收集追问文本（P1 预览已废弃，v1.3：不再推送 judge_stream）。

        仍以流式方式收集 LLM 输出以获得完整追问文本（判定质量/生成 NONE），但
        取消逐段 SSE 推送：判题完成后由 judged 事件一次性携带下一题（追问）直达
        前端，题目卡仅打印一次，避免"判题中预览 + 进入下一题再打一遍"的重复体验。

        Args:
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。
            question: 当前题目文本。
            answer: 用户回答（纠错后或原文）。
            resume_context: 简历结构化上下文。

        Returns:
            追问文本（≤300字）；NONE/空返回 None（无追问）。
        """
        import time

        full: list[str] = []
        for chunk in generate_follow_up_stream(question, answer, resume_context):
            full.append(chunk)

        text = "".join(full).strip()
        if is_follow_up_none(text):
            return None
        return text[:300]

    def _persist_and_advance_locked(
        self,
        db: Session,
        cache: redis.Redis,
        interview: Interview,
        checkpoint: dict,
        questions: list[InterviewQuestion],
        target: InterviewQuestion,
        question_index: int,
        tab_epoch: int,
        answer_duration: int | None,
        follow_up_text: str | None,
        corrected_answer: str,
    ) -> dict:
        """T2.1 短持锁推进：锁内版本复校 + 单事务落库 + checkpoint 推进（毫秒级）。

        判题结果（follow_up_text/corrected_answer）已由无锁段 _judge_no_lock
        求得，本方法不调 LLM；锁内只做版本复校与状态写，持锁窗口毫秒级。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。
            checkpoint: 无锁段装载的Checkpoint（锁内以最新复载为准）。
            questions: 题目快照（锁内以最新复载为准）。
            target: 当前题目ORM（锁内以最新快照取对应题）。
            question_index: 所答题目题序。
            tab_epoch: 客户端租约epoch（回写Checkpoint）。
            answer_duration: 回答时长（秒）。
            follow_up_text: 裁定生成的追问文本（无则 None）。
            corrected_answer: 纠错后的回答文本（落库用）。

        Returns:
            提交回答响应字典。

        Raises:
            InterviewConflictError: 锁内复校发现状态已变（version_mismatch/finished）。
        """
        interview_id = interview.id

        # 锁内版本复校：无锁判题期间状态可能被其他流程变更（inactivity abort、双开接管等）
        latest_questions = list(interview_question_repository.list_by_interview(db, interview_id))
        latest = self._load_or_rebuild_checkpoint(db, cache, interview, latest_questions)
        if latest.get("phase") != PHASE_ANALYZING or latest.get("question_index") != question_index:
            re_target = latest_questions[question_index - 1] if 1 <= question_index <= len(latest_questions) else None
            if re_target is not None and re_target.user_answer is not None:
                return self._idempotent_response(
                    db, cache, interview, latest, latest_questions, re_target, question_index
                )
            raise InterviewConflictError(
                "version_mismatch", self._state_from(db, interview, latest, latest_questions)
            )
        checkpoint = latest
        questions = latest_questions
        target = questions[question_index - 1]

        # 单事务：落库本题 user_answer（+ 可能追问题）+ 投递异步分析 outbox（§14.2/§六）
        # user_answer 落纠错后文本，保证历史/报告与异步分析基于同一份文本
        try:
            target.user_answer = corrected_answer
            if answer_duration is not None:
                target.answer_duration = answer_duration
            db.flush()

            follow_up_row = None
            if follow_up_text:
                follow_up_row = interview_question_repository.create_follow_up(
                    db,
                    interview_id,
                    question_no=target.question_no,
                    question_type=target.question_type,
                    category=target.category,
                    parent_question_id=target.id,
                    question_text=follow_up_text,
                )

            # 异步全量分析（OUTBOX 同事务原子投递；Worker 补 ai_score/ai_comment，§六）
            self._dispatch_async_analysis(
                db, interview_id, int(target.id), int(target.question_no),
                target.question_text, corrected_answer, answer_duration, int(interview.resume_id or 0),
                int(interview.user_id),
            )

            db.commit()
        except Exception:
            db.rollback()
            checkpoint["phase"] = PHASE_ANSWERING
            isess.save_checkpoint_sync(cache, interview_id, checkpoint)
            raise

        # 刷新题目快照（含新追问），确定下一题（§12）
        questions = list(interview_question_repository.list_by_interview(db, interview_id))
        if follow_up_row is not None:
            next_q = follow_up_row
        else:
            next_q = self._next_base_question(questions, target.question_no)
        # T3.8/T3.9：推进后同步问题队列镜像（当前题出队；追问插队首，队首即下一题）
        try:
            isess.remove_from_queue(cache, interview_id, target.id)
            if follow_up_row is not None:
                isess.enqueue_head(cache, interview_id, follow_up_row.id)
        except Exception:
            logger.exception("问题队列镜像同步失败: interview_id=%s", interview_id)
        elapsed_over = self._elapsed_over_limit(cache, interview_id, checkpoint, MAX_INTERVIEW_MINUTES)

        answered_count = interview_question_repository.count_answered(db, interview_id)
        total_follow_up = interview_question_repository.count_follow_up_total(db, interview_id)

        if next_q is not None and not elapsed_over:
            # 还有下一题（追问或下一基础题）
            next_idx = self._ordinal_of(questions, next_q.id)
            interview_repository.update_progress(
                db, interview_id,
                current_question_index=next_q.question_no,
                follow_up_count=total_follow_up,
            )
            db.commit()
            checkpoint.update(
                {
                    "phase": PHASE_ANSWERING,
                    "question_index": next_idx,
                    "current_question_id": next_q.id,
                    "current_question": next_q.question_text,
                    "current_answer": "",
                    "answered_count": answered_count,
                    "total_follow_up_used": total_follow_up,
                    "epoch": tab_epoch,
                }
            )
            isess.save_checkpoint_sync(cache, interview_id, checkpoint)
            phase, next_out = PHASE_ANSWERING, self._question_out(questions, next_idx - 1)
        else:
            # 终止条件满足：status=1 → 异步生成报告（§13.1，MQ Worker）
            total_duration = self._total_duration(questions)
            interview_repository.finish(
                db, interview_id,
                total_score=0,  # 占位，报告生成后回写真实总分
                total_duration=total_duration,
                follow_up_count=total_follow_up,
            )
            # 同一事务投递报告生成事件（§13.1 MQ 异步化，Worker 生成后消息通知）
            self._dispatch_report_generation(
                db, interview_id, int(interview.user_id), int(interview.resume_id or 0)
            )
            db.commit()
            checkpoint.update(
                {
                    "phase": PHASE_SUMMARIZING,
                    "answered_count": answered_count,
                    "total_follow_up_used": total_follow_up,
                    "epoch": tab_epoch,
                }
            )
            isess.save_checkpoint_sync(cache, interview_id, checkpoint)
            phase, next_out = PHASE_SUMMARIZING, None
            # 最后一题回答完成：SSE 通知进入报告等待（§16）
            self._publish_sse(
                interview.user_id,
                {"kind": "interview:completed", "session_id": interview_id},
            )

        # 全量分析异步化：同步响应不再携带逐题详评，标记为"待异步分析"（§七/§八决策2）
        analysis_out = {
            "score": 0,
            "comment": "分析中，稍后展示",
            "correctness": "",
            "technical_depth": 0,
            "completeness": 0,
            "logic": 0,
            "key_points": [],
            "weaknesses": [],
        }
        return {
            "interview_id": interview_id,
            "question_index": question_index,
            "analysis": analysis_out,
            "duplicated": False,
            "phase": phase,
            "next_question": next_out,
        }

    def _dispatch_async_analysis(
        self,
        db: Session,
        interview_id: int,
        question_id: int,
        question_no: int,
        question_text: str,
        answer: str,
        answer_duration: int | None,
        resume_id: int,
        user_id: int,
    ) -> None:
        """投递面试回答异步分析事件（Transactional Outbox，§5.1）。

        与本题 user_answer 落库同一事务原子提交：Worker 消费后在 MySQL 补
        ai_score/ai_comment，前端/同步 API 不等待（§六：返回下一题不等待分析）。

        Args:
            db: 数据库同步会话（当前事务内）。
            interview_id: 面试会话ID。
            question_id: 题目ID。
            question_no: 基础题号。
            question_text: 题目文本。
            answer: 用户回答。
            answer_duration: 回答时长（秒）。
            resume_id: 简历ID（Worker 加载简历上下文）。
            user_id: 用户ID。
        """
        priority_ref = f"interview:{interview_id}:q{question_id}"
        sync_outbox_repository.insert_event(
            db,
            event_type="interview.analysis",
            aggregate_type="interview",
            aggregate_id=str(interview_id),
            payload={
                "interview_id": interview_id,
                "user_id": user_id,
                "question_id": question_id,
                "question_no": question_no,
                "question_text": question_text,
                "answer": answer,
                "answer_duration": answer_duration,
                "resume_id": resume_id,
                "priority_ref": priority_ref,
            },
        )

    def _dispatch_report_generation(
        self,
        db: Session,
        interview_id: int,
        user_id: int,
        resume_id: int,
    ) -> None:
        """投递面试报告生成事件（Transactional Outbox，§13.1 MQ 异步化）。

        与面试 finish 落库同一事务原子提交：Worker 消费后生成报告并消息通知，
        报告生成不再占用 API 进程线程，用户无需在回答页等待。

        Args:
            db: 数据库同步会话（当前事务内）。
            interview_id: 面试会话ID。
            user_id: 面试所属用户ID（Worker 通知用）。
            resume_id: 简历ID（Worker 加载简历上下文）。
        """
        sync_outbox_repository.insert_event(
            db,
            event_type="interview.report.generate",
            aggregate_type="interview",
            aggregate_id=str(interview_id),
            payload={
                "interview_id": interview_id,
                "user_id": user_id,
                "resume_id": resume_id,
            },
        )

    def _wait_analysis_complete(self, db: Session, interview_id: int) -> None:
        """报告生成前轮询等待异步分析补齐（§八决策4=可行，60s 上限）。

        逐题检查 ai_score：已答但未分析完的题在等待期内补齐；超时后不再阻塞，
        由报告组装时对缺分析分的题打"待补充"标记（§六：报告依赖完整性兜底）。

        Args:
            db: 数据库同步会话。
            interview_id: 面试会话ID。
        """
        import time

        deadline = time.monotonic() + REPORT_ANALYSIS_WAIT_SECONDS
        while time.monotonic() < deadline:
            questions = list(interview_question_repository.list_by_interview(db, interview_id))
            pending = [q for q in questions if q.user_answer is not None and q.ai_score is None]
            if not pending:
                return
            db.expire_all()
            time.sleep(REPORT_ANALYSIS_POLL_INTERVAL)
        logger.info(
            "报告前异步分析等待超时，缺分析题将带待补充标记: interview_id=%s",
            interview_id,
        )

    def _idempotent_response(
        self,
        db: Session,
        cache: redis.Redis,
        interview: Interview,
        checkpoint: dict,
        questions: list[InterviewQuestion],
        target: InterviewQuestion,
        question_index: int,
    ) -> dict:
        """幂等命中：返回既有分析结果与当前应展示的下一题（§5.9）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。
            checkpoint: 当前Checkpoint状态。
            questions: 发问顺序题目快照。
            target: 已分析的题目ORM对象。
            question_index: 请求题序。

        Returns:
            提交回答响应字典（duplicated=True）。
        """
        state = self._state_from(db, interview, checkpoint, questions)
        next_q = state.get("current_question")
        # 异步分析：ai_score 未落库说明 Worker 尚未完成 → 返回"分析中"
        if target.ai_score is None:
            score, comment = 0, "分析中，稍后展示"
        else:
            score, comment = target.ai_score, target.ai_comment or ""
        return {
            "interview_id": interview.id,
            "question_index": question_index,
            "analysis": {
                "score": score,
                "comment": comment,
                "correctness": "",
                "technical_depth": 0,
                "completeness": 0,
                "logic": 0,
                "key_points": [],
                "weaknesses": [],
            },
            "duplicated": True,
            "phase": state["phase"],
            "next_question": next_q,
        }

    # ------------------------------------------------------------------
    # 主动放弃（§21）
    # ------------------------------------------------------------------

    def abort(
        self,
        db: Session,
        cache: redis.Redis,
        user_id: int,
        interview_id: int,
        tab_epoch: int,
    ) -> None:
        """主动放弃面试：status=2，已答题目与评分保留，清理租约。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。
            tab_epoch: 客户端租约epoch。

        Raises:
            InterviewNotFoundError: 面试不存在或无权访问。
            InterviewConflictError: epoch不符或面试已结束。
        """
        interview = self._get_owned(db, user_id, interview_id)
        if interview.status != INTERVIEW_STATUS_IN_PROGRESS:
            raise InterviewConflictError("finished", self._build_state(db, cache, interview))

        current_epoch = isess.get_client_epoch_sync(cache, interview_id)
        if current_epoch is None or current_epoch != tab_epoch:
            raise InterviewConflictError("epoch_mismatch", self._build_state(db, cache, interview))

        token = isess.generate_lock_token()
        if not isess.acquire_lock_sync(cache, interview_id, token):
            raise InterviewConflictError("busy", self._build_state(db, cache, interview))
        try:
            interview_repository.abort(db, interview_id)
            db.commit()
            checkpoint = isess.load_checkpoint_sync(cache, interview_id) or {}
            checkpoint.update({"phase": PHASE_ABORTED})
            isess.save_checkpoint_sync(cache, interview_id, checkpoint)
        finally:
            # 清理客户端租约与面试图检查点（v2，§14.4）；Checkpoint 保留供回看
            isess.clear_client_sync(cache, interview_id)
            isess.delete_queue(cache, interview_id)
            invalidate_checkpoint(interview_id)
            isess.release_lock_sync(cache, interview_id, token)

    # ------------------------------------------------------------------
    # 报告查询与生成（§13）
    # ------------------------------------------------------------------

    def get_report(self, db: Session, cache: redis.Redis, user_id: int, interview_id: int) -> dict:
        """查询面试报告（未生成时惰性兜底触发一次并返回generating，§13.1）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。

        Returns:
            {"status": generating/ready/failed/invalid, "report": 报告或None}。

        Raises:
            InterviewNotFoundError: 面试不存在或无权访问。
        """
        interview = self._get_owned(db, user_id, interview_id)
        if interview.status == INTERVIEW_STATUS_INTERRUPTED:
            return {"status": "invalid", "report": None}
        if interview.status == INTERVIEW_STATUS_IN_PROGRESS:
            return {"status": "invalid", "report": None}

        report = interview_report_repository.get_by_interview(db, interview_id)
        if report is not None:
            return {"status": "ready", "report": report}

        # 未生成：失败次数已达上限 → failed（等待手动regenerate）
        checkpoint = isess.load_checkpoint_sync(cache, interview_id) or {}
        if int(checkpoint.get("report_fail_count", 0)) >= MAX_REPORT_RETRIES:
            return {"status": "failed", "report": None}

        # 报告由 MQ Worker 异步生成（§13.1），此处仅返回 generating 状态，
        # 生成完成后 Worker 消息通知 + SSE 推送（前端无需在回答页干等）
        return {"status": "generating", "report": None}

    def regenerate_report(self, db: Session, cache: redis.Redis, user_id: int, interview_id: int) -> str:
        """报告手动重试（LLM失败后暴露的regenerate端点，§13.1）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。

        Returns:
            状态字符串 generating。

        Raises:
            InterviewNotFoundError: 面试不存在或无权访问。
            InterviewConflictError: 面试未完成（status≠1）不可生成报告。
        """
        interview = self._get_owned(db, user_id, interview_id)
        if interview.status != INTERVIEW_STATUS_COMPLETED:
            raise InterviewConflictError("not_finished", self._build_state(db, cache, interview))

        # 重置失败计数后投递 MQ 事件重新生成（§13.1，Worker 生成后消息通知）
        checkpoint = isess.load_checkpoint_sync(cache, interview_id) or {}
        checkpoint["report_fail_count"] = 0
        isess.save_checkpoint_sync(cache, interview_id, checkpoint)
        self._dispatch_report_generation(
            db, interview_id, int(interview.user_id), int(interview.resume_id or 0)
        )
        db.commit()
        return "generating"

    def generate_report_background(self, cache: redis.Redis, interview_id: int) -> bool:
        """报告生成任务（MQ Worker 经 asyncio.to_thread 调用，操作锁保护，§13.1）。

        独立DB会话 + 最多3次重试；成功后落库报告、回写总分、phase=completed
        并 SSE 推送 report_ready；全部失败保留题目数据等待手动重试。
        由 InterviewReportConsumer 调用，不再占用 API 进程线程。

        Args:
            cache: 同步Redis客户端。
            interview_id: 面试会话ID。

        Returns:
            是否本次成功生成报告（True）。报告已存在/面试不合法/锁竞争返回 False，
            由调用方（Worker）决定是否发送失败通知。
        """
        db = SyncSessionLocal()
        try:
            interview = interview_repository.get_by_id(db, interview_id)
            if interview is None or interview.status != INTERVIEW_STATUS_COMPLETED:
                return False
            if interview_report_repository.get_by_interview(db, interview_id) is not None:
                return False

            token = isess.generate_lock_token()
            if not isess.acquire_lock_sync(cache, interview_id, token):
                return False
            try:
                self._generate_report_with_retry(db, cache, interview)
            finally:
                isess.release_lock_sync(cache, interview_id, token)
            return True
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 面试记录列表 / 逐题详情（历史页与报告页对接）
    # ------------------------------------------------------------------

    def delete_record(
        self, db: Session, cache: redis.Redis, user_id: int, interview_id: int
    ) -> None:
        """软删除面试记录（草稿/进行中/已中断/已完成均可删除）。

        仅标记 is_deleted=1，保留题目与报告行——控制台平均分/完成数统计
        仍计入已删记录（用户要求删除不影响统计）。删除后清理 Redis
        Checkpoint/租约/锁，并移除关联的面试就绪通知（消息不属于统计）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。

        Raises:
            InterviewNotFoundError: 面试不存在或无权访问。
            InterviewConflictError: 删除并发冲突（409）。
        """
        interview = self._get_owned(db, user_id, interview_id)
        if interview.is_deleted == 1:
            raise InterviewConflictError("already_deleted", None)

        token = isess.generate_lock_token()
        if not isess.acquire_lock_sync(cache, interview_id, token):
            raise InterviewConflictError("busy", None)
        try:
            from sqlalchemy import delete as sa_delete

            from app.models.message import Message
            # 软删除面试记录（保留题目/报告/总分，统计不受影响）
            interview_repository.soft_delete(db, interview_id)
            # 移除关联的面试就绪通知（related_type=4-interview，消息不属于统计）
            db.execute(
                sa_delete(Message).where(
                    Message.user_id == user_id,
                    Message.related_type == 4,
                    Message.related_id == interview_id,
                )
            )
            db.commit()
        finally:
            isess.clear_client_sync(cache, interview_id)
            isess.delete_checkpoint_sync(cache, interview_id)
            isess.delete_queue(cache, interview_id)
            isess.release_lock_sync(cache, interview_id, token)
        logger.info("软删除面试记录: interview_id=%s", interview_id)

    def list_interviews(
        self, db: Session, cache: redis.Redis, user_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        """分页查询用户面试记录（按ID倒序，含报告就绪标志）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端（草稿态判定）。
            user_id: 当前用户ID。
            page: 页码（从1开始）。
            page_size: 页大小。

        Returns:
            {"items": 列表项字典列表, "total": 总数, "page", "page_size"}。
        """
        total = interview_repository.count_by_user(db, user_id)
        offset = (page - 1) * page_size
        interviews = interview_repository.list_by_user(db, user_id, offset, page_size)

        # 批量查询报告就绪状态与题目计数（避免 N+1）
        report_map: dict[int, bool] = {}
        if interviews:
            ids = [i.id for i in interviews]
            from sqlalchemy import select as sa_select

            from app.models.interview_report import InterviewReport
            stmt = sa_select(InterviewReport.interview_id).where(
                InterviewReport.interview_id.in_(ids)
            )
            for row in db.execute(stmt).scalars():
                report_map[int(row)] = True

        items = []
        for it in interviews:
            questions = interview_question_repository.list_by_interview(db, it.id)
            base_count = len([q for q in questions if q.is_follow_up == 0])
            answered = len([q for q in questions if q.user_answer is not None])
            # 进行中但为草稿态（设备检测前，§3）：标记 is_started=False 供前端分流
            is_started = True
            if it.status == INTERVIEW_STATUS_IN_PROGRESS:
                cp = isess.load_checkpoint_sync(cache, it.id)
                if cp is not None and cp.get("phase") == PHASE_NOT_STARTED:
                    is_started = False
                elif cp is None and answered == 0:
                    # Checkpoint 缺失且未答过题：视为草稿（题目生成中/孤儿记录），
                    # 避免误判"进行中"直接进面试间绕过设备检测（§3 状态保持）
                    is_started = False
            items.append(
                {
                    "interview_id": it.id,
                    "status": it.status,
                    "type": it.type,
                    "total_score": float(it.total_score) if it.total_score is not None else None,
                    "follow_up_count": it.follow_up_count,
                    "question_count": base_count,
                    "answered_count": answered,
                    "report_ready": report_map.get(it.id, False),
                    "is_started": is_started,
                    "created_at": it.created_at,
                    "interview_time": it.interview_time,
                    "total_duration": it.total_duration,
                }
            )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def list_questions(self, db: Session, user_id: int, interview_id: int) -> dict:
        """查询已结束面试的逐题详情（报告页逐题展示）。

        按 §7.2 约束，未完成面试不返回全量题目（仅当前题由状态接口提供）。

        Args:
            db: 数据库同步会话。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。

        Returns:
            {"items": 题目详情字典列表, "total": 题目总数}。

        Raises:
            InterviewNotFoundError: 面试不存在或无权访问。
            InterviewConflictError: 面试进行中（409）。
        """
        interview = self._get_owned(db, user_id, interview_id)
        if interview.status == INTERVIEW_STATUS_IN_PROGRESS:
            raise InterviewConflictError("in_progress", None)

        questions = list(interview_question_repository.list_by_interview(db, interview_id))
        items = [
            {
                "question_index": idx,
                "question_no": q.question_no,
                "question_id": q.id,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "category": q.category,
                "is_follow_up": bool(q.is_follow_up),
                "user_answer": q.user_answer,
                "ai_score": q.ai_score,
                "ai_comment": q.ai_comment,
                "answer_duration": q.answer_duration,
            }
            for idx, q in enumerate(questions, start=1)
        ]
        return {"items": items, "total": len(items)}

    # ------------------------------------------------------------------
    # 面试统计（控制台平均分，含软删除记录，§统计口径：删除不影响统计）
    # ------------------------------------------------------------------

    def get_stats(self, db: Session, user_id: int) -> dict:
        """统计用户面试数据（总次数/完成数/平均分）。

        统计口径包含软删除记录：删除面试仅从历史列表移除，不改变平均分
        与完成数（用户要求）。总次数为未删除可见记录数，用于历史页分页。

        Args:
            db: 数据库同步会话。
            user_id: 当前用户ID。

        Returns:
            {"total": 可见记录总数, "completed_count": 已完成次数,
             "avg_score": 平均分（含已删）}。
        """
        return interview_repository.get_stats(db, user_id)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _generate_report_with_retry(self, db: Session, cache: redis.Redis, interview: Interview) -> None:
        """带重试的报告生成（内部，已持操作锁）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。
        """
        interview_id = interview.id
        checkpoint = isess.load_checkpoint_sync(cache, interview_id) or {}
        # 报告前轮询补齐异步分析（§八决策4=可行：等待上限60s，超时带"待补充"）
        self._wait_analysis_complete(db, interview_id)
        questions = list(interview_question_repository.list_by_interview(db, interview_id))
        resume = resume_repository.get_by_id(db, interview.resume_id)
        resume_context = self._load_resume_context(db, cache, resume)

        records = [
            {
                "question": q.question_text,
                "is_follow_up": bool(q.is_follow_up),
                "answer": q.user_answer or "",
                "score": q.ai_score,
                "comment": (
                    "待补充" if q.ai_score is None and q.user_answer is not None
                    else (q.ai_comment or "")
                ),
            }
            for q in questions
        ]
        result: InterviewReportResult | None = None
        last_error: Exception | None = None
        for _ in range(MAX_REPORT_RETRIES):
            try:
                result = generate_report(resume_context, records)
                break
            except Exception as exc:  # noqa: BLE001 - 重试需吞掉LLM异常
                last_error = exc
                logger.warning("报告生成重试: interview_id=%s", interview_id, exc_info=exc)

        if result is None:
            # 3次均失败：记数并通知（§13.1），等待手动 regenerate
            checkpoint["report_fail_count"] = int(checkpoint.get("report_fail_count", 0)) + MAX_REPORT_RETRIES
            isess.save_checkpoint_sync(cache, interview_id, checkpoint)
            logger.error("报告生成最终失败: interview_id=%s", interview_id)
            self._publish_sse(
                interview.user_id,
                {"kind": "interview:report_failed", "session_id": interview_id},
            )
            return

        total_duration = self._total_duration(questions)
        follow_up_count = len([q for q in questions if q.is_follow_up == 1])
        try:
            interview_report_repository.upsert(
                db,
                interview_id=interview_id,
                user_id=interview.user_id,
                total_score=result.total_score,
                dimension_scores=result.dimension_scores or None,
                strengths=result.strengths,
                weaknesses=result.weaknesses,
                capability_profile=result.capability_profile or None,
                suggestions=result.suggestions,
                summary=result.summary,
                question_count=len([q for q in questions if q.is_follow_up == 0]),
                follow_up_count=follow_up_count,
                total_duration=total_duration,
            )
            interview_repository.finish(
                db, interview_id,
                total_score=result.total_score,
                total_duration=total_duration,
                follow_up_count=follow_up_count,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("报告落库失败: interview_id=%s", interview_id)
            return

        checkpoint.update({"phase": PHASE_COMPLETED, "report_fail_count": 0})
        isess.save_checkpoint_sync(cache, interview_id, checkpoint)
        # 清理客户端租约、问题队列与面试图检查点（§14.4）；Checkpoint 保留供报告页回看
        isess.clear_client_sync(cache, interview_id)
        isess.delete_queue(cache, interview_id)
        invalidate_checkpoint(interview_id)
        self._publish_sse(
            interview.user_id,
            {"kind": "interview:report_ready", "session_id": interview_id},
        )

    def _get_owned(self, db: Session, user_id: int, interview_id: int) -> Interview:
        """查询并校验面试归属（越权由归属校验兜底，§3.2）。

        Args:
            db: 数据库同步会话。
            user_id: 当前用户ID。
            interview_id: 面试会话ID。

        Returns:
            Interview对象。

        Raises:
            InterviewNotFoundError: 不存在、非本人或已删除（软删除）。
        """
        interview = interview_repository.get_by_id(db, interview_id)
        if interview is None or interview.user_id != user_id or interview.is_deleted == 1:
            raise InterviewNotFoundError("面试不存在")
        return interview

    def _load_resume_context(self, db: Session, cache: redis.Redis, resume: Resume | None) -> dict:
        """加载简历上下文（Redis优先，未命中回源MySQL并回写，§4.1）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            resume: 简历ORM对象。

        Returns:
            简历结构化上下文字典（基础信息/技能/经历等）。
        """
        if resume is None:
            return {}
        key = _RESUME_CACHE_KEY.format(resume_id=resume.id)
        raw = cache.get(key)
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except (ValueError, TypeError):
                pass

        works = resume_work_experience_repository.list_by_resume(db, resume.id)
        context = {
            "name": resume.parsed_name,
            "skills": resume.parsed_skills or [],
            "education": resume.parsed_education or [],
            "projects": resume.parsed_projects or [],
            "work_experience": [
                {"company": w.company, "role": w.role, "duration": w.duration, "description": w.description}
                for w in works
            ],
        }
        try:
            cache.setex(key, _RESUME_CACHE_TTL, json.dumps(context, ensure_ascii=False))
        except Exception:
            logger.warning("简历上下文缓存回写失败: resume_id=%s", resume.id)
        return context

    def _load_or_rebuild_checkpoint(
        self, db: Session, cache: redis.Redis, interview: Interview, questions: list[InterviewQuestion]
    ) -> dict:
        """加载Checkpoint，丢失时由MySQL逐题数据重建（§6.4）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。
            questions: 发问顺序题目快照。

        Returns:
            Checkpoint状态字典。
        """
        checkpoint = isess.load_checkpoint_sync(cache, interview.id)
        if checkpoint is not None:
            return checkpoint

        # 重建：定位第一道未答题；无任何已答题视为草稿态（not_started），
        # 保证题目生成中/孤儿记录进入设备检测而非直接进面试间（§3 状态保持）
        answered_count = interview_question_repository.count_answered(db, interview.id)
        checkpoint = {
            "phase": PHASE_NOT_STARTED if answered_count == 0 else PHASE_ANSWERING,
            "question_index": len(questions),
            "current_question_id": questions[-1].id if questions else None,
            "current_question": questions[-1].question_text if questions else "",
            "current_answer": "",
            "answered_count": answered_count,
            "base_question_count": len([q for q in questions if q.is_follow_up == 0]),
            "total_follow_up_used": len([q for q in questions if q.is_follow_up == 1]),
            "started_at": interview.created_at.isoformat() if interview.created_at else datetime.now().isoformat(),
            "last_activity_at": datetime.now().isoformat(),
            "epoch": isess.get_client_epoch_sync(cache, interview.id) or 1,
            "analysis_fail_count": 0,
            "report_fail_count": 0,
        }
        for idx, q in enumerate(questions, start=1):
            if q.user_answer is None:
                checkpoint["question_index"] = idx
                checkpoint["current_question_id"] = q.id
                checkpoint["current_question"] = q.question_text
                break
        isess.save_checkpoint_sync(cache, interview.id, checkpoint)
        logger.info("Checkpoint丢失由MySQL重建: interview_id=%s question_index=%s", interview.id, checkpoint["question_index"])
        return checkpoint

    def _build_state(self, db: Session, cache: redis.Redis, interview: Interview) -> dict:
        """组装面试当前状态（刷新恢复响应，§6.2/§15）。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。

        Returns:
            状态字典。
        """
        questions = list(interview_question_repository.list_by_interview(db, interview.id))
        checkpoint = self._load_or_rebuild_checkpoint(db, cache, interview, questions)
        return self._state_from(db, interview, checkpoint, questions)

    def _state_from(
        self, db: Session, interview: Interview, checkpoint: dict, questions: list[InterviewQuestion]
    ) -> dict:
        """由Checkpoint与题目快照组装状态字典（内部）。

        Args:
            db: 数据库同步会话。
            interview: 面试会话ORM对象。
            checkpoint: Checkpoint状态。
            questions: 发问顺序题目快照。

        Returns:
            状态字典。
        """
        if interview.status == INTERVIEW_STATUS_COMPLETED:
            phase = checkpoint.get("phase", PHASE_SUMMARIZING)
            if phase != PHASE_COMPLETED:
                phase = PHASE_SUMMARIZING
        elif interview.status == INTERVIEW_STATUS_INTERRUPTED:
            phase = PHASE_ABORTED
        else:
            phase = checkpoint.get("phase", PHASE_ANSWERING)

        current = None
        if interview.status == INTERVIEW_STATUS_IN_PROGRESS and questions:
            idx = int(checkpoint.get("question_index", 1))
            if 1 <= idx <= len(questions):
                current = self._question_out(questions, idx - 1)

        return {
            "interview_id": interview.id,
            "status": interview.status,
            "type": interview.type,
            "phase": phase,
            "question_index": int(checkpoint.get("question_index", 1)),
            "epoch": int(checkpoint.get("epoch", 0)) or 1,
            "answered_count": int(checkpoint.get("answered_count", 0)),
            "total_questions": int(checkpoint.get("base_question_count", 0)),
            "current_question": current,
        }

    def _question_out(self, questions: list[InterviewQuestion], pos: int) -> dict | None:
        """题目ORM转输出字典（仅当前题，未完成不返回全量列表，§7.2）。

        Args:
            questions: 发问顺序题目快照。
            pos: 题目下标（0起）。

        Returns:
            题目输出字典或None。
        """
        if pos < 0 or pos >= len(questions):
            return None
        q = questions[pos]
        return {
            "question_index": pos + 1,
            "question_no": q.question_no,
            "question_id": q.id,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "category": q.category,
            "is_follow_up": bool(q.is_follow_up),
        }

    def _ordinal_of(self, questions: list[InterviewQuestion], question_id: int) -> int:
        """计算题目在发问顺序中的题序（1起）。

        Args:
            questions: 发问顺序题目快照。
            question_id: 题目ID。

        Returns:
            题序（找不到返回1，防御）。
        """
        for idx, q in enumerate(questions, start=1):
            if q.id == question_id:
                return idx
        return 1

    def _find_parent(self, questions: list[InterviewQuestion], target: InterviewQuestion) -> InterviewQuestion | None:
        """查找追问题的父基础题（追问上限按基础题判定，§10）。

        Args:
            questions: 发问顺序题目快照。
            target: 当前追问题。

        Returns:
            父题目ORM对象或None。
        """
        for q in questions:
            if q.id == target.parent_question_id:
                return q
        return None

    def _next_base_question(
        self, questions: list[InterviewQuestion], current_no: int
    ) -> InterviewQuestion | None:
        """查找下一道基础题（题号大于当前题号的最小者，§12）。

        Args:
            questions: 发问顺序题目快照。
            current_no: 当前基础题号。

        Returns:
            下一基础题ORM对象，无则None。
        """
        for q in questions:
            if q.is_follow_up == 0 and q.question_no > current_no:
                return q
        return None

    def _elapsed_over_limit(self, cache: redis.Redis, interview_id: int, checkpoint: dict, minutes: int) -> bool:
        """判断面试累计时长是否超过上限（时长兜底，§12.1）。

        Args:
            cache: 同步Redis客户端。
            interview_id: 面试会话ID。
            checkpoint: Checkpoint状态。
            minutes: 上限分钟数。

        Returns:
            是否超限。
        """
        started = checkpoint.get("started_at")
        if not started:
            return False
        try:
            started_dt = datetime.fromisoformat(str(started))
            return (datetime.now() - started_dt).total_seconds() > minutes * 60
        except ValueError:
            return False

    def _check_inactivity(self, db: Session, cache: redis.Redis, interview: Interview) -> None:
        """30分钟无活动自动中断（§21，读路径顺带检查）。

        草稿态（not_started，题目已生成待设备检测）不受此限制：用户可能隔
        数日才回来开始面试，故不按 30 分钟无活动自动中断。

        Args:
            db: 数据库同步会话。
            cache: 同步Redis客户端。
            interview: 面试会话ORM对象。
        """
        checkpoint = isess.load_checkpoint_sync(cache, interview.id)
        if checkpoint is None:
            return
        # 草稿态不参与无活动自动中断（§3：草稿互不影响，无时长限制）
        if checkpoint.get("phase") == PHASE_NOT_STARTED:
            return
        last = checkpoint.get("last_activity_at")
        if not last:
            return
        try:
            last_dt = datetime.fromisoformat(str(last))
        except ValueError:
            return
        if (datetime.now() - last_dt).total_seconds() <= INACTIVITY_ABORT_MINUTES * 60:
            return
        logger.info("面试超时无活动自动中断: interview_id=%s", interview.id)
        interview_repository.abort(db, interview.id)
        db.commit()
        checkpoint["phase"] = PHASE_ABORTED
        isess.save_checkpoint_sync(cache, interview.id, checkpoint)
        isess.clear_client_sync(cache, interview.id)

    def _total_duration(self, questions: list[InterviewQuestion]) -> int:
        """汇总面试总时长（各题回答时长之和，秒）。

        Args:
            questions: 发问顺序题目快照。

        Returns:
            总时长秒数。
        """
        return sum(q.answer_duration or 0 for q in questions)

    def _publish_sse(self, user_id: int, event: dict) -> None:
        """经用户频道推送面试SSE事件（失败不阻断业务，§16）。

        复用 notification_service 的统一同步发布口径，避免手拼通道名。

        Args:
            user_id: 目标用户ID。
            event: 事件数据（含 kind 与 session_id）。
        """
        try:
            notification_service.publish_to_user_sync(user_id, event)
        except Exception:
            logger.exception("面试SSE事件推送失败: user_id=%s event=%s", user_id, event.get("kind"))


def interview_repository_hard_delete(db: Session, interview_id: int) -> None:
    """物理删除面试会话记录（创建失败无脏数据清理，§21）。

    Args:
        db: 数据库同步会话。
        interview_id: 面试会话ID。
    """
    from sqlalchemy import delete as sa_delete

    db.execute(sa_delete(Interview).where(Interview.id == interview_id))
    db.commit()


interview_service = InterviewService()
