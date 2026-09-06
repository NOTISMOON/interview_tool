"""事务性Outbox事件表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 事件状态常量：0-待发布 1-已发布 2-死信（重试超限）
OUTBOX_STATUS_PENDING = 0
OUTBOX_STATUS_PUBLISHED = 1
OUTBOX_STATUS_DEAD = 2


class OutboxEvent(Base):
    """Outbox事件ORM模型，映射 outbox_event 表。

    设计要点:
        - 业务变更与事件写入同一个本地事务，事务提交即保证事件不丢。
        - id 自增 = 全局事件序号，Relay 按 id ASC 批量投递保证顺序。
        - 通用基础设施：不与 user_follow 耦合字段，业务字段全部在 payload JSON 中，
          后续帖子点赞、评论等事件直接复用该表。

    索引说明: 当前 ORM 未定义二级索引（历史迁移 f15581dc7487 已删除
        idx_status_retry/idx_published，Relay 按 id ASC 顺序扫描，如需请经 DDL 补充）。
    """

    __tablename__ = "outbox_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="业务事件名（如 follow_created/user_deactivated/comment.created/post.liked/notification.created/interview.report.generate/chat.message.sent 等）")
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="聚合根类型（user_follow/user/comment/message/post_like/post_favorite/interview/chat）")
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="聚合根标识（user_follow 为 follower_id:following_id，post_like/post_favorite 为 post_id:user_id，其余为实体ID字符串）")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, comment="事件负载（含实体字段快照，消费端免回查）")
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="0-待发布 1-已发布 2-死信(重试超限)",
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment="投递重试次数")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="下次允许重试时间（指数退避），NULL表示立即可投")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="成功发布到MQ的时间")
