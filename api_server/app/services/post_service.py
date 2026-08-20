"""帖子业务逻辑层。

写路径: 创建/更新/删除采用 Transactional Outbox——业务变更与事件写入同一个MySQL本地事务，
    事务提交即保证事件不丢；独立Relay轮询outbox_event投递RabbitMQ，Consumer异步
    同步缓存与Feed（最终一致，秒级）。写接口不等待MQ/Redis，DB事务内完成全部操作。

读路径: 详情走Cache-Aside（缓存穿透/击穿防护），列表走DB直查+批量作者信息组装。
"""

import json
import logging
from datetime import datetime

import redis
from sqlalchemy.orm import Session

from app.models.post import POST_STATUS_DELETED, POST_STATUS_NORMAL, Post
from app.repositories.outbox_repository import sync_outbox_repository
from app.repositories.post_repository import post_repository
from app.repositories.user_repository import sync_user_repository
from app.schemas.post import PostCreate, PostListItem, PostListResponse, PostResponse, PostUpdate

logger = logging.getLogger(__name__)

# 帖子正文摘要长度
CONTENT_PREVIEW_LENGTH = 200


class PostNotFoundError(Exception):
    """帖子不存在或已删除（路由层转404）。"""


class PostService:
    """帖子业务逻辑层（同步），编排帖子的创建、更新、删除与查询。"""

    # ------------------------------------------------------------------
    # 写路径：创建/更新/删除（Transactional Outbox）
    # ------------------------------------------------------------------

    def create_post(self, db: Session, cache_client: redis.Redis, author_id: int, data: PostCreate) -> Post:
        """创建帖子：单事务内写帖子、标签、计数与Outbox事件。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端（事务提交后失效作者资料缓存）。
            author_id: 作者用户ID。
            data: 帖子创建请求数据。

        Returns:
            创建成功的Post ORM对象。
        """
        now = datetime.now()
        with db.begin():
            # ① 创建帖子
            post = post_repository.create(
                db,
                author_id=author_id,
                title=data.title,
                content=data.content,
                cover_url=data.cover_url,
                images=data.images if data.images else None,
            )
            post_id = post.id

            # ② 写标签关联
            if data.tags:
                post_repository.create_tags(db, post_id, data.tags)

            # ③ Outbox事件：post.created（供Feed Push、用户动态等Consumer消费）
            sync_outbox_repository.insert_event(
                db,
                event_type="post.created",
                aggregate_type="post",
                aggregate_id=str(post_id),
                payload={
                    "post_id": post_id,
                    "author_id": author_id,
                    "title": data.title,
                    "tags": data.tags,
                    "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_at_ms": int(now.timestamp() * 1000),
                },
            )

            # ④ 帖子事件（用户动态）
            sync_outbox_repository.insert_event(
                db,
                event_type="post.event",
                aggregate_type="user_activity",
                aggregate_id=str(author_id),
                payload={
                    "user_id": author_id,
                    "activity_type": 4,  # 发帖动态
                    "related_id": post_id,
                    "content": f"发布了帖子《{data.title}》",
                },
            )

            # ⑤ 作者发帖数+1
            post_repository.increment_posts_count(db, author_id)

        # 事务提交后失效作者资料缓存（发帖数已变更）
        from app.services.user_service import user_service

        user_service.invalidate_profile_cache(cache_client, author_id)
        logger.info("帖子创建成功 post_id=%s author_id=%s", post_id, author_id)
        return post

    def update_post(self, db: Session, post_id: int, author_id: int, data: PostUpdate) -> Post:
        """更新帖子标题/正文/标签（仅作者可更新）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            author_id: 请求者用户ID（用于权限校验）。
            data: 帖子更新请求数据。

        Returns:
            更新后的Post ORM对象。

        Raises:
            PostNotFoundError: 帖子不存在或已删除，或非作者操作。
        """
        post = post_repository.get_by_id(db, post_id)
        if post is None or post.author_id != author_id:
            raise PostNotFoundError("帖子不存在")

        update_fields: dict = {}
        if data.title is not None:
            update_fields["title"] = data.title
        if data.content is not None:
            update_fields["content"] = data.content
        if data.cover_url is not None:
            update_fields["cover_url"] = data.cover_url
        if data.images is not None:
            update_fields["images"] = json.dumps(data.images, ensure_ascii=False)
        if data.tags is not None:
            update_fields["tags"] = json.dumps(data.tags, ensure_ascii=False)

        if update_fields:
            # 结束校验查询产生的隐式事务（SQLAlchemy 2.0 autobegin），否则 db.begin() 报错
            db.rollback()
            with db.begin():
                post_repository.update(db, post_id, update_fields)
                # 标签全量替换
                if data.tags is not None:
                    post_repository.delete_tags_by_post_id(db, post_id)
                    if data.tags:
                        post_repository.create_tags(db, post_id, data.tags)

        # 重新查询最新数据
        db.refresh(post)
        logger.info("帖子更新成功 post_id=%s", post_id)
        return post

    def soft_delete_post(self, db: Session, cache_client: redis.Redis, post_id: int, author_id: int) -> None:
        """软删除帖子：单事务内删帖子、计数修正与Outbox事件。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端（事务提交后失效缓存）。
            post_id: 帖子ID。
            author_id: 请求者用户ID（用于权限校验）。

        Raises:
            PostNotFoundError: 帖子不存在或已删除，或非作者操作。
        """
        post = post_repository.get_by_id(db, post_id)
        if post is None or post.author_id != author_id:
            raise PostNotFoundError("帖子不存在")
        post_author_id = post.author_id

        now = datetime.now()
        # 结束校验查询产生的隐式事务（SQLAlchemy 2.0 autobegin），否则 db.begin() 报错
        db.rollback()
        with db.begin():
            deleted = post_repository.soft_delete(db, post_id)
            if not deleted:
                raise PostNotFoundError("帖子不存在")

            # ① Outbox事件：post.deleted
            sync_outbox_repository.insert_event(
                db,
                event_type="post.deleted",
                aggregate_type="post",
                aggregate_id=str(post_id),
                payload={
                    "post_id": post_id,
                    "author_id": post_author_id,
                    "deleted_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "deleted_at_ms": int(now.timestamp() * 1000),
                },
            )

            # ② 作者发帖数-1
            post_repository.decrement_posts_count(db, post_author_id)

        # 事务提交后失效缓存
        self._invalidate_detail_cache(cache_client, post_id)
        from app.services.user_service import user_service

        user_service.invalidate_profile_cache(cache_client, post_author_id)
        logger.info("帖子删除成功 post_id=%s author_id=%s", post_id, post_author_id)

    # ------------------------------------------------------------------
    # 读路径：详情/列表
    # ------------------------------------------------------------------

    def get_post_detail(
        self,
        db: Session,
        cache_client: redis.Redis,
        post_id: int,
        current_user_id: int | None = None,
    ) -> PostResponse:
        """查询帖子详情（含作者信息、标签、是否点赞/收藏）。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端（用于缓存读写）。
            post_id: 帖子ID。
            current_user_id: 当前登录用户ID（游客为None，不查询互动状态）。

        Returns:
            PostResponse响应模型。

        Raises:
            PostNotFoundError: 帖子不存在或已删除。
        """
        post = post_repository.get_by_id(db, post_id)
        if post is None:
            raise PostNotFoundError("帖子不存在")

        return self._assemble_post_response(db, post, current_user_id)

    def list_posts(
        self,
        db: Session,
        *,
        author_id: int | None = None,
        sort: str = "latest",
        cursor: int | None = None,
        limit: int = 20,
        current_user_id: int | None = None,
    ) -> PostListResponse:
        """分页查询帖子列表（含作者信息、标签）。

        Args:
            db: 数据库同步会话。
            author_id: 作者ID（None=全站）。
            sort: 排序方式（"latest"/"hot"/"pinned"）。
            cursor: 游标（上一页最后一条帖子ID）。
            limit: 每页条数。
            current_user_id: 当前登录用户ID（游客为None）。

        Returns:
            PostListResponse分页响应模型。
        """
        posts = post_repository.list_posts(db, author_id=author_id, sort=sort, cursor=cursor, limit=limit)
        total = post_repository.count_posts(db, author_id=author_id)

        if not posts:
            return PostListResponse(items=[], next_cursor=None, total=total)

        # 批量查作者信息
        author_ids = list({p.author_id for p in posts})
        authors = sync_user_repository.batch_get_by_ids(db, author_ids)

        # 批量查标签
        post_ids = [p.id for p in posts]
        tags_map = post_repository.get_tags_by_post_ids(db, post_ids)

        items = [
            self._assemble_post_list_item(post, authors.get(post.author_id), tags_map.get(post.id, []))
            for post in posts
        ]

        next_cursor = posts[-1].id if len(posts) == limit else None
        return PostListResponse(items=items, next_cursor=next_cursor, total=total)

    # ------------------------------------------------------------------
    # 组装辅助方法
    # ------------------------------------------------------------------

    def _assemble_post_response(
        self,
        db: Session,
        post: Post,
        current_user_id: int | None = None,
    ) -> PostResponse:
        """将ORM Post对象组装为PostResponse（含作者信息、标签、互动状态）。

        Args:
            db: 数据库同步会话。
            post: Post ORM对象。
            current_user_id: 当前登录用户ID。

        Returns:
            PostResponse响应模型。
        """
        from app.schemas.post import PostAuthor

        author = sync_user_repository.get_by_id(db, post.author_id)
        author_info = None
        if author:
            author_info = PostAuthor(id=author.id, nickname=author.nickname, avatar=author.avatar)

        tags = post_repository.get_tags_by_post_id(db, post.id)

        is_liked = False
        is_favorited = False
        if current_user_id is not None:
            is_liked = self._check_is_liked(db, current_user_id, post.id)
            is_favorited = self._check_is_favorited(db, current_user_id, post.id)

        return PostResponse(
            id=post.id,
            author=author_info,
            title=post.title,
            content=post.content,
            cover_url=post.cover_url,
            images=post.images if isinstance(post.images, list) else [],
            tags=tags if tags else (post.tags if isinstance(post.tags, list) else []),
            likes_count=post.likes_count,
            comments_count=post.comments_count,
            views_count=post.views_count,
            is_pinned=bool(post.is_pinned),
            is_hot=bool(post.is_hot),
            is_liked=is_liked,
            is_favorited=is_favorited,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )

    def _assemble_post_list_item(
        self,
        post: Post,
        author,
        tags: list[str],
    ) -> PostListItem:
        """将ORM Post对象组装为PostListItem（列表项，正文截断为摘要）。

        Args:
            post: Post ORM对象。
            author: 作者User ORM对象。
            tags: 标签列表。

        Returns:
            PostListItem响应模型。
        """
        from app.schemas.post import PostAuthor

        author_info = None
        if author:
            author_info = PostAuthor(id=author.id, nickname=author.nickname, avatar=author.avatar)

        content_preview = post.content[:CONTENT_PREVIEW_LENGTH]
        if len(post.content) > CONTENT_PREVIEW_LENGTH:
            content_preview += "..."

        resolved_tags = tags if tags else (post.tags if isinstance(post.tags, list) else [])

        return PostListItem(
            id=post.id,
            author=author_info,
            title=post.title,
            content_preview=content_preview,
            cover_url=post.cover_url,
            images_count=len(post.images) if isinstance(post.images, list) else 0,
            tags=resolved_tags,
            likes_count=post.likes_count,
            comments_count=post.comments_count,
            views_count=post.views_count,
            is_pinned=bool(post.is_pinned),
            is_hot=bool(post.is_hot),
            is_liked=False,
            is_favorited=False,
            created_at=post.created_at,
        )

    def _check_is_liked(self, db: Session, user_id: int, post_id: int) -> bool:
        """检查用户是否点赞了帖子。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            post_id: 帖子ID。

        Returns:
            是否已点赞。
        """
        from app.repositories.like_repository import like_repository

        return like_repository.is_liked(db, post_id, user_id)

    def _check_is_favorited(self, db: Session, user_id: int, post_id: int) -> bool:
        """检查用户是否收藏了帖子。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            post_id: 帖子ID。

        Returns:
            是否已收藏。
        """
        from app.repositories.favorite_repository import favorite_repository

        return favorite_repository.is_favorited(db, post_id, user_id)

    # ------------------------------------------------------------------
    # 缓存辅助
    # ------------------------------------------------------------------

    def _invalidate_detail_cache(self, cache_client: redis.Redis, post_id: int) -> None:
        """失效帖子详情缓存。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
        """
        try:
            cache_client.delete(f"post:detail:{post_id}")
        except Exception:
            logger.exception("失效帖子缓存失败 post_id=%s", post_id)


# 模块级单例
post_service = PostService()