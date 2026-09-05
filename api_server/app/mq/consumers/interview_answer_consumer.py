"""面试回答受理消费者（v3·提交落库 MQ 化）。

消费 interview.answer.submitted.queue 消息：判题（Fast Decision）+ 追问生成 +
user_answer/追问题落库 + checkpoint 推进，全部在消费端异步完成；请求线程经
受理接口（POST /answers）毫秒级返回"已受理"，前端轮询/SSE 感知判题完成。

payload（由受理接口同事务投递）：
    - priority_ref: f"interview:{interview_id}:q{question_index}"（幂等键）
    - interview_id / user_id / question_index / question_id / question_text
    - answer / answer_duration / tab_epoch / resume_id

幂等（T3.5）：该题 user_answer 已写（重复投递/受理重投）→ 跳过。
顺序性（T3.3）：判题→追问生成→推进强串行，在同一消息处理内完成；
队列单实例消费保证同面试题目严格按题序处理（runner 不复刻 ANALYSIS 竞争并发）。
"""

import asyncio
import logging
import time

from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.redis.sync_client import SyncRedisClient
from app.services.interview_service import interview_service

logger = logging.getLogger(__name__)


class InterviewAnswerConsumer(BaseConsumer):
    """面试回答受理消费者（独立 Worker 进程内运行，v3）。

    消费 interview.answer.submitted：编排判题/追问/落库/推进（复用
    interview_service.process_answer_submitted）。业务失败记录日志并 ack，
    由"前端轮询超时重提 + 受理 analyzing 残留重投"兜底恢复，不 reject 防死信堆积。
    """

    queue_name = QueueName.INTERVIEW_ANSWER_SUBMITTED

    async def handle_message(self, message: MQMessage) -> None:
        """处理单条回答受理：幂等预检 → 判题/落库/推进编排 → SSE judged。

        Args:
            message: 入站消息，payload 含 interview/answer 字段。

        Raises:
            KeyError: payload 缺必要字段（由基类 reject 毒消息丢弃）。
        """
        payload = message.payload
        interview_id = int(payload["interview_id"])
        question_index = int(payload["question_index"])
        answer = str(payload["answer"])
        tab_epoch = int(payload.get("tab_epoch") or 0)
        answer_duration = payload.get("answer_duration")
        started_at = time.monotonic()
        logger.info(
            "回答受理消费开始 interview_id=%s question_index=%s message_id=%s",
            interview_id, question_index, message.message_id,
        )

        # 判题/落库/推进经 to_thread 调同步编排（避免阻塞事件循环）；同步 Redis 客户端
        cache = SyncRedisClient.get_client()
        ok = await asyncio.to_thread(
            interview_service.process_answer_submitted,
            cache, interview_id, question_index, answer, tab_epoch, answer_duration,
        )

        if not ok:
            # 业务失败：日志记录并 ack（不 reject），依赖受理重投/前端重提恢复
            logger.error(
                "回答受理消费业务失败 interview_id=%s question_index=%s message_id=%s",
                interview_id, question_index, message.message_id,
            )
        logger.info(
            "回答受理消费完成 interview_id=%s question_index=%s ok=%s elapsed_ms=%d",
            interview_id, question_index, ok, (time.monotonic() - started_at) * 1000,
        )