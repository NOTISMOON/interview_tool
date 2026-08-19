"""消息通知API端点，提供SSE实时通道与REST CRUD接口。

端点清单:
    GET    /api/v1/messages/stream        SSE 实时通道（增量补偿）
    GET    /api/v1/messages               消息列表（since_id 增量 / cursor 历史翻页）
    GET    /api/v1/messages/unread-count  未读计数
    GET    /api/v1/messages/{id}          消息详情（访问即标记已读）
    PUT    /api/v1/messages/{id}/read     单条标记已读
    PUT    /api/v1/messages/read-all      全部标记已读
    DELETE /api/v1/messages/{id}          删除单条通知
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db, get_current_user
from app.core.config import settings
from app.db.async_session import AsyncSessionLocal
from app.schemas.message import MessageListResponse, MessageResponse, UnreadCountResponse
from app.services.notification_service import notification_service
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["消息通知"])


def _get_user_id(payload: dict) -> int:
    """从认证载荷中解析当前用户ID。

    Args:
        payload: get_current_user依赖返回的JWT载荷字典。

    Returns:
        当前用户唯一标识。
    """
    return int(payload["sub"])


# ------------------------------------------------------------------
# SSE 实时通道
# ------------------------------------------------------------------


@router.get("/stream", summary="SSE 实时消息通道")
async def message_stream(
    request: Request,
    since_id: int | None = Query(None, ge=0, description="增量起点：返回 id > since_id 的消息"),
    payload: dict = Depends(get_current_user),
):
    """SSE 长连接端点，建立后推送增量补偿消息（最多10条）并进入实时 Pub/Sub 监听。

    支持通过 query ?since_id= 或请求头 Last-Event-ID 指定增量起点。
    每15秒发送 keepalive 注释帧防止 Nginx 超时断连。

    注意：端点不注入 get_async_db 会话——依赖会话的生命周期与整个 SSE 连接相同，
    会长期占用连接池；补偿查询改用短生命周期的 AsyncSessionLocal，查完立即归还。

    Args:
        request: FastAPI 请求对象（用于读取 Last-Event-ID 头）。
        since_id: query 增量起点（优先级高于 Last-Event-ID 头）。
        payload: JWT 认证载荷。

    Returns:
        StreamingResponse (text/event-stream)。
    """
    user_id = _get_user_id(payload)

    # 解析增量起点：query.since_id > header[Last-Event-ID] > NULL
    effective_since_id = since_id
    if effective_since_id is None:
        last_event_id = request.headers.get("Last-Event-ID")
        if last_event_id:
            try:
                effective_since_id = int(last_event_id)
            except (ValueError, TypeError):
                pass

    async def generate():
        """SSE 事件生成器，先推送补偿消息，再进入实时监听。"""
        queue = None
        connect_started_at = time.monotonic()
        pushed_events = 0  # 实时下发事件计数（结束日志统计用）
        try:
            # 1. 建立 SSE 连接（注册本地队列 + 启动 Pub/Sub 监听）
            queue = await sse_manager.connect(user_id)
            logger.info(
                "SSE连接建立 user_id=%s since_id=%s since_id_source=%s",
                user_id,
                effective_since_id,
                "query" if since_id is not None else ("header" if request.headers.get("Last-Event-ID") else "none"),
            )

            # 2. 增量补偿查询（最多10条）
            #    短生命周期会话：async with 结束即归还连接，不随长连接占用连接池
            catchup_started_at = time.monotonic()
            async with AsyncSessionLocal() as db:
                catchup = await notification_service.get_list_since_id(
                    db, user_id, effective_since_id, settings.SSE_CATCHUP_LIMIT
                )
            logger.info(
                "SSE补偿查询完成 user_id=%s since_id=%s catchup_count=%s unread_total=%s latest_id=%s query_elapsed_ms=%d",
                user_id,
                effective_since_id,
                len(catchup.items),
                catchup.unread_total,
                catchup.items[0].id if catchup.items else None,
                (time.monotonic() - catchup_started_at) * 1000,
            )

            # 3. 先推送补偿消息（按 id 升序，客户端按时间顺序展示；by_alias 与 REST 字段一致）
            for msg in reversed(catchup.items):
                yield _format_sse_event(
                    event="message",
                    event_id=msg.id,
                    data=msg.model_dump(mode="json", by_alias=True),
                )

            # 4. 推送未读计数（与实时 unread_count 事件载荷结构保持一致）
            yield _format_sse_event(
                event="unread_count",
                data=json.dumps({"total": catchup.unread_total, "by_type": {}}, ensure_ascii=False),
            )

            # 5. 发送 retry 间隔（建议浏览器重连间隔 3s）
            yield f"retry: {settings.SSE_RETRY_INTERVAL_MS}\n\n"

            # 6. 进入实时监听循环
            keepalive_interval = settings.SSE_KEEPALIVE_INTERVAL
            last_keepalive = asyncio.get_event_loop().time()

            while True:
                # 检查客户端是否断开
                if await request.is_disconnected():
                    logger.info("SSE客户端已断开 user_id=%s", user_id)
                    break

                try:
                    # 等待新消息（带超时，用于发送 keepalive）
                    event_data = await asyncio.wait_for(queue.get(), timeout=keepalive_interval)

                    # 防护：跳过非字典的异常载荷，避免污染流
                    if not isinstance(event_data, dict):
                        logger.warning("SSE 收到非字典事件，已跳过 user_id=%s data=%r", user_id, event_data)
                        continue

                    # 根据事件类型格式化 SSE 帧
                    kind = event_data.get("kind", "message")

                    if kind == "unread_count":
                        # 剔除控制字段 kind，仅输出 total/by_type
                        payload = {k: v for k, v in event_data.items() if k != "kind"}
                        yield _format_sse_event(
                            event="unread_count",
                            data=json.dumps(payload, ensure_ascii=False, default=str),
                        )
                    else:
                        # message / system_broadcast 及未知类型统一按消息体透传
                        msg_data = event_data.get("message", event_data)
                        yield _format_sse_event(
                            event=kind if kind in ("message", "system_broadcast") else "message",
                            event_id=msg_data.get("id"),
                            data=json.dumps(msg_data, ensure_ascii=False, default=str),
                        )

                    pushed_events += 1
                    logger.debug(
                        "SSE事件已下发 user_id=%s kind=%s event_id=%s",
                        user_id,
                        kind,
                        event_data.get("message", {}).get("id") if isinstance(event_data.get("message"), dict) else None,
                    )

                except asyncio.TimeoutError:
                    # 超时发送 keepalive 注释帧
                    now = asyncio.get_event_loop().time()
                    if now - last_keepalive >= keepalive_interval:
                        yield ": keepalive\n\n"
                        last_keepalive = now

        except asyncio.CancelledError:
            logger.info("SSE流已取消（服务端关闭或客户端中断）user_id=%s pushed_events=%s", user_id, pushed_events)
        except Exception:
            logger.exception("SSE 流异常 user_id=%s pushed_events=%s", user_id, pushed_events)
        finally:
            # 仅移除本连接的队列，同一用户其他标签页连接不受影响
            if queue is not None:
                await sse_manager.disconnect(user_id, queue)
            logger.info(
                "SSE连接结束 user_id=%s pushed_events=%s duration_ms=%d",
                user_id,
                pushed_events,
                (time.monotonic() - connect_started_at) * 1000,
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


# ------------------------------------------------------------------
# REST 接口
# ------------------------------------------------------------------


@router.get("", response_model=MessageListResponse, summary="消息列表")
async def list_messages(
    since_id: int | None = Query(None, ge=0, description="增量起点：id > since_id（优先级高于 cursor）"),
    limit: int = Query(10, ge=1, le=10, description="增量模式返回条数（1-10）"),
    cursor: int = Query(0, ge=0, description="翻页游标：上一页最后一条消息ID（since_id 不传时生效）"),
    size: int = Query(20, ge=1, le=50, description="历史翻页每页条数（1-50）"),
    type: str | None = Query(None, description="类型过滤：system/comment/like/follow/interview/dm"),
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> MessageListResponse:
    """查询消息列表，支持增量（since_id）和翻页（cursor）两种模式。

    since_id 与 cursor 同时传入时，since_id 优先。

    Args:
        since_id: 增量起点。
        limit: 增量返回条数（服务端强制 clamp 到 [1, 10]）。
        cursor: 翻页游标。
        size: 翻页每页条数（clamp 到 [1, 50]）。
        type: 类型过滤（可选）。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        MessageListResponse: 消息列表 + 翻页游标 + 未读总数。
    """
    user_id = _get_user_id(payload)

    # 类型名称转类型ID
    type_id: int | None = None
    if type:
        from app.models.message import (
            MESSAGE_TYPE_COMMENT,
            MESSAGE_TYPE_DM,
            MESSAGE_TYPE_FOLLOW,
            MESSAGE_TYPE_INTERVIEW,
            MESSAGE_TYPE_LIKE,
            MESSAGE_TYPE_SYSTEM,
        )

        type_map = {
            "system": MESSAGE_TYPE_SYSTEM,
            "comment": MESSAGE_TYPE_COMMENT,
            "like": MESSAGE_TYPE_LIKE,
            "follow": MESSAGE_TYPE_FOLLOW,
            "interview": MESSAGE_TYPE_INTERVIEW,
            "dm": MESSAGE_TYPE_DM,
        }
        type_id = type_map.get(type.lower())

    if since_id is not None:
        return await notification_service.get_list_since_id(db, user_id, since_id, limit)
    return await notification_service.get_list_cursor(db, user_id, cursor, size, type_id)


@router.get("/unread-count", response_model=UnreadCountResponse, summary="未读计数")
async def get_unread_count(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> UnreadCountResponse:
    """获取当前用户未读计数（含分类汇总）。

    Args:
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        UnreadCountResponse: 总数 + 分类汇总。
    """
    return await notification_service.get_unread_count(db, _get_user_id(payload))


@router.get("/{message_id}", response_model=MessageResponse, summary="消息详情")
async def get_message_detail(
    message_id: int = Path(..., ge=1, description="消息ID"),
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> MessageResponse:
    """获取消息详情（访问即标记已读，幂等）。

    Args:
        message_id: 消息ID。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        MessageResponse: 消息详情。

    Raises:
        HTTPException: 消息不存在或不属于当前用户时返回404。
    """
    user_id = _get_user_id(payload)
    result = await notification_service.get_message_detail(db, user_id, message_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")
    return result


@router.put("/{message_id}/read", summary="单条标记已读")
async def mark_message_read(
    message_id: int = Path(..., ge=1, description="消息ID"),
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """标记单条消息为已读（幂等：已读消息重复调用仍返回成功），并同步推送 unread_count SSE 事件。

    Args:
        message_id: 消息ID。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        操作结果字典。

    Raises:
        HTTPException: 消息不存在或不属于当前用户时返回404。
    """
    user_id = _get_user_id(payload)

    # 先校验存在性：仅消息不存在时404；已读消息幂等返回成功
    message = await notification_service.get_message(db, user_id, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")

    await notification_service.mark_read(db, user_id, message_id)

    # 推送更新后的未读数
    unread = await notification_service.get_unread_count(db, user_id)
    await notification_service.publish_to_user(
        user_id,
        {"kind": "unread_count", "total": unread.total, "by_type": unread.by_type},
    )

    return {"ok": True}


@router.put("/read-all", summary="全部标记已读")
async def mark_all_messages_read(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """标记所有消息为已读，并同步推送 unread_count=0 SSE 事件。

    Args:
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        操作结果字典（含已读数量）。
    """
    user_id = _get_user_id(payload)
    count = await notification_service.mark_all_read(db, user_id)

    # 推送清零后的未读数
    await notification_service.publish_to_user(
        user_id,
        {"kind": "unread_count", "total": 0, "by_type": {}},
    )

    return {"ok": True, "count": count}


@router.delete("/{message_id}", summary="删除单条通知")
async def delete_message(
    message_id: int = Path(..., ge=1, description="消息ID"),
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """删除单条通知消息。

    Args:
        message_id: 消息ID。
        payload: JWT 认证载荷。
        db: 数据库异步会话。

    Returns:
        操作结果字典。

    Raises:
        HTTPException: 消息不存在时返回404。
    """
    user_id = _get_user_id(payload)
    ok = await notification_service.delete_message(db, user_id, message_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")
    return {"ok": True}


def _format_sse_event(event: str, data: str, event_id: int | None = None) -> str:
    """格式化单条 SSE 事件帧。

    Args:
        event: 事件类型名称。
        data: 事件数据（JSON 字符串）。
        event_id: 事件ID（对应 message.id）。

    Returns:
        符合 SSE 规范的字符串帧。
    """
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    # 多行数据每行加 "data: " 前缀
    for line in data.split("\n"):
        lines.append(f"data: {line}")
    lines.append("")  # 空行结束
    return "\n".join(lines) + "\n"