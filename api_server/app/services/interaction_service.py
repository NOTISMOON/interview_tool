"""互动业务逻辑层（点赞/收藏）。

写路径: 点赞/取消点赞、收藏/取消收藏采用 Transactional Outbox——
    业务变更与事件写入同一个MySQL本地事务，事务提交即保证事件不丢；
    独立Relay轮询outbox_event投递RabbitMQ，Consumer异步处理通知。

幂等性: 点赞/取消点赞由DB唯一索引uk_post_user兜底，重复操作捕获IntegrityError后幂等返回。
"""

import logging
from datetime import datetime

import redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cache.interaction_cache import interaction_cache
from app.repositories.favorite_repository import favorite_repository
from app.repositories.like_repository import like_repository
from app.repositories.outbox_repository import sync_outbox_repository
from app.repositories.post_repository import post_repository
from app.repositories.user_repository import sync_user_repository

logger = logging.getLogger(__name__)


class PostNotFoundError(Exception):
    """帖子不存在或已删除（路由层转404）。"""


class InteractionService:
    """互动业务逻辑层（同步），编排点赞/收藏的创建、删除与Outbox事件。"""

    # ------------------------------------------------------------------
    # 点赞
    # ------------------------------------------------------------------

    def toggle_like(self, db: Session, cache_client: redis.Redis, post_id: int, user_id: int) -> dict:
        """切换点赞状态：已点赞→取消，未点赞→点赞。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 当前用户ID。

        Returns:
            {"is_liked": bool, "likes_count": int}。

        Raises:
            PostNotFoundError: 帖子不存在或已删除。
        """
        post = post_repository.get_by_id(db, post_id)
        if post is None:
            raise PostNotFoundError("帖子不存在")

        # 先查Redis SET快速判断当前状态
        cached = interaction_cache.is_liked(cache_client, post_id, user_id)
        if cached is True:
            return self._unlike(db, cache_client, post_id, user_id)
        elif cached is False:
            return self._like(db, cache_client, post_id, user_id, post.author_id)
        else:
            # 缓存miss，查DB
            is_liked = like_repository.is_liked(db, post_id, user_id)
            if is_liked:
                return self._unlike(db, cache_client, post_id, user_id)
            else:
                return self._like(db, cache_client, post_id, user_id, post.author_id)

    def _like(self, db: Session, cache_client: redis.Redis, post_id: int, user_id: int, post_author_id: int) -> dict:
        """点赞操作：单事务内写点赞、计数、Outbox事件。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 点赞用户ID。
            post_author_id: 帖子作者ID。

        Returns:
            {"is_liked": True, "likes_count": int}。
        """
        now = datetime.now()
        try:
            with db.begin():
                like_repository.create_like(db, post_id, user_id)
                like_repository.increment_likes_count(db, post_id)

                # Outbox事件：post.liked
                sync_outbox_repository.insert_event(
                    db,
                    event_type="post.liked",
                    aggregate_type="post_like",
                    aggregate_id=f"{post_id}:{user_id}",
                    payload={
                        "post_id": post_id,
                        "user_id": user_id,
                        "post_author_id": post_author_id,
                        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "created_at_ms": int(now.timestamp() * 1000),
                    },
                )

                # 通知事件（非自己点赞自己）
                if post_author_id != user_id:
                    sync_outbox_repository.insert_event(
                        db,
                        event_type="notification.created",
                        aggregate_type="message",
                        aggregate_id=str(post_author_id),
                        payload={
                            "recipient_id": post_author_id,
                            "type": 1,  # MESSAGE_TYPE_LIKE
                            "title": "新点赞",
                            "content": "有人点赞了你的帖子",
                            "from_user_id": user_id,
                            "related_id": post_id,
                            "related_type": 1,  # RELATED_TYPE_POST
                        },
                    )
        except IntegrityError:
            logger.info("重复点赞，幂等返回 post_id=%s user_id=%s", post_id, user_id)
            db.rollback()

        # 更新Redis缓存（事务提交后）
        interaction_cache.add_like(cache_client, post_id, user_id)

        # 刷新点赞数
        db.refresh(post_repository.get_by_id(db, post_id))
        likes_count = post_repository.get_by_id(db, post_id).likes_count

        logger.info("点赞成功 post_id=%s user_id=%s", post_id, user_id)
        return {"is_liked": True, "likes_count": likes_count}

    def _unlike(self, db: Session, cache_client: redis.Redis, post_id: int, user_id: int) -> dict:
        """取消点赞操作：单事务内删点赞、计数修正、Outbox事件。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 点赞用户ID。

        Returns:
            {"is_liked": False, "likes_count": int}。
        """
        now = datetime.now()
        with db.begin():
            deleted = like_repository.remove_like(db, post_id, user_id)
            if not deleted:
                logger.info("取消点赞未点赞过，幂等返回 post_id=%s user_id=%s", post_id, user_id)
                return {"is_liked": False, "likes_count": post_repository.get_by_id(db, post_id).likes_count}

            like_repository.decrement_likes_count(db, post_id)

            # Outbox事件：post.unliked
            sync_outbox_repository.insert_event(
                db,
                event_type="post.unliked",
                aggregate_type="post_like",
                aggregate_id=f"{post_id}:{user_id}",
                payload={
                    "post_id": post_id,
                    "user_id": user_id,
                    "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_at_ms": int(now.timestamp() * 1000),
                },
            )

        # 更新Redis缓存
        interaction_cache.remove_like(cache_client, post_id, user_id)

        likes_count = post_repository.get_by_id(db, post_id).likes_count

        logger.info("取消点赞成功 post_id=%s user_id=%s", post_id, user_id)
        return {"is_liked": False, "likes_count": likes_count}

    # ------------------------------------------------------------------
    # 收藏
    # ------------------------------------------------------------------

    def toggle_favorite(self, db: Session, cache_client: redis.Redis, post_id: int, user_id: int) -> dict:
        """切换收藏状态：已收藏→取消，未收藏→收藏。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 当前用户ID。

        Returns:
            {"is_favorited": bool}。

        Raises:
            PostNotFoundError: 帖子不存在或已删除。
        """
        post = post_repository.get_by_id(db, post_id)
        if post is None:
            raise PostNotFoundError("帖子不存在")

        cached = interaction_cache.is_favorited(cache_client, post_id, user_id)
        if cached is True:
            return self._unfavorite(db, cache_client, post_id, user_id)
        elif cached is False:
            return self._favorite(db, cache_client, post_id, user_id)
        else:
            is_favorited = favorite_repository.is_favorited(db, post_id, user_id)
            if is_favorited:
                return self._unfavorite(db, cache_client, post_id, user_id)
            else:
                return self._favorite(db, cache_client, post_id, user_id)

    def _favorite(self, db: Session, cache_client: redis.Redis, post_id: int, user_id: int) -> dict:
        """收藏操作：单事务内写收藏、Outbox事件。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 收藏用户ID。

        Returns:
            {"is_favorited": True}。
        """
        now = datetime.now()
        try:
            with db.begin():
                favorite_repository.create_favorite(db, post_id, user_id)

                sync_outbox_repository.insert_event(
                    db,
                    event_type="post.favorited",
                    aggregate_type="post_favorite",
                    aggregate_id=f"{post_id}:{user_id}",
                    payload={
                        "post_id": post_id,
                        "user_id": user_id,
                        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "created_at_ms": int(now.timestamp() * 1000),
                    },
                )
        except IntegrityError:
            logger.info("重复收藏，幂等返回 post_id=%s user_id=%s", post_id, user_id)
            db.rollback()

        interaction_cache.add_favorite(cache_client, post_id, user_id)
        logger.info("收藏成功 post_id=%s user_id=%s", post_id, user_id)
        return {"is_favorited": True}

    def _unfavorite(self, db: Session, cache_client: redis.Redis, post_id: int, user_id: int) -> dict:
        """取消收藏操作：单事务内删收藏、Outbox事件。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 收藏用户ID。

        Returns:
            {"is_favorited": False}。
        """
        now = datetime.now()
        with db.begin():
            deleted = favorite_repository.remove_favorite(db, post_id, user_id)
            if not deleted:
                logger.info("取消收藏未收藏过，幂等返回 post_id=%s user_id=%s", post_id, user_id)
                return {"is_favorited": False}

            sync_outbox_repository.insert_event(
                db,
                event_type="post.unfavorited",
                aggregate_type="post_favorite",
                aggregate_id=f"{post_id}:{user_id}",
                payload={
                    "post_id": post_id,
                    "user_id": user_id,
                    "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_at_ms": int(now.timestamp() * 1000),
                },
            )

        interaction_cache.remove_favorite(cache_client, post_id, user_id)
        logger.info("取消收藏成功 post_id=%s user_id=%s", post_id, user_id)
        return {"is_favorited": False}


# 模块级单例
interaction_service = InteractionService()