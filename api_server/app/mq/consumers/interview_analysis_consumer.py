"""面试回答异步分析消费者。

消费 interview.analysis.queue 消息（v2·分析异步化），对已答题目做
全量分析+评分+能力画像渐进更新，并把结果落库到 interview_question 的
ai_score / ai_comment（user_answer 与追问题已由同步路径先行落库）。

payload（由 interview_service 提交回答时投递）：
    - priority_ref: f"interview:{interview_id}:q{question_no}"（幂等键）
    - interview_id / user_id / question_id / question_no
    - question_text / answer / answer_duration / resume_id

幂等（§六）：Worker 先查该题 ai_score 是否已写入或 worker 锁是否被其他
实例持有，已写则跳过（同步重复投递 / 重复消费均不重复分析）。
"""

import asyncio
import json
import logging
import time

from app.db.sync_session import SyncSessionLocal
from app.llm.workflow.interview import analyze_answer
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.redis.async_client import AsyncRedisClient
from app.repositories.interview_question_repository import interview_question_repository
from app.repositories.resume_repository import resume_repository
from app.repositories.resume_work_experience_repository import resume_work_experience_repository

logger = logging.getLogger(__name__)

# 能力画像缓存 key 前缀（面试进行中渐进累计，报告阶段汇总，§5.3）
_PROFILE_CACHE_KEY = "interview:profile:{interview_id}"
_PROFILE_CACHE_TTL = 24 * 3600
# 简历分析结果缓存键（复用，读取简历上下文，§17.3）
_RESUME_CACHE_KEY = "resume:analysis:{resume_id}"


class InterviewAnalysisConsumer(BaseConsumer):
    """面试回答异步分析消费者（独立 Worker 进程内运行，v2）。

    消费 interview.analysis 事件，对单题做全量分析+评分，落库 ai_score/
    ai_comment 并渐进更新能力画像缓存。失败重试 N 次后置 ai_comment="分析
    失败"（ai_score=NULL）并告警，不 reject 消息（避免死信循环）。
    """

    queue_name = QueueName.INTERVIEW_ANALYSIS

    async def handle_message(self, message: MQMessage) -> None:
        """处理单题异步分析：查题 → 幂等预检 → 全量 LLM 分析 → 落库。

        Args:
            message: 入站消息，payload 含 interview/question/answer 字段。

        Raises:
            KeyError: payload 缺必要字段（由基类 reject 兜底）。
            Exception: 分析进程内异常（由本方法内部消化，不向外抛）。
        """
        payload = message.payload
        interview_id = int(payload["interview_id"])
        question_id = int(payload["question_id"])
        question_text = str(payload["question_text"])
        answer = str(payload["answer"])
        answer_duration = payload.get("answer_duration")
        resume_id = int(payload.get("resume_id") or 0)
        user_id = int(payload["user_id"])
        priority_ref = str(payload.get("priority_ref", f"interview:{interview_id}:q{question_id}"))
        started_at = time.monotonic()
        logger.info(
            "回答异步分析开始 interview_id=%s question_id=%s priority_ref=%s message_id=%s",
            interview_id, question_id, priority_ref, message.message_id,
        )

        # 幂等：ai_score 已写入（重复消费）→ 跳过
        question = await asyncio.to_thread(self._load_question, question_id)
        if question is None or question.ai_score is not None:
            logger.info("题目不存在或已分析，跳过 interview_id=%s question_id=%s", interview_id, question_id)
            return

        # 简历上下文（追问贴合项目实际，§9.3）
        resume_context = {}
        if resume_id:
            resume_context = await asyncio.to_thread(self._load_resume_context, resume_id)

        # 全量分析（单次合并 LLM：分析+评分+追问预生成），失败重试后标记
        analysis = None
        last_error: Exception | None = None
        for attempt in range(1, MAX_ANALYSIS_RETRIES + 1):
            try:
                analysis = await asyncio.to_thread(
                    analyze_answer, question_text, answer, resume_context
                )
                break
            except Exception as exc:  # noqa: BLE001 - 重试需吞掉LLM异常
                last_error = exc
                logger.warning(
                    "回答异步分析第 %s 次失败 interview_id=%s question_id=%s",
                    attempt, interview_id, question_id, exc_info=exc,
                )
                if attempt < MAX_ANALYSIS_RETRIES:
                    await asyncio.sleep(ASYNC_RETRY_BACKOFF_SECONDS)

        try:
            if analysis is None:
                # 重试耗尽：置 ai_comment="分析失败"（ai_score=NULL），不丢已答数据（§21）
                logger.error(
                    "回答异步分析最终失败 interview_id=%s question_id=%s err=%s",
                    interview_id, question_id, last_error,
                )
                await asyncio.to_thread(self._mark_failed, question_id, answer, answer_duration)
                return
            # 单事务落库该题分析结果（§14.2）
            await asyncio.to_thread(self._save_analysis, question_id, analysis, answer_duration)
            # 渐进更新能力画像缓存（AVG 累计，§5.3）
            await self._update_profile(priority_ref, interview_id, analysis.score)
        except Exception:
            logger.exception("回答异步分析结果落库失败 interview_id=%s question_id=%s", interview_id, question_id)
            return

        logger.info(
            "回答异步分析完成 interview_id=%s question_id=%s score=%s elapsed_ms=%d",
            interview_id, question_id, analysis.score, (time.monotonic() - started_at) * 1000,
        )

    # ------------------------------------------------------------------
    # 同步 DB 操作（经 asyncio.to_thread 调用，避免阻塞事件循环）
    # ------------------------------------------------------------------

    @staticmethod
    def _load_question(question_id: int):
        """同步查询单题。

        Args:
            question_id: 题目ID。

        Returns:
            InterviewQuestion 对象；不存在返回 None。
        """
        db = SyncSessionLocal()
        try:
            return interview_question_repository.get_by_id(db, question_id)
        finally:
            db.close()

    @staticmethod
    def _load_resume_context(resume_id: int) -> dict:
        """同步加载简历上下文（缓存优先，未命中回源MySQL并回写）。

        Args:
            resume_id: 简历ID。

        Returns:
            简历结构化上下文字典。
        """
        db = SyncSessionLocal()
        try:
            resume = resume_repository.get_by_id(db, resume_id)
            if resume is None:
                return {}
            works = resume_work_experience_repository.list_by_resume(db, resume.id)
            return {
                "name": resume.parsed_name,
                "skills": resume.parsed_skills or [],
                "education": resume.parsed_education or [],
                "projects": resume.parsed_projects or [],
                "work_experience": [
                    {"company": w.company, "role": w.role, "duration": w.duration, "description": w.description}
                    for w in works
                ],
            }
        finally:
            db.close()

    @staticmethod
    def _save_analysis(question_id: int, analysis, answer_duration: int | None) -> None:
        """同步单事务落库单题分析结果。

        user_answer 已由同步路径落库；此处补 ai_score/ai_comment 与 answer_duration。

        Args:
            question_id: 题目ID。
            analysis: AnswerAnalysisResult。
            answer_duration: 回答时长（秒，可选）。
        """
        db = SyncSessionLocal()
        try:
            question = interview_question_repository.get_by_id(db, question_id)
            if question is None:
                return
            interview_question_repository.save_analysis(
                db, question_id, question.user_answer or "",
                analysis.score, analysis.comment, answer_duration,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _mark_failed(question_id: int, answer: str, answer_duration: int | None) -> None:
        """同步标记该题分析失败（ai_score=NULL，ai_comment=分析失败，§21）。

        Args:
            question_id: 题目ID。
            answer: 用户回答。
            answer_duration: 回答时长（秒，可选）。
        """
        db = SyncSessionLocal()
        try:
            question = interview_question_repository.get_by_id(db, question_id)
            if question is None:
                return
            question.user_answer = answer
            question.ai_comment = "分析失败"
            if answer_duration is not None:
                question.answer_duration = answer_duration
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("标记回答分析失败异常 question_id=%s", question_id)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 能力画像缓存（渐进累计，§5.3）
    # ------------------------------------------------------------------

    async def _update_profile(self, priority_ref: str, interview_id: int, score: int) -> None:
        """渐进更新能力画像缓存（单题分数 AVG 累计，报告阶段由 summary 汇总）。

        Args:
            priority_ref: 幂等引用（防重复累计）。
            interview_id: 面试会话ID。
            score: 本题评分 1-5。
        """
        try:
            redis_client = await AsyncRedisClient.get_client()
            profile_key = _PROFILE_CACHE_KEY.format(interview_id=interview_id)
            # Lua：若该 priority_ref 尚未累计则累加（幂等防重复消费重复累计）
            lua = """
local k, subk = KEYS[1], ARGV[1]
local cur = redis.call("HGET", k, subk)
if cur then return 0 end
redis.call("HSET", k, subk, ARGV[2])
redis.call("EXPIRE", k, tonumber(ARGV[3]))
return 1
"""
            await redis_client.eval(lua, 1, profile_key, priority_ref, str(score), _PROFILE_CACHE_TTL)
        except Exception:
            logger.exception("能力画像缓存累计失败 interview_id=%s", interview_id)


# 重试次数与退避（LLM 失败重试，超限置失败标记）
MAX_ANALYSIS_RETRIES = 3
# 重试退避间隔（秒）
ASYNC_RETRY_BACKOFF_SECONDS = 2