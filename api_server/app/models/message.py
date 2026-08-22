"""消息通知表ORM模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 消息类型常量（与通知功能流程文档对齐）
MESSAGE_TYPE_SYSTEM = 1
MESSAGE_TYPE_COMMENT = 2
MESSAGE_TYPE_LIKE = 3
MESSAGE_TYPE_FOLLOW = 4
MESSAGE_TYPE_INTERVIEW = 5
MESSAGE_TYPE_DM = 6
MESSAGE_TYPE_FOLLOW_POST = 7  # 关注的人发布了新帖子

# 关联实体类型常量
RELATED_TYPE_POST = 1
RELATED_TYPE_REPORT = 2
RELATED_TYPE_USER = 3
RELATED_TYPE_RESUME = 4  # 简历（简历AI分析完成/失败通知跳转用）


class Message(Base):
    """消息通知ORM模型，映射 message 表。

    设计要点:
        - user_id 为消息接收者，from_user_id 为消息触发者（系统消息为空）。
        - id 自增 BIGINT 全局有序，SSE 增量补偿和前端 last_msg_id 均基于此。
        - 索引 idx_user_unread 支撑未读计数与未读列表快速查询。

    索引设计:
        - idx_user_type(user_id, type, created_at DESC): 按类型筛选消息
        - idx_user_unread(user_id, is_read, created_at DESC): 未读列表查询
    """

    __tablename__ = "message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="消息接收者")
    type: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-系统 2-评论 3-点赞 4-关注 5-面试 6-私信 7-关注动态")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="消息标题")
    content: Mapped[str] = mapped_column(String(1000), nullable=False, comment="消息内容")
    from_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="消息发送者（系统消息为空）")
    related_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="关联实体ID")
    related_type: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="1-帖子 2-报告 3-用户")
    is_read: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment="0-未读 1-已读")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="已读时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )