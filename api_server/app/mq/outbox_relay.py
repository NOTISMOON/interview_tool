"""Outbox Relay（事件投递器）模块。

Transactional Outbox 的投递侧：轮询 outbox_event 表中待发布事件，逐条经
publisher confirm 通道投递到 RabbitMQ，成功标记已发布，失败按指数退避重试，
超限置死信；附带低频清理任务删除超期已发布事件。

可靠性设计:
    - 独立通道且开启 publisher confirm（收到confirm才标记status=1），
      不改动现有 MQProducer 语义，保证 at-least-once 投递。
    - 逐条确认而非批量：单条失败不影响本批其余事件（重复投递由消费端幂等消化）。
    - 单实例按 id ASC 投递 + 单队列FIFO + 单消费者实例 → 同一关注关系的
      created/deleted 事件有序消费。

启动方式: 由 app.mq.runner 挂载为 asyncio 任务（与消费者同进程）。
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import aio_pika

from app.core.config import settings
from app.db.async_session import AsyncSessionLocal
from app.models.outbox_event import OutboxEvent
from app.mq.connection import MQConnection
from app.mq.exchanges import ExchangeName, declare_exchange
from app.mq.producer import MQProducer
from app.repositories.outbox_repository import outbox_repository

logger = logging.getLogger(__name__)

# 事件类型 -> (exchange, routing_key) 映射
EVENT_EXCHANGE_MAP: dict[str, tuple[ExchangeName, str]] = {
    "follow_created": (ExchangeName.SOCIAL, "social.follow.created"),
    "follow_deleted": (ExchangeName.SOCIAL, "social.follow.deleted"),
    "user_deactivated": (ExchangeName.SOCIAL, "social.user.deactivated"),
    "post.created": (ExchangeName.SOCIAL, "social.post.created"),
    "post.deleted": (ExchangeName.SOCIAL, "social.post.deleted"),
    "post.event": (ExchangeName.SOCIAL, "social.post.event"),
    "post.liked": (ExchangeName.SOCIAL, "social.post.liked"),
    "post.unliked": (ExchangeName.SOCIAL, "social.post.unliked"),
    "post.favorited": (ExchangeName.SOCIAL, "social.post.favorited"),
    "post.unfavorited": (ExchangeName.SOCIAL, "social.post.unfavorited"),
    "comment.created": (ExchangeName.SOCIAL, "social.comment.created"),
    "comment.deleted": (ExchangeName.SOCIAL, "social.comment.deleted"),
    "notification.created": (ExchangeName.NOTIFICATION, "notification.deliver"),
    "chat.message.sent": (ExchangeName.NOTIFICATION, "chat.message.sent"),
    "resume.parse": (ExchangeName.INTERVIEW, "interview.resume.parse"),
    "interview.analysis": (ExchangeName.INTERVIEW, "interview.analysis"),
    "interview.report.generate": (ExchangeName.INTERVIEW, "interview.report.generate"),
}

# 清理任务执行间隔（秒）
CLEANUP_INTERVAL_SECONDS = 600


class OutboxRelay:
    """Outbox事件投递器（asyncio任务，单实例随runner进程运行）。"""

    def __init__(self) -> None:
        """初始化Relay，预置任务句柄与停止事件。"""
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._channel: aio_pika.RobustChannel | None = None
        self._last_cleanup_at: float = 0.0

    async def start(self) -> None:
        """启动Relay轮询任务（幂等：重复调用不重复启动）。"""
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="outbox-relay")
        logger.info("Outbox Relay 已启动 poll_interval=%ss batch=%d", settings.OUTBOX_POLL_INTERVAL, settings.OUTBOX_BATCH_SIZE)

    async def stop(self) -> None:
        """停止Relay轮询任务并等待退出。"""
        self._stop_event.set()
        if self._task is not None:
            try:
                await self._task
            except Exception:
                logger.exception("Outbox Relay 任务退出异常")
            self._task = None
        logger.info("Outbox Relay 已停止")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """主循环：轮询投递 + 低频清理，异常兜底防进程退出。"""
        while not self._stop_event.is_set():
            try:
                await self._poll_once()
            except Exception:
                # 单轮失败不影响整体（DB/MQ短暂不可用场景），下轮自然重试
                logger.exception("Outbox Relay 轮询投递异常")

            try:
                await self._maybe_cleanup()
            except Exception:
                logger.exception("Outbox Relay 清理任务异常")

            # 可中断的间隔等待（stop_event触发时立即退出）
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=settings.OUTBOX_POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass

    async def _poll_once(self) -> None:
        """单轮投递：扫描一批待发布事件并逐条确认投递。"""
        async with AsyncSessionLocal() as session:
            events = await outbox_repository.fetch_pending(session, settings.OUTBOX_BATCH_SIZE)
        if not events:
            return

        logger.debug("Outbox扫描到待发布事件 count=%s", len(events))
        for event in events:
            # stop_event触发时尽快退出，剩余事件下轮继续
            if self._stop_event.is_set():
                return
            await self._publish_one(event)

    async def _publish_one(self, event: OutboxEvent) -> None:
        """投递单条事件：confirm发布成功标记已发布，失败记录退避重试。

        Args:
            event: 待发布的Outbox事件ORM对象。
        """
        exchange_and_routing = EVENT_EXCHANGE_MAP.get(event.event_type)
        if exchange_and_routing is None:
            # 未知事件类型：不可重试，直接置死信并告警，避免毒数据阻塞投递循环
            logger.error("未知事件类型，置死信 event_id=%s event_type=%s", event.id, event.event_type)
            async with AsyncSessionLocal() as session:
                await outbox_repository.mark_dead(session, event_id=event.id, retry_count=event.retry_count)
            return

        target_exchange, routing_key = exchange_and_routing

        try:
            exchange = await self._ensure_exchange(target_exchange)
            # message_id=outbox行id：DB行 → MQ message_id → Consumer日志 三段统一
            body = MQProducer._build_body(str(event.id), event.payload)
            message = aio_pika.Message(
                body=body.encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=str(event.id),
                timestamp=datetime.now(timezone.utc),
            )
            publish_started_at = time.monotonic()
            await exchange.publish(message, routing_key=routing_key)
        except Exception:
            logger.exception("Outbox事件投递失败 event_id=%s event_type=%s", event.id, event.event_type)
            await self._mark_failed(event)
            return

        async with AsyncSessionLocal() as session:
            await outbox_repository.mark_published(session, event.id)
        logger.info(
            "Outbox事件已投递 event_id=%s event_type=%s routing_key=%s publish_elapsed_ms=%d",
            event.id,
            event.event_type,
            routing_key,
            (time.monotonic() - publish_started_at) * 1000,
        )

    async def _mark_failed(self, event: OutboxEvent) -> None:
        """记录一次投递失败（指数退避），超限置死信并告警。

        Args:
            event: 投递失败的Outbox事件。
        """
        async with AsyncSessionLocal() as session:
            dead = await outbox_repository.mark_failed(
                session,
                event_id=event.id,
                retry_count=event.retry_count,
                max_retry=settings.OUTBOX_MAX_RETRY,
                base_delay=settings.OUTBOX_RETRY_BASE_DELAY,
            )
        if dead:
            logger.error(
                "Outbox事件投递重试超限，已置死信 event_id=%s event_type=%s aggregate_id=%s",
                event.id,
                event.event_type,
                event.aggregate_id,
            )

    async def _ensure_exchange(self, exchange_name: ExchangeName) -> aio_pika.RobustExchange:
        """获取confirm发布通道与目标交换机（懒创建，断线由Robust机制自动恢复）。

        Args:
            exchange_name: 目标交换机名称枚举。

        Returns:
            已声明的交换机实例。
        """
        if self._channel is None or self._channel.is_closed:
            connection = await MQConnection.get_connection()
            # 独立通道显式开启publisher confirm：收到confirm才标记status=1，
            # 保证at-least-once（Broker落盘前宕机时事件保持待发布态，重启重投）
            self._channel = await connection.channel(publisher_confirms=True)
        return await declare_exchange(self._channel, exchange_name)

    # ------------------------------------------------------------------
    # 清理任务（低频）
    # ------------------------------------------------------------------

    async def _maybe_cleanup(self) -> None:
        """按间隔触发已发布超期事件清理（分批DELETE避免大事务长锁）。"""
        now = time.monotonic()
        if now - self._last_cleanup_at < CLEANUP_INTERVAL_SECONDS:
            return
        self._last_cleanup_at = now

        before = datetime.now() - timedelta(days=settings.OUTBOX_RETENTION_DAYS)
        total = 0
        while not self._stop_event.is_set():
            async with AsyncSessionLocal() as session:
                deleted = await outbox_repository.delete_published_before(
                    session, before, settings.OUTBOX_CLEANUP_BATCH
                )
            total += deleted
            if deleted < settings.OUTBOX_CLEANUP_BATCH:
                break  # 已无可删数据
        if total:
            logger.info("Outbox已发布事件清理完成 deleted=%d before=%s", total, before)


outbox_relay = OutboxRelay()