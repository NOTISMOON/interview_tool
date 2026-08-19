"""消息通知请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class FromUserInfo(BaseModel):
    """消息发送者简要信息。"""

    id: int
    nickname: str
    avatar: str | None = None


class RelatedInfo(BaseModel):
    """关联实体简要信息。"""

    id: int
    type: int
    type_name: str | None = None


class MessageResponse(BaseModel):
    """消息响应模型（含发送者信息与关联实体）。

    注意：unread_total 仅在 MessageListResponse 顶层有意义，单项消息恒为 null，
    通过 exclude=True 从序列化中剔除，保证 SSE 实时事件与 REST 响应字段完全一致。
    """

    id: int
    type: int
    type_name: str = ""
    title: str
    content_text: str = Field(..., alias="content")
    from_user: FromUserInfo | None = None
    related: RelatedInfo | None = None
    created_at: datetime
    is_read: bool = False
    unread_total: int | None = Field(default=None, exclude=True)

    model_config = {"from_attributes": True, "populate_by_name": True}


class MessageListResponse(BaseModel):
    """消息列表响应模型。"""

    items: list[MessageResponse]
    next_cursor: int | None = None
    unread_total: int = 0


class UnreadCountResponse(BaseModel):
    """未读计数响应模型。"""

    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class MarkReadRequest(BaseModel):
    """标记已读请求模型。"""

    message_id: int = Field(..., ge=1, description="消息ID")