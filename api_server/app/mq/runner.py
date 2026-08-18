"""消费者进程入口模块。

独立进程运行所有注册的消费者，不依赖 FastAPI 生命周期。
通过 `python -m app.mq.runner` 启动，支持优雅关闭（Ctrl+C / SIGTERM）。

流程：
    1. 加载应用配置与日志。
    2. 建立 RabbitMQ 连接与通道。
    3. 声明全部交换机与队列绑定，确保拓扑就绪。
    4. 实例化 CONSUMER_REGISTRY 中所有消费者并订阅。
    5. 阻塞运行，等待信号后优雅关闭所有消费者与连接。
"""

import asyncio
import logging
import signal
import sys

from app.core.config import settings
from app.core.logging import setup_logging
from app.mq.connection import MQConnection
from app.mq.consumers import CONSUMER_REGISTRY
from app.mq.queues import declare_all_queues

logger = logging.getLogger(__name__)


async def run_consumers() -> None:
    """启动所有注册的消费者，阻塞运行至收到停止信号。"""
    setup_logging(logging.INFO)
    logger.info("消费者进程启动 %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # 建立连接与通道（单例）
    channel = await MQConnection.get_channel()

    # 声明全部交换机、队列与绑定，确保消费者订阅前拓扑就绪
    await declare_all_queues(channel)
    logger.info("MQ 拓扑声明完成（交换机/队列/绑定）")

    # 实例化并启动所有消费者
    consumers = [consumer_cls() for consumer_cls in CONSUMER_REGISTRY.values()]
    for consumer in consumers:
        await consumer.start()

    # 注册停止信号，触发优雅关闭
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler，使用 KeyboardInterrupt 兜底
            pass

    logger.info("所有消费者已订阅，阻塞等待消息...")

    # Windows 信号兜底：捕获 KeyboardInterrupt 后触发停止事件
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass

    # 优雅关闭
    logger.info("开始优雅关闭所有消费者...")
    for consumer in consumers:
        try:
            await consumer.stop()
        except Exception:
            logger.exception("关闭消费者失败: %s", consumer.__class__.__name__)

    await MQConnection.close()
    logger.info("消费者进程已停止")


def main() -> None:
    """消费者进程主入口函数。

    由 `python -m app.mq.runner` 调用，使用 asyncio.run 启动事件循环。
    """
    try:
        asyncio.run(run_consumers())
    except KeyboardInterrupt:
        logger.info("收到中断信号，进程退出")
        sys.exit(0)


if __name__ == "__main__":
    main()
