"""评论管理API端点，提供评论创建、删除、列表查询接口。"""

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_redis
from app.schemas.comment import CommentCreate, CommentListResponse, CommentResponse
from app.services.comment_service import CommentNotFoundError, PostNotFoundError, comment_service

router = APIRouter(tags=["评论"])


def _get_user_id(payload: dict) -> int:
    """从认证载荷中解析当前用户ID。

    Args:
        payload: get_current_user依赖返回的JWT载荷字典。

    Returns:
        当前用户唯一标识。
    """
    return int(payload["sub"])


def _try_get_viewer_id(request: Request) -> int | None:
    """尝试从Cookie解析访问者身份（可选认证，游客返回None）。

    Args:
        request: FastAPI请求对象。

    Returns:
        访问者用户ID，未登录或令牌无效返回None。
    """
    from app.core.security import decode_access_token

    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    return int(payload["sub"]) if payload else None


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建评论",
)
def create_comment(
    post_id: int = Path(..., ge=1, description="帖子ID"),
    data: CommentCreate = ...,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentResponse:
    """创建评论或回复（Transactional Outbox：写评论、计数、事件与通知同事务）。

    一级评论: root_id和reply_user_id不传
    回复评论: root_id=一级评论ID, reply_user_id=被回复者ID

    Args:
        post_id: 帖子ID（路径参数，会覆盖请求体中的post_id）。
        data: 评论创建请求体。
        payload: JWT认证载荷。
        db: 数据库同步会话。

    Returns:
        CommentResponse: 创建成功的评论。

    Raises:
        HTTPException: 帖子不存在404，或创建失败500。
    """
    data.post_id = post_id
    try:
        comment = comment_service.create_comment(db, _get_user_id(payload), data)
    except PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    except Exception:
        raise HTTPException(status_code=500, detail="评论失败")

    # 组装为响应模型
    return comment_service._assemble_comment_responses(db, [comment])[0]


@router.get(
    "/posts/{post_id}/comments",
    response_model=CommentListResponse,
    summary="获取帖子评论列表",
)
def list_comments(
    post_id: int = Path(..., ge=1, description="帖子ID"),
    request: Request = None,
    cursor: int | None = Query(None, ge=1, description="分页游标（上一页最后一条评论ID）"),
    limit: int = Query(20, ge=1, le=50, description="每页条数"),
    sort: str = Query("latest", pattern="^(latest|hot)$", description="排序：latest=最新 hot=最热"),
    db: Session = Depends(get_db),
) -> CommentListResponse:
    """查询帖子的一级评论列表（游标分页，按时间倒序）。

    Args:
        post_id: 帖子ID。
        request: FastAPI请求对象（可选认证）。
        cursor: 分页游标。
        limit: 每页条数。
        sort: 排序方式。
        db: 数据库同步会话。

    Returns:
        CommentListResponse: 分页评论列表。

    Raises:
        HTTPException: 帖子不存在404。
    """
    current_user_id = _try_get_viewer_id(request)
    try:
        return comment_service.list_comments(
            db, post_id, cursor=cursor, limit=limit, sort=sort, current_user_id=current_user_id,
        )
    except PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")


@router.get(
    "/comments/{comment_id}/replies",
    response_model=CommentListResponse,
    summary="获取评论回复列表",
)
def list_replies(
    comment_id: int = Path(..., ge=1, description="一级评论ID"),
    request: Request = None,
    cursor: int | None = Query(None, ge=1, description="分页游标（上一页最后一条回复ID）"),
    limit: int = Query(10, ge=1, le=30, description="每页条数"),
    db: Session = Depends(get_db),
) -> CommentListResponse:
    """查询某条一级评论的回复列表（游标分页，按时间正序）。

    Args:
        comment_id: 一级评论ID。
        request: FastAPI请求对象（可选认证）。
        cursor: 分页游标。
        limit: 每页条数。
        db: 数据库同步会话。

    Returns:
        CommentListResponse: 分页回复列表。
    """
    current_user_id = _try_get_viewer_id(request)
    try:
        return comment_service.list_replies(
            db, comment_id, cursor=cursor, limit=limit, current_user_id=current_user_id,
        )
    except CommentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评论不存在")


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除评论",
)
def delete_comment(
    comment_id: int = Path(..., ge=1, description="评论ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """软删除评论（仅作者可操作，Transactional Outbox：删评论+计数修正+事件同事务）。

    Args:
        comment_id: 评论ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。

    Raises:
        HTTPException: 评论不存在或非作者操作404。
    """
    try:
        comment_service.delete_comment(db, comment_id, _get_user_id(payload))
    except CommentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评论不存在")