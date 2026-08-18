"""面试业务消费者示例。

两个示例消费者：
    - InterviewResumeParseConsumer: 消费简历解析任务，调用 AI 服务异步解析简历。
    - InterviewReportConsumer: 消费面试报告生成任务，调用 AI 服务生成综合报告。

注意：此处仅演示消费流程骨架，具体 AI 服务调用逻辑待后续接入。
"""

import logging

from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName

logger = logging.getLogger(__name__)


class InterviewResumeParseConsumer(BaseConsumer):
    """简历解析任务消费者。

    消费 interview.resume.parse.queue 队列消息，
    根据负载中的 resume_id 调用 AI 服务解析简历内容。
    """

    queue_name = QueueName.INTERVIEW_RESUME_PARSE

    async def handle_message(self, message: MQMessage) -> None:
        """处理简历解析任务。

        Args:
            message: 入站消息对象，payload 含 resume_id 与 user_id。
        """
        resume_id = message.payload.get("resume_id")
        user_id = message.payload.get("user_id")
        logger.info(
            "开始解析简历 resume_id=%s user_id=%s message_id=%s",
            resume_id,
            user_id,
            message.message_id,
        )

        # TODO: 接入 AI 简历解析服务
        # async with AsyncSessionLocal() as db:
        #     resume = await resume_repo.get_by_id(db, resume_id)
        #     parsed = await ai_service.parse_resume(resume.file_url)
        #     await resume_repo.update_parsed_content(db, resume_id, parsed)


class InterviewReportConsumer(BaseConsumer):
    """面试报告生成消费者。

    消费 interview.report.queue 队列消息，
    根据负载中的 interview_id 调用 AI 服务生成面试综合报告。
    """

    queue_name = QueueName.INTERVIEW_REPORT_GENERATE

    async def handle_message(self, message: MQMessage) -> None:
        """处理面试报告生成任务。

        Args:
            message: 入站消息对象，payload 含 interview_id。
        """
        interview_id = message.payload.get("interview_id")
        logger.info(
            "开始生成面试报告 interview_id=%s message_id=%s",
            interview_id,
            message.message_id,
        )

        # TODO: 接入 AI 报告生成服务
        # async with AsyncSessionLocal() as db:
        #     interview = await interview_repo.get_by_id(db, interview_id)
        #     report = await ai_service.generate_report(interview)
        #     await interview_repo.update_report(db, interview_id, report)
