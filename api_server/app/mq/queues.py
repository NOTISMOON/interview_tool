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
    INTERVIEW_ANALYSIS = "interview.analysis.queue"  # 面试回答异步分析队列（v2）

    # 通知业务队列
    NOTIFICATION_DELIVER = "notification.deliver.queue"  # 通知投递队列

    # 私信业务队列（Outbox 扇出：未读数 + 推送对端 WS）
    CHAT_FANOUT = "chat.fanout.queue"  # 私信扇出队列

    # 社交业务队列（关注/取关缓存同步，消费失败经DLX进死信队列存档）
    SOCIAL_FOLLOW_CACHE = "social.follow.cache.queue"  # 关注缓存同步队列
    SOCIAL_FOLLOW_CACHE_DLQ = "social.follow.cache.dlq"  # 关注缓存同步死信队列（仅存档不消费）
    SOCIAL_COMMENT_CACHE = "social.comment.cache.queue"  # 评论缓存同步队列
    SOCIAL_COMMENT_CACHE_DLQ = "social.comment.cache.dlq"  # 评论缓存同步死信队列（仅存档不消费）
    SOCIAL_INTERACTION_CACHE = "social.interaction.cache.queue"  # 互动缓存同步队列
    SOCIAL_INTERACTION_CACHE_DLQ = "social.interaction.cache.dlq"  # 互动缓存同步死信队列（仅存档不消费）
    SOCIAL_FEED_PUSH = "social.feed.push.queue"  # Feed Push队列
    SOCIAL_FEED_PUSH_DLQ = "social.feed.push.dlq"  # Feed Push死信队列（仅存档不消费）
    SOCIAL_FOLLOW_POST_NOTIFY = "social.follow.post.notify.queue"  # 关注动态通知队列


# 队列声明参数（仅含DLX配置的队列需要，声明时携带才能生效）。
# social.follow.cache.queue 消费失败 nack(requeue=False) 后由 Broker 转投死信队列，
# 消除既有"直接丢弃"的静默丢失，支撑人工重放与告警。
QUEUE_DECLARE_ARGUMENTS: dict[QueueName, dict[str, str]] = {
    QueueName.SOCIAL_FOLLOW_CACHE: {
        "x-dead-letter-exchange": ExchangeName.SOCIAL_DLX.value,
        "x-dead-letter-routing-key": "social.follow.cache.dead",
    },
    QueueName.SOCIAL_COMMENT_CACHE: {
        "x-dead-letter-exchange": ExchangeName.SOCIAL_DLX.value,
        "x-dead-letter-routing-key": "social.comment.cache.dead",
    },
    QueueName.SOCIAL_INTERACTION_CACHE: {
        "x-dead-letter-exchange": ExchangeName.SOCIAL_DLX.value,
        "x-dead-letter-routing-key": "social.interaction.cache.dead",
    },
    QueueName.SOCIAL_FEED_PUSH: {
        "x-dead-letter-exchange": ExchangeName.SOCIAL_DLX.value,
        "x-dead-letter-routing-key": "social.feed.push.dead",
    },
}


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
        queue=QueueName.INTERVIEW_ANALYSIS,
        exchange=ExchangeName.INTERVIEW,
        routing_key="interview.analysis",
    ),
    QueueBinding(
        queue=QueueName.NOTIFICATION_DELIVER,
        exchange=ExchangeName.NOTIFICATION,
        routing_key="notification.deliver",
    ),
    # 私信扇出：落库成功事件路由到私信扇出队列
    QueueBinding(
        queue=QueueName.CHAT_FANOUT,
        exchange=ExchangeName.NOTIFICATION,
        routing_key="chat.message.sent",
    ),
    # 关注缓存同步：三类事件路由到同一队列，顺序消费保证同一关系事件有序
    QueueBinding(
        queue=QueueName.SOCIAL_FOLLOW_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.follow.created",
    ),
    QueueBinding(
        queue=QueueName.SOCIAL_FOLLOW_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.follow.deleted",
    ),
    QueueBinding(
        queue=QueueName.SOCIAL_FOLLOW_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.user.deactivated",
    ),
    # 死信队列：消费失败消息存档，仅人工重放，不消费
    QueueBinding(
        queue=QueueName.SOCIAL_FOLLOW_CACHE_DLQ,
        exchange=ExchangeName.SOCIAL_DLX,
        routing_key="social.follow.cache.dead",
    ),
    # 评论缓存同步：两类事件路由到同一队列，顺序消费保证同一帖子评论事件有序
    QueueBinding(
        queue=QueueName.SOCIAL_COMMENT_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.comment.created",
    ),
    QueueBinding(
        queue=QueueName.SOCIAL_COMMENT_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.comment.deleted",
    ),
    # 评论缓存同步死信队列：消费失败消息存档，仅人工重放，不消费
    QueueBinding(
        queue=QueueName.SOCIAL_COMMENT_CACHE_DLQ,
        exchange=ExchangeName.SOCIAL_DLX,
        routing_key="social.comment.cache.dead",
    ),
    # 互动缓存同步：点赞/收藏/取消点赞/取消收藏四类事件路由到同一队列
    QueueBinding(
        queue=QueueName.SOCIAL_INTERACTION_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.post.liked",
    ),
    QueueBinding(
        queue=QueueName.SOCIAL_INTERACTION_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.post.unliked",
    ),
    QueueBinding(
        queue=QueueName.SOCIAL_INTERACTION_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.post.favorited",
    ),
    QueueBinding(
        queue=QueueName.SOCIAL_INTERACTION_CACHE,
        exchange=ExchangeName.SOCIAL,
        routing_key="social.post.unfavorited",
    ),
    # 互动缓存同步死信队列：消费失败消息存档，仅人工重放，不消费
    QueueBinding(
        queue=QueueName.SOCIAL_INTERACTION_CACHE_DLQ,
        exchange=ExchangeName.SOCIAL_DLX,
        routing_key="social.interaction.cache.dead",
    ),
    # Feed Push：帖子创建事件路由到Feed Push队列
    QueueBinding(
    queue=QueueName.SOCIAL_FEED_PUSH,
    exchange=ExchangeName.SOCIAL,
    routing_key="social.post.created",
),
# Feed Push死信队列：消费失败消息存档，仅人工重放，不消费
QueueBinding(
    queue=QueueName.SOCIAL_FEED_PUSH_DLQ,
    exchange=ExchangeName.SOCIAL_DLX,
    routing_key="social.feed.push.dead",
),
# 关注动态通知：帖子创建事件路由到关注通知队列
QueueBinding(
    queue=QueueName.SOCIAL_FOLLOW_POST_NOTIFY,
    exchange=ExchangeName.SOCIAL,
    routing_key="social.post.created",
),
]


async def declare_queue(
    channel: aio_pika.RobustChannel,
    name: QueueName,
    durable: bool = True,
) -> aio_pika.RobustQueue:
    """声明指定名称的队列（不存在则创建），自动携带该队列的声明参数（如DLX）。

    Args:
        channel: RabbitMQ 异步通道。
        name: 队列名称枚举。
        durable: 是否持久化，默认 True（Broker 重启后保留）。

    Returns:
        aio_pika.RobustQueue 实例。
    """
    return await channel.declare_queue(
        name=name.value,
        durable=durable,
        arguments=QUEUE_DECLARE_ARGUMENTS.get(name),
    )


def get_dead_letter_queue(name: QueueName) -> QueueName | None:
    """依据队列DLX声明参数，从绑定关系中推导其死信队列。

    Args:
        name: 主队列名称枚举。

    Returns:
        对应的死信队列枚举，未配置DLX或无法推导时返回None。
    """
    args = QUEUE_DECLARE_ARGUMENTS.get(name)
    if not args:
        return None
    dlx = args.get("x-dead-letter-exchange")
    dlx_routing_key = args.get("x-dead-letter-routing-key")
    for binding in QUEUE_BINDINGS:
        if binding.exchange.value == dlx and binding.routing_key == dlx_routing_key:
            return binding.queue
    return None


async def ensure_queue_topology(channel: aio_pika.RobustChannel, name: QueueName) -> aio_pika.RobustQueue:
    """声明指定队列并建立其全部绑定（含死信队列），确保消费者独立启动时拓扑就绪。

    仅declare不bind时，消息发往交换机后无路由可达会被Broker静默丢弃，
    因此消费者订阅前必须确保绑定已存在；死信队列也一并声明，
    否则消费失败消息经DLX路由时因目标队列不存在而被丢弃，存档失效。

    Args:
        channel: RabbitMQ异步通道。
        name: 队列名称枚举。

    Returns:
        已声明并完成绑定的队列实例。
    """

    async def _declare_and_bind(target: QueueName) -> aio_pika.RobustQueue:
        """声明目标队列并建立其全部交换机绑定（幂等）。"""
        target_queue = await declare_queue(channel, target)
        for binding in QUEUE_BINDINGS:
            if binding.queue == target:
                exchange = await declare_exchange(channel, binding.exchange)
                await target_queue.bind(exchange, routing_key=binding.routing_key)
        return target_queue

    queue = await _declare_and_bind(name)

    # 死信队列随主队列一并声明绑定（DLX目标不存在时死信消息直接丢弃）
    dlq = get_dead_letter_queue(name)
    if dlq is not None:
        await _declare_and_bind(dlq)

    return queue


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