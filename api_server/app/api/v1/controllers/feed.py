"""Feed API控制器，提供用户信息流端点。"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_redis
from app.repositories.favorite_repository import favorite_repository
from app.repositories.like_repository import like_repository
from app.repositories.post_repository import post_repository
from app.repositories.user_repository import sync_user_repository
from app.schemas.post import PostAuthor, PostListItem, PostListResponse
from app.services.feed_service import feed_service

router = APIRouter(prefix="/feed", tags=["feed"])

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


def _assemble_feed_item(
    db: Session,
    post,
    user_id: int,
) -> PostListItem:
    """组装Feed帖子项（含作者信息、标签、互动状态）。

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
        cover_url=post.cover_url,
        images_count=len(post.images) if isinstance(post.images, list) else 0,
        tags=tags if tags else [],
        likes_count=post.likes_count,
        comments_count=post.comments_count,
        views_count=post.views_count,
        is_hot=bool(post.is_hot),
        is_liked=is_liked,
        is_favorited=is_favorited,
        created_at=post.created_at,
    )


@router.get(
    "",
    response_model=PostListResponse,
    summary="获取用户信息流",
    status_code=status.HTTP_200_OK,
)
def get_feed(
    cursor: int | None = Query(None, ge=1, description="游标（上一页最后一条帖子ID）"),
    limit: int = Query(20, ge=1, le=50, description="每页条数"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis),
) -> PostListResponse:
    """获取当前用户的个性化信息流（需要登录）。

    信息流包含关注者帖子 + 热门推荐，按时间倒序游标分页。
    """
    user_id = _get_user_id(payload)

    # 获取Feed帖子ID列表
    post_ids, next_cursor = feed_service.get_feed(
        db, redis_client, user_id, cursor=cursor, limit=limit
    )

    if not post_ids:
        return PostListResponse(items=[], next_cursor=None)

    # 查DB获取帖子详情
    posts_map = post_repository.batch_get_by_ids(db, post_ids)
    ordered_posts = [posts_map[pid] for pid in post_ids if pid in posts_map]

    # 读路径兜底过滤（BUG2）：缓存仅存 post_id、可能残留已取关作者的帖子
    # （如旧代码时期产生的脏缓存 / 清理失败的并发窗口）。以当前关注关系
    # 为准过滤作者，保证任何缓存状态下都不会返回已取关人的帖子。
    following_ids = set(sync_user_repository.get_following_ids(db, user_id))
    if following_ids:
        ordered_posts = [p for p in ordered_posts if p.author_id in following_ids]
    else:
        ordered_posts = []

    # 组装响应
    items = [_assemble_feed_item(db, p, user_id) for p in ordered_posts]

    return PostListResponse(items=items, next_cursor=next_cursor)