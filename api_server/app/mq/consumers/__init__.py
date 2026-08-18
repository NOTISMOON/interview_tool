"""具体业务消费者目录。

每个业务消费者继承 app.mq.consumer.BaseConsumer，实现 handle_message 方法。
runner.py 通过 CONSUMER_REGISTRY 字典统一注册并启动。
"""

from app.mq.consumers.interview_consumer import (
    InterviewReportConsumer,
    InterviewResumeParseConsumer,
)

# 消费者注册表：类名 -> 类对象，runner 通过此表批量启动。
# 新增消费者时，在对应文件定义后，在此处导入并添加即可。
CONSUMER_REGISTRY: dict[str, type] = {
    "InterviewResumeParseConsumer": InterviewResumeParseConsumer,
    "InterviewReportConsumer": InterviewReportConsumer,
}

__all__ = [
    "CONSUMER_REGISTRY",
    "InterviewReportConsumer",
    "InterviewResumeParseConsumer",
]
