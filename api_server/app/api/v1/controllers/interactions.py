"""互动 API 控制器（点赞/收藏），提供切换点赞、切换收藏、收藏列表端点。"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_redis
from app.repositories.favorite_repository import favorite_repository
from app.repositories.like_repository import like_repository
from app.repositories.post_repository import post_repository
from app.repositories.user_repository import sync_user_repository
from app.schemas.post import PostAuthor, PostListItem, PostListResponse
from app.services.interaction_service import InteractionService, PostNotFoundError

router = APIRouter(prefix="/posts", tags=["interactions"])

# 模块级单例
_interaction_service = InteractionService()

# 内容预览截断长度
CONTENT_PREVIEW_LENGTH = 150


def _get_user_id(payload: dict) -> int:
    """从JWT payload中提取用户ID。

    Args:
        payload: JWT解析后的字典（sub字段为字符串用户ID）。

    Returns:
        用户ID（int）。
    """
    return int(payload["sub"])


def _assemble_list_item(
    db: Session,
    post,
    user_id: int,
) -> PostListItem:
    """组装帖子列表项（含作者信息、标签、互动状态）。

    Args:
        db: 数据库同步会话。
        post: Post ORM对象。
        user_id: 当前用户ID。

    Returns:
        PostListItem。
    """
    author = sync_user_repository.get_by_id(db, post.author_id)
    author_info = None
    if author:
        author_info = PostAuthor(id=author.id, nickname=author.nickname, avatar=author.avatar)

    tags = post_repository.get_tags_by_post_id(db, post.id)

    content_preview = post.content[:CONTENT_PREVIEW_LENGTH]
    if len(post.content) > CONTENT_PREVIEW_LENGTH:
        content_preview += "..."

    is_liked = like_repository.is_liked(db, post.id, user_id)
    is_favorited = favorite_repository.is_favorited(db, post.id, user_id)

    return PostListItem(
        id=post.id,
        author=author_info,
        title=post.title,
        content_preview=content_preview,
        tags=tags if tags else [],
        likes_count=post.likes_count,
        comments_count=post.comments_count,
        views_count=post.views_count,
        is_pinned=bool(post.is_pinned),
        is_hot=bool(post.is_hot),
        is_liked=is_liked,
        is_favorited=is_favorited,
        created_at=post.created_at,
    )


@router.post(
    "/{post_id}/like",
    response_model=dict,
    summary="切换点赞状态",
    status_code=status.HTTP_200_OK,
)
def toggle_like(
    post_id: int = Path(..., ge=1, description="帖子ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis),
) -> dict:
    """切换帖子点赞状态（需要登录）。

    已点赞→取消，未点赞→点赞。返回 is_liked 和 likes_count。
    """
    user_id = _get_user_id(payload)
    try:
        return _interaction_service.toggle_like(db, redis_client, post_id, user_id)
    except PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")


@router.post(
    "/{post_id}/favorite",
    response_model=dict,
    summary="切换收藏状态",
    status_code=status.HTTP_200_OK,
)
def toggle_favorite(
    post_id: int = Path(..., ge=1, description="帖子ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis),
) -> dict:
    """切换帖子收藏状态（需要登录）。

    已收藏→取消，未收藏→收藏。返回 is_favorited。
    """
    user_id = _get_user_id(payload)
    try:
        return _interaction_service.toggle_favorite(db, redis_client, post_id, user_id)
    except PostNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")


@router.get(
    "/favorites",
    response_model=PostListResponse,
    summary="收藏列表",
    status_code=status.HTTP_200_OK,
)
def list_favorites(
    cursor: int | None = Query(None, ge=1, description="游标（上一页最后一条收藏ID）"),
    limit: int = Query(20, ge=1, le=50, description="每页条数"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostListResponse:
    """获取当前用户的收藏列表（游标分页，按收藏时间倒序）。

    需要登录，仅返回收藏者本人可见。
    """
    user_id = _get_user_id(payload)
    favorites = favorite_repository.list_favorites(db, user_id, cursor=cursor, limit=limit)
    post_ids = [f.post_id for f in favorites]
    if not post_ids:
        return PostListResponse(items=[], next_cursor=None)

    posts_map = post_repository.batch_get_by_ids(db, post_ids)
    ordered_posts = [posts_map[pid] for pid in post_ids if pid in posts_map]

    items = [_assemble_list_item(db, p, user_id) for p in ordered_posts]
    next_cursor = favorites[-1].id if len(favorites) == limit else None
    return PostListResponse(items=items, next_cursor=next_cursor)