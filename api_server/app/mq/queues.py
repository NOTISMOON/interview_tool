"""队列声明与绑定模块。

集中定义所有队列名称、绑定关系（交换机 + routing_key）与声明工厂。
新增业务队列时，只需在 QueueName 枚举与 QUEUE_BINDINGS 中添加配置。
"""

from dataclasses import dataclass
from enum import Enum

import aio_pika

from app.mq.exchanges import ExchangeName, declare_exchange


class QueueName(str, Enum):
    """队列名称枚举（业务前缀 + 用途，便于运维识别）。"""

    # 面试业务队列
    INTERVIEW_RESUME_PARSE = "interview.resume.parse.queue"  # 简历解析任务队列
    INTERVIEW_REPORT_GENERATE = "interview.report.queue"  # 面试报告生成队列

    # 通知业务队列
    NOTIFICATION_DELIVER = "notification.deliver.queue"  # 通知投递队列


@dataclass(frozen=True)
class QueueBinding:
    """队列绑定关系配置。

    Attributes:
        queue: 队列名称枚举。
        exchange: 绑定的交换机名称枚举。
        routing_key: 路由键（topic 交换机支持通配符 * 与 #）。
    """

    queue: QueueName
    exchange: ExchangeName
    routing_key: str


# 全部队列与交换机的绑定关系。
# topic 交换机下，routing_key 使用点分层次，支持通配符匹配。
QUEUE_BINDINGS: list[QueueBinding] = [
    QueueBinding(
        queue=QueueName.INTERVIEW_RESUME_PARSE,
        exchange=ExchangeName.INTERVIEW,
        routing_key="interview.resume.parse",
    ),
    QueueBinding(
        queue=QueueName.INTERVIEW_REPORT_GENERATE,
        exchange=ExchangeName.INTERVIEW,
        routing_key="interview.report.generate",
    ),
    QueueBinding(
        queue=QueueName.NOTIFICATION_DELIVER,
        exchange=ExchangeName.NOTIFICATION,
        routing_key="notification.deliver",
    ),
]


async def declare_queue(
    channel: aio_pika.RobustChannel,
    name: QueueName,
    durable: bool = True,
) -> aio_pika.RobustQueue:
    """声明指定名称的队列（不存在则创建）。

    Args:
        channel: RabbitMQ 异步通道。
        name: 队列名称枚举。
        durable: 是否持久化，默认 True（Broker 重启后保留）。

    Returns:
        aio_pika.RobustQueue 实例。
    """
    return await channel.declare_queue(name=name.value, durable=durable)


async def declare_all_queues(
    channel: aio_pika.RobustChannel,
) -> dict[str, aio_pika.RobustQueue]:
    """声明所有队列并完成与交换机的绑定。

    在消费者进程启动时统一调用，确保所有队列与路由就绪。

    Args:
        channel: RabbitMQ 异步通道。

    Returns:
        队列名称字符串 -> RobustQueue 的映射字典。
    """
    # 先确保所有交换机已声明
    exchanges = {binding.exchange: await declare_exchange(channel, binding.exchange) for binding in QUEUE_BINDINGS}

    queues: dict[str, aio_pika.RobustQueue] = {}
    declared_queues: set[QueueName] = set()

    for binding in QUEUE_BINDINGS:
        # 队列只需声明一次（不同绑定可能复用同一队列）
        if binding.queue not in declared_queues:
            queue = await declare_queue(channel, binding.queue)
            queues[binding.queue.value] = queue
            declared_queues.add(binding.queue)

        # 建立队列与交换机的绑定
        queue = queues[binding.queue.value]
        exchange = exchanges[binding.exchange]
        await queue.bind(
            exchange=exchange,
            routing_key=binding.routing_key,
        )

    return queues


def get_routing_key(queue: QueueName) -> str:
    """根据队列名称查询其绑定的 routing_key。

    Args:
        queue: 队列名称枚举。

    Returns:
        绑定的 routing_key 字符串。

    Raises:
        KeyError: 队列未配置绑定时抛出。
    """
    for binding in QUEUE_BINDINGS:
        if binding.queue == queue:
            return binding.routing_key
    raise KeyError(f"队列 {queue} 未配置绑定关系")
