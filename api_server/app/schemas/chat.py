"""私信请求/响应模型。

包含：
- WS 入站消息模型（WSSendMessage）：客户端经 WebSocket 发送的私信请求。
- WS 回执模型（WSMessageAck）：服务端写缓冲成功/重复的回执。
- 会话/消息响应模型（ConversationResponse / DmMessageResponse）：私信 REST 兜底接口用。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# 内容类型常量：1-文本 2-图片 3-文件
CONTENT_TYPE_TEXT = 1
CONTENT_TYPE_IMAGE = 2
CONTENT_TYPE_FILE = 3


class WSSendMessage(BaseModel):
    """WS 入站消息：客户端一次私信发送请求。

    Attributes:
        action: 固定为 "send"。
        conversation_id: 目标会话ID。
        receiver_id: 接收方用户ID。
        client_msg_id: 客户端 UUID 幂等键（断线重发不变）。
        content: 消息内容。
        content_type: 内容类型（1-文本 2-图片 3-文件），默认文本。
    """

    action: Literal["send"] = "send"
    conversation_id: int = Field(..., gt=0, description="目标会话ID")
    receiver_id: int = Field(..., gt=0, description="接收方用户ID")
    client_msg_id: str = Field(..., min_length=8, max_length=64, description="客户端UUID幂等键")
    content: str = Field(..., min_length=1, max_length=5000, description="消息内容")
    content_type: int = Field(default=CONTENT_TYPE_TEXT, ge=1, le=3, description="内容类型1-3")

    @field_validator("content")
    @classmethod
    def check_content(cls, v: str) -> str:
        """校验纯文本消息去除空白后仍非空，避免发空消息。"""
        if not v.strip():
            raise ValueError("消息内容不能全为空白")
        return v


class WSMessageAck(BaseModel):
    """WS 回执模型：服务端写入写缓冲后的确认帧。

    Attributes:
        action: ack 类型（sent 正常 / duplicate 重复）。
        client_msg_id: 对应入站消息的幂等键。
        conversation_id: 会话ID。
        seq: 该消息在本会话的序号。
    """

    action: Literal["sent", "duplicate"] = "sent"
    client_msg_id: str
    conversation_id: int
    seq: int
    status: str = "ok"


class WSErrorAck(BaseModel):
    """WS 错误回执模型：参数校验失败或服务端异常时的提示帧。

    Attributes:
        action: 恒为 "error"。
        client_msg_id: 对应入站消息的幂等键（可空）。
        error: 错误说明。
    """

    action: Literal["error"] = "error"
    client_msg_id: str | None = None
    error: str


class DmMessageResponse(BaseModel):
    """私信消息响应模型（REST 兜底）。

    Attributes:
        id: 消息ID。
        conversation_id: 会话ID。
        from_user_id: 发送方用户ID。
        receiver_id: 接收方用户ID。
        content_type: 内容类型。
        content: 消息内容。
        seq: 同会话自增序号。
        is_read: 是否已读。
        created_at: 发送时间。
    """

    id: int
    conversation_id: int
    from_user_id: int
    receiver_id: int
    content_type: int
    content: str
    seq: int
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    """私信会话响应模型（REST 兜底）。

    Attributes:
        id: 会话ID。
        peer: 对方用户简要信息。
        last_message: 最后一条消息摘要。
        last_message_at: 最后消息时间。
        last_message_id: 最后一条消息ID。
        unread: 会话未读数。
    """

    id: int
    peer: "PeerInfo | None" = None
    last_message: str | None = None
    last_message_at: datetime | None = None
    last_message_id: int | None = None
    unread: int = 0

    model_config = {"from_attributes": True}


class PeerInfo(BaseModel):
    """会话对方用户简要信息。

    Attributes:
        id: 用户ID。
        nickname: 昵称。
        avatar: 头像。
    """

    id: int
    nickname: str
    avatar: str | None = None


class ConversationListResponse(BaseModel):
    """私信会话列表响应模型。

    Attributes:
        items: 会话列表。
    """

    items: list[ConversationResponse]


class MessageListResponse(BaseModel):
    """私信消息列表响应模型（历史分页）。

    Attributes:
        items: 消息列表（按 seq DESC）。
        next_cursor: 下一页游标（无更多为 None）。
        unread_total: 会话未读总数（冗余，便于前端角标）。
    """

    items: list[DmMessageResponse]
    next_cursor: int | None = None
    unread_total: int = 0


class CreateConversationRequest(BaseModel):
    """获取或创建会话请求模型。

    Attributes:
        user_id: 对方用户ID。
    """

    user_id: int = Field(..., gt=0, description="对方用户ID")


class CreateConversationResponse(BaseModel):
    """获取或创建会话响应模型。

    Attributes:
        id: 会话ID（新建或已存在）。
        created: 是否新建。
    """

    id: int
    created: bool = False