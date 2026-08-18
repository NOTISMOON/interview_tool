"""Outbox事件数据访问层。

包含两个类:
    - SyncOutboxRepository: 同步实现，供写接口（关注/取关/注销等普通业务）在
      同一同步事务内写入事件（保证业务变更与事件的原子性，本方案核心，禁止拆会话）。
    - OutboxRepository: 异步实现，供 Outbox Relay（runner进程）轮询、标记与清理。
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.outbox_event import OUTBOX_STATUS_DEAD, OUTBOX_STATUS_PENDING, OutboxEvent


class SyncOutboxRepository:
    """Outbox事件数据访问层（同步），事件写入必须与业务操作共用同一Session。"""

    def insert_event(
        self,
        db: Session,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict,
    ) -> int:
        """在当前事务内写入一条待发布事件（flush回填event_id到payload）。

        Args:
            db: 数据库同步会话（必须与业务操作同一会话，随业务事务一起提交/回滚）。
            event_type: 事件类型（follow_created/follow_deleted/user_deactivated）。
            aggregate_type: 聚合根类型（user_follow/user）。
            aggregate_id: 聚合根标识（如 "1:2" 或 "5"）。
            payload: 事件负载字典（业务字段快照）。

        Returns:
            事件自增ID（payload中同步回填event_id，便于链路追踪）。
        """
        event = OutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
        )
        db.add(event)
        db.flush()  # 获取自增主键，供payload回填event_id
        event.payload = {**payload, "event_id": event.id}
        db.flush()
        return event.id


class OutboxRepository:
    """Outbox事件数据访问层（异步），供Relay轮询投递与清理任务使用。"""

    async def fetch_pending(self, db: AsyncSession, batch_size: int) -> list[OutboxEvent]:
        """查询一批待发布事件（按id升序保证投递顺序，命中idx_status_retry）。

        Args:
            db: 数据库异步会话。
            batch_size: 单批最大条数。

        Returns:
            待发布事件列表（已到重试时间的优先）。
        """
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == OUTBOX_STATUS_PENDING,
                (OutboxEvent.next_retry_at.is_(None)) | (OutboxEvent.next_retry_at <= datetime.now()),
            )
            .order_by(OutboxEvent.id.asc())
            .limit(batch_size)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def mark_published(self, db: AsyncSession, event_id: int) -> None:
        """将事件标记为已发布（仅当仍为待发布态，防重复标记）。

        Args:
            db: 数据库异步会话。
            event_id: 事件ID。
        """
        await db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.status == OUTBOX_STATUS_PENDING)
            .values(status=1, published_at=datetime.now())
        )
        await db.commit()

    async def mark_failed(
        self,
        db: AsyncSession,
        event_id: int,
        retry_count: int,
        max_retry: int,
        base_delay: int,
    ) -> bool:
        """记录一次投递失败：计数+1并按指数退避安排下次重试，超限置死信。

        Args:
            db: 数据库异步会话。
            event_id: 事件ID。
            retry_count: 失败前的重试次数（新次数=retry_count+1）。
            max_retry: 最大重试次数，新次数达到该值即置死信。
            base_delay: 退避基数（秒），实际延迟=base*2^新次数。

        Returns:
            置为死信返回True，否则False（等待下次重试）。
        """
        new_count = retry_count + 1
        if new_count >= max_retry:
            await db.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == event_id)
                .values(retry_count=new_count, status=OUTBOX_STATUS_DEAD)
            )
            await db.commit()
            return True

        delay_seconds = base_delay * (2 ** new_count)
        next_retry_at = datetime.now() + timedelta(seconds=delay_seconds)
        await db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(retry_count=new_count, next_retry_at=next_retry_at)
        )
        await db.commit()
        return False

    async def mark_dead(self, db: AsyncSession, event_id: int, retry_count: int) -> None:
        """直接将事件置为死信（未知事件类型等不可重试场景）。

        Args:
            db: 数据库异步会话。
            event_id: 事件ID。
            retry_count: 写入的重试计数值。
        """
        await db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(retry_count=retry_count, status=OUTBOX_STATUS_DEAD)
        )
        await db.commit()

    async def delete_published_before(self, db: AsyncSession, before: datetime, batch_size: int) -> int:
        """分批删除已发布超期事件（清理任务，避免大事务长锁）。

        Args:
            db: 数据库异步会话。
            before: 删除published_at早于该时间的事件。
            batch_size: 单批DELETE上限。

        Returns:
            本批删除的行数（0表示无可删数据）。
        """
        result = await db.execute(
            delete(OutboxEvent)
            .where(OutboxEvent.status == 1, OutboxEvent.published_at < before)
            .limit(batch_size)
        )
        await db.commit()
        return int(result.rowcount or 0)


sync_outbox_repository = SyncOutboxRepository()
outbox_repository = OutboxRepository()
