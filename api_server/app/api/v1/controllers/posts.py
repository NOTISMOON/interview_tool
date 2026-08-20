"""帖子管理API端点，提供发帖、查帖、改帖、删帖接口。"""

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_redis
from app.schemas.post import PostCreate, PostListResponse, PostResponse, PostUpdate
from app.services.post_service import PostNotFoundError, post_service

router = APIRouter(prefix="/posts", tags=["帖子"])


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
    "/",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建帖子",
)
def create_post(
    data: PostCreate,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> PostResponse:
    """创建新帖子（Transactional Outbox：写帖子、标签、计数与事件同事务）。

    Args:
        data: 帖子创建请求体。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        PostResponse: 创建成功的帖子详情。

    Raises:
        HTTPException: 创建失败时返回500。
    """
    try:
        post = post_service.create_post(db, cache_client, _get_user_id(payload), data)
    except Exception:
        raise HTTPException(status_code=500, detail="创建帖子失败")
    return post_service.get_post_detail(db, cache_client, post.id, _get_user_id(payload))


@router.get(
    "/{post_id}",
    response_model=PostResponse,
    summary="获取帖子详情",
)
def get_post_detail(
    post_id: int = Path(..., ge=1, description="帖子ID"),
    request: Request = None,
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> PostResponse:
    """获取帖子详情（含作者信息、标签，游客可查看）。

    Args:
        post_id: 帖子ID。
        request: FastAPI请求对象（用于可选认证）。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        PostResponse: 帖子详情。

    Raises:
        HTTPException: 帖子不存在或已删除时返回404。
    """
    current_user_id = _try_get_viewer_id(request)
    try:
        return post_service.get_post_detail(db, cache_client, post_id, current_user_id)
    except PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")


@router.get(
    "/",
    response_model=PostListResponse,
    summary="获取帖子列表",
)
def list_posts(
    request: Request = None,
    author_id: int | None = Query(None, ge=1, description="作者ID（不传则查全站）"),
    sort: str = Query("latest", pattern="^(latest|hot|pinned)$", description="排序方式：latest=最新 hot=热门 pinned=置顶优先"),
    cursor: int | None = Query(None, ge=1, description="分页游标（上一页最后一条帖子ID）"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> PostListResponse:
    """分页查询帖子列表（游标分页，按帖子ID降序）。

    Args:
        request: FastAPI请求对象（用于可选认证）。
        author_id: 作者ID（不传=全站，传了=某人发的帖子）。
        sort: 排序方式。
        cursor: 分页游标。
        limit: 每页条数。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        PostListResponse: 分页帖子列表。
    """
    current_user_id = _try_get_viewer_id(request)
    return post_service.list_posts(
        db,
        author_id=author_id,
        sort=sort,
        cursor=cursor,
        limit=limit,
        current_user_id=current_user_id,
    )


@router.put(
    "/{post_id}",
    response_model=PostResponse,
    summary="更新帖子",
)
def update_post(
    post_id: int = Path(..., ge=1, description="帖子ID"),
    data: PostUpdate = ...,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> PostResponse:
    """更新帖子标题/正文/标签（仅作者可操作）。

    Args:
        post_id: 帖子ID。
        data: 帖子更新请求体。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        PostResponse: 更新后的帖子详情。

    Raises:
        HTTPException: 帖子不存在或非作者操作时返回404。
    """
    try:
        post = post_service.update_post(db, post_id, _get_user_id(payload), data)
    except PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    return post_service.get_post_detail(db, cache_client, post.id, _get_user_id(payload))


@router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除帖子",
)
def delete_post(
    post_id: int = Path(..., ge=1, description="帖子ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> None:
    """软删除帖子（仅作者可操作，Transactional Outbox：删帖+计数修正+事件同事务）。

    Args:
        post_id: 帖子ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Raises:
        HTTPException: 帖子不存在或非作者操作时返回404。
    """
    try:
        post_service.soft_delete_post(db, cache_client, post_id, _get_user_id(payload))
    except PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")