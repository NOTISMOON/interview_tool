"""交换机声明模块。

集中定义所有交换机名称、类型与声明工厂，避免分散在各业务模块中。
新增业务交换机时，只需在此处添加枚举值与声明逻辑。
"""

from enum import Enum

import aio_pika


class ExchangeName(str, Enum):
    """交换机名称枚举（业务前缀 + 用途，便于运维识别）。"""

    INTERVIEW = "interview.exchange"  # 面试业务交换机（topic，按 routing_key 路由）
    NOTIFICATION = "notification.exchange"  # 通知业务交换机（topic，消息推送）
    SOCIAL = "social.exchange"  # 社交业务交换机（topic，关注/取关缓存同步）
    SOCIAL_DLX = "dlx.social"  # 社交业务死信交换机（direct，消费失败消息存档）


# 交换机类型映射：交换机名称 -> aio_pika.ExchangeType
EXCHANGE_TYPE_MAP: dict[ExchangeName, aio_pika.ExchangeType] = {
    ExchangeName.INTERVIEW: aio_pika.ExchangeType.TOPIC,
    ExchangeName.NOTIFICATION: aio_pika.ExchangeType.TOPIC,
    ExchangeName.SOCIAL: aio_pika.ExchangeType.TOPIC,
    ExchangeName.SOCIAL_DLX: aio_pika.ExchangeType.DIRECT,
}


async def declare_exchange(
    channel: aio_pika.RobustChannel,
    name: ExchangeName,
    durable: bool = True,
) -> aio_pika.RobustExchange:
    """声明指定名称的交换机（不存在则创建）。

    Args:
        channel: RabbitMQ 异步通道。
        name: 交换机名称枚举。
        durable: 是否持久化，默认 True（Broker 重启后保留）。

    Returns:
        aio_pika.RobustExchange 实例。
    """
    exchange_type = EXCHANGE_TYPE_MAP[name]
    exchange = await channel.declare_exchange(
        name=name.value,
        type=exchange_type,
        durable=durable,
    )
    return exchange


async def declare_all_exchanges(channel: aio_pika.RobustChannel) -> dict[str, aio_pika.RobustExchange]:
    """声明所有已注册的交换机。

    在消费者进程启动时统一调用，确保拓扑结构就绪。

    Args:
        channel: RabbitMQ 异步通道。

    Returns:
        交换机名称字符串 -> RobustExchange 的映射字典。
    """
    exchanges: dict[str, aio_pika.RobustExchange] = {}
    for name in ExchangeName:
        exchanges[name.value] = await declare_exchange(channel, name)
    return exchanges
