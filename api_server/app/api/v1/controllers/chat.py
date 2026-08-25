"""私信 WebSocket 端点与 REST 读路径接口（M1-M3）。

端点清单：
    WS   /api/v1/chat/ws                     私信长连接：接收 send，写 Redis Stream，回执 + 跨实例推送
    GET  /api/v1/chat/conversations          会话列表（含对方信息 + 未读数 + 最后消息）
    POST /api/v1/chat/conversations          获取或创建与某用户的会话（他人主页进入）
    GET  /api/v1/chat/conversations/{id}/messages  会话历史分页 + 标记已读

M1 写路径流程（WS 接收一条 send）：
    1. 握手鉴权：从 Cookie 读取 access_token 解析出 user_id；无效则 4001 关闭。
    2. 循环接收 JSON，校验 WSSendMessage。
    3. 将消息写入会话 Redis Stream（幂等 + 保序，见 app/redis/chat_stream.py）。
    4. 写缓冲成功 → 回执 sent+seq；重复 → 回执 duplicate+seq。
    5. 新消息经 Pub/Sub 跨实例推送接收方（由 chat_connection_manager.publish_to_user 承载）。
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db, get_current_user
from app.core.security import decode_access_token
from app.redis.chat_stream import append_message, is_duplicate
from app.repositories.chat_repository import chat_repository
from app.schemas.chat import (
    ConversationListResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    MessageListResponse,
    WSMessageAck,
    WSSendMessage,
    WSErrorAck,
)
from app.services.chat_connection_manager import chat_connection_manager
from app.services.chat_service import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["私信"])


def _user_id(payload: dict) -> int:
    """从认证载荷中解析当前用户ID。

    Args:
        payload: get_current_user 依赖返回的 JWT 载荷。

    Returns:
        当前用户唯一标识。
    """
    return int(payload["sub"])


def _ws_user_id(websocket: WebSocket) -> int | None:
    """从 WS 握手 Cookie 中解析当前登录用户ID。

    私信 WS 走同源 HttpOnly Cookie 认证（与 API 一致），token 不下发前端 JS。

    Args:
        websocket: WebSocket 连接对象。

    Returns:
        用户ID；未认证/令牌无效返回 None。
    """
    token = websocket.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket) -> None:
    """私信 WebSocket 长连接端点。

    处理客户端私信发送请求：写 Redis Stream 写缓冲、回执、跨实例推送接收方。

    Args:
        websocket: FastAPI WebSocket 连接对象。
    """
    user_id = _ws_user_id(websocket)
    if user_id is None:
        await websocket.close(code=4001, reason="未认证")
        return

    await websocket.accept()
    await chat_connection_manager.connect(user_id, websocket)
    logger.info("私信WS握手成功 user_id=%s remote=%s", user_id, websocket.client)

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_send_message(websocket, user_id, raw)
    except WebSocketDisconnect:
        logger.info("私信WS客户端断开 user_id=%s", user_id)
    except Exception:
        logger.exception("私信WS处理异常 user_id=%s", user_id)
    finally:
        await chat_connection_manager.disconnect(user_id, websocket)


async def _handle_send_message(websocket: WebSocket, user_id: int, raw: str) -> None:
    """处理单条客户端私信发送请求。

    Args:
        websocket: 当前连接。
        user_id: 当前用户ID（发送方）。
        raw: 客户端原始 JSON 文本。
    """
    try:
        msg = WSSendMessage.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning("私信WS入站消息校验失败 user_id=%s err=%s", user_id, exc.errors()[:2])
        await websocket.send_text(
            WSErrorAck(client_msg_id=None, error="消息格式错误").model_dump_json()
        )
        return
    except json.JSONDecodeError:
        logger.warning("私信WS收到非JSON消息 user_id=%s", user_id)
        await websocket.send_text(
            WSErrorAck(client_msg_id=None, error="消息不是合法JSON").model_dump_json()
        )
        return

    # 发送方强制为当前登录用户，防止越权（不信任客户端传入的身份）
    sender_id = user_id

    try:
        # 幂等预检（低成本）；最终以 Lua/DB 唯一索引为准
        if await is_duplicate(msg.conversation_id, msg.client_msg_id):
            # 重复发送：查询已分配 seq 并回执（append_message 的重复分支幂等返回）
            _existed, seq = await append_message(
                msg.conversation_id,
                sender_id,
                msg.receiver_id,
                msg.client_msg_id,
                msg.content,
                msg.content_type,
            )
            await websocket.send_text(
                WSMessageAck(
                    action="duplicate",
                    client_msg_id=msg.client_msg_id,
                    conversation_id=msg.conversation_id,
                    seq=seq,
                    status="ok",
                ).model_dump_json()
            )
            return

        is_new, seq = await append_message(
            msg.conversation_id,
            sender_id,
            msg.receiver_id,
            msg.client_msg_id,
            msg.content,
            msg.content_type,
        )

        # 回执发送方（乐观渲染确认）
        await websocket.send_text(
            WSMessageAck(
                action="sent" if is_new else "duplicate",
                client_msg_id=msg.client_msg_id,
                conversation_id=msg.conversation_id,
                seq=seq,
                status="ok",
            ).model_dump_json()
        )

        # 新消息：跨实例推送接收方（接收方不在本实例时由持有其连接的实例推送）
        if is_new:
            await chat_connection_manager.publish_to_user(
                msg.receiver_id,
                {
                    "action": "new_message",
                    "conversation_id": msg.conversation_id,
                    "from_user_id": sender_id,
                    "client_msg_id": msg.client_msg_id,
                    "content": msg.content,
                    "content_type": msg.content_type,
                    "seq": seq,
                },
            )
    except Exception:
        logger.exception("私信写缓冲失败 user_id=%s cmid=%s", user_id, msg.client_msg_id)
        await websocket.send_text(
            WSErrorAck(client_msg_id=msg.client_msg_id, error="发送失败，请重试").model_dump_json()
        )


# ------------------------------------------------------------------
# REST 读路径（M3）
# ------------------------------------------------------------------


@router.get("/conversations", response_model=ConversationListResponse, summary="私信会话列表")
async def list_conversations(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> ConversationListResponse:
    """查询当前用户的私信会话列表（含对方信息与未读数）。

    Args:
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        会话列表响应。
    """
    user_id = _user_id(payload)
    items = await chat_service.list_conversations(db, user_id)
    return ConversationListResponse(items=items)


@router.post(
    "/conversations",
    response_model=CreateConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="获取或创建私信会话",
)
async def create_conversation(
    body: CreateConversationRequest,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> CreateConversationResponse:
    """获取或创建与指定用户的私信会话。

    他人主页点击"发私信"时调用，返回会话ID；已存在则直接复用。

    Args:
        body: 请求体（对方 user_id）。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        创建响应（含 id 与 created 标记）。

    Raises:
        HTTPException: 与自己私信时返回 400。
    """
    user_id = _user_id(payload)
    if body.user_id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能与自己私信")
    result = await chat_service.get_or_create_conversation(db, user_id, body.user_id)
    return result


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="私信会话历史消息",
)
async def list_conversation_messages(
    conversation_id: int = Path(..., ge=1, description="会话ID"),
    cursor: int = Query(0, ge=0, description="翻页游标：上一页最小 seq，0 取最新一页"),
    size: int = Query(20, ge=1, le=50, description="每页条数"),
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> MessageListResponse:
    """分页查询会话历史消息（最新在前），并将会话中发给当前用户的未读标记为已读、清未读缓存。

    Args:
        conversation_id: 会话ID。
        cursor: 翻页游标。
        size: 每页条数。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        消息列表响应。

    Raises:
        HTTPException: 会话不存在或非成员时返回 404。
    """
    user_id = _user_id(payload)
    result = await chat_service.list_messages(db, conversation_id, user_id, cursor, size)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    # 读取会话（首次打开/首页）时清未读：DB 置已读 + Redis 未读 hash 清空
    if cursor <= 0:
        # 打开会话即取消隐藏（从用户主页"私信"进入或重新访问时恢复会话显示）
        await chat_service.unhide_conversation(db, conversation_id, user_id)
        await chat_repository.mark_conversation_read(db, conversation_id, user_id)
        await db.commit()
        from app.redis.sync_client import SyncRedisClient

        redis_client = SyncRedisClient.get_client()
        redis_client.hdel(f"unread:{user_id}", str(conversation_id))

    return result


@router.put(
    "/conversations/{conversation_id}/read",
    status_code=status.HTTP_200_OK,
    summary="标记会话为已读",
)
async def mark_conversation_read(
    conversation_id: int = Path(..., ge=1, description="会话ID"),
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """将会话中发给当前用户的未读消息标记为已读，并清 Redis 未读计数。

    聊天页实时收到对方新消息时调用，保证停留聊天页时未读即时清零。

    Args:
        conversation_id: 会话ID。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        操作结果字典（含已读数）。
    """
    user_id = _user_id(payload)
    conv = await chat_repository.get_conversation(db, conversation_id, user_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    count = await chat_repository.mark_conversation_read(db, conversation_id, user_id)
    await db.commit()

    from app.redis.sync_client import SyncRedisClient

    redis_client = SyncRedisClient.get_client()
    redis_client.hdel(f"unread:{user_id}", str(conversation_id))
    return {"ok": True, "count": count}


@router.put(
    "/conversations/{conversation_id}/hide",
    status_code=status.HTTP_200_OK,
    summary="隐藏私信会话",
)
async def hide_conversation(
    conversation_id: int = Path(..., ge=1, description="会话ID"),
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """隐藏私信会话（仅对当前用户生效），并清除该会话未读。

    隐藏后会话从列表消失；对方再来新消息或重新打开会话时自动恢复。

    Args:
        conversation_id: 会话ID。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        操作结果字典。

    Raises:
        HTTPException: 会话不存在或非成员时返回404。
    """
    user_id = _user_id(payload)
    ok = await chat_service.hide_conversation(db, conversation_id, user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    await db.commit()
    return {"ok": True}


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="删除私信会话",
)
async def delete_conversation(
    conversation_id: int = Path(..., ge=1, description="会话ID"),
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """删除私信会话：软删自己的历史消息 + 隐藏会话（仅影响当前用户）。

    Args:
        conversation_id: 会话ID。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        操作结果字典。

    Raises:
        HTTPException: 会话不存在或非成员时返回404。
    """
    user_id = _user_id(payload)
    ok = await chat_service.delete_conversation(db, conversation_id, user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    await db.commit()
    return {"ok": True}