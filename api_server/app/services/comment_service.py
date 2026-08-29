"""评论业务逻辑层。

写路径: 创建/删除评论采用 Transactional Outbox——业务变更与事件写入同一个MySQL本地事务，
    事务提交即保证事件不丢；独立Relay轮询outbox_event投递RabbitMQ，Consumer异步
    同步缓存与通知（最终一致，秒级）。写接口不等待MQ/Redis，DB事务内完成全部操作。

读路径: 一级评论与回复分开查询（游标分页），批量组装作者信息。
"""

import logging
from datetime import datetime

import redis
from sqlalchemy.orm import Session

from app.models.comment import Comment
from app.repositories.comment_repository import comment_repository
from app.repositories.outbox_repository import sync_outbox_repository
from app.repositories.post_repository import post_repository
from app.repositories.user_repository import sync_user_repository
from app.schemas.comment import CommentCreate, CommentListResponse, CommentResponse

logger = logging.getLogger(__name__)


class CommentNotFoundError(Exception):
    """评论不存在或已删除（路由层转404）。"""


class PostNotFoundError(Exception):
    """帖子不存在或已删除（路由层转404）。"""


class CommentService:
    """评论业务逻辑层（同步），编排评论的创建、删除与查询。"""

    # ------------------------------------------------------------------
    # 写路径：创建/删除（Transactional Outbox）
    # ------------------------------------------------------------------

    def create_comment(self, db: Session, author_id: int, data: CommentCreate) -> Comment:
        """创建评论：单事务内写评论、计数、Outbox事件。

        Args:
            db: 数据库同步会话。
            author_id: 评论者用户ID。
            data: 评论创建请求数据。

        Returns:
            创建成功的Comment ORM对象。

        Raises:
            PostNotFoundError: 帖子不存在或已删除。
        """
        post = post_repository.get_by_id(db, data.post_id)
        if post is None:
            raise PostNotFoundError("帖子不存在")
        post_author_id = post.author_id

        is_reply = data.root_id is not None

        now = datetime.now()
        # 结束校验查询产生的隐式事务（SQLAlchemy 2.0 autobegin），否则 db.begin() 报错
        db.rollback()
        with db.begin():
            # ① 创建评论
            comment = comment_repository.create(
                db,
                post_id=data.post_id,
                author_id=author_id,
                content=data.content,
                root_id=data.root_id,
                reply_user_id=data.reply_user_id,
            )

            # ② 帖子评论数+1
            post_repository.increment_comments_count(db, data.post_id)

            # ③ 如果是回复，一级评论回复数+1
            if is_reply:
                comment_repository.increment_reply_count(db, data.root_id)

            # ④ Outbox事件：comment.created（供缓存同步、动态等Consumer消费）
            sync_outbox_repository.insert_event(
                db,
                event_type="comment.created",
                aggregate_type="comment",
                aggregate_id=str(comment.id),
                payload={
                    "comment_id": comment.id,
                    "post_id": data.post_id,
                    "root_id": data.root_id,
                    "author_id": author_id,
                    "reply_user_id": data.reply_user_id,
                    "content": data.content[:100],  # 截断避免payload过大
                    "is_reply": is_reply,
                    "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_at_ms": int(now.timestamp() * 1000),
                },
            )

            # ⑤ 通知事件：通知帖子作者（非自己评论自己）
            if post_author_id != author_id:
                sync_outbox_repository.insert_event(
                    db,
                    event_type="notification.created",
                    aggregate_type="message",
                    aggregate_id=str(post_author_id),
                    payload={
                        "recipient_id": post_author_id,
                        "type": 2,  # MESSAGE_TYPE_COMMENT
                        "title": "新评论",
                        "content": f"有人评论了你的帖子",
                        "from_user_id": author_id,
                        "related_id": comment.id,
                        "related_type": 1,  # RELATED_TYPE_POST
                    },
                )

            # ⑥ 如果是回复且被回复者不是帖子作者，额外通知被回复者
            if is_reply and data.reply_user_id is not None and data.reply_user_id != post_author_id:
                sync_outbox_repository.insert_event(
                    db,
                    event_type="notification.created",
                    aggregate_type="message",
                    aggregate_id=str(data.reply_user_id),
                    payload={
                        "recipient_id": data.reply_user_id,
                        "type": 2,  # MESSAGE_TYPE_COMMENT
                        "title": "新回复",
                        "content": f"有人回复了你的评论",
                        "from_user_id": author_id,
                        "related_id": comment.id,
                        "related_type": 1,  # RELATED_TYPE_POST
                    },
                )

        logger.info("评论创建成功 comment_id=%s post_id=%s is_reply=%s", comment.id, data.post_id, is_reply)
        return comment

    def delete_comment(self, db: Session, comment_id: int, user_id: int) -> None:
        """软删除评论：单事务内删评论、计数修正与Outbox事件。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。
            user_id: 请求者用户ID（用于权限校验：仅作者可删）。

        Raises:
            CommentNotFoundError: 评论不存在、已删除或非作者操作。
        """
        comment = comment_repository.get_by_id(db, comment_id)
        if comment is None or comment.author_id != user_id:
            raise CommentNotFoundError("评论不存在")

        # 提前提取属性，rollback会使ORM对象过期
        comment_post_id = comment.post_id
        comment_root_id = comment.root_id
        comment_author_id = comment.author_id
        is_reply = comment_root_id is not None
        now = datetime.now()

        # 结束校验查询产生的隐式事务（SQLAlchemy 2.0 autobegin），否则 db.begin() 报错
        db.rollback()
        with db.begin():
            deleted = comment_repository.soft_delete(db, comment_id)
            if not deleted:
                raise CommentNotFoundError("评论不存在")

            # ① 帖子评论数-1
            post_repository.decrement_comments_count(db, comment_post_id)

            # ② 如果是回复，一级评论回复数-1
            if is_reply:
                comment_repository.decrement_reply_count(db, comment_root_id)

            # ③ Outbox事件：comment.deleted
            sync_outbox_repository.insert_event(
                db,
                event_type="comment.deleted",
                aggregate_type="comment",
                aggregate_id=str(comment_id),
                payload={
                    "comment_id": comment_id,
                    "post_id": comment_post_id,
                    "root_id": comment_root_id,
                    "author_id": comment_author_id,
                    "is_reply": is_reply,
                    "deleted_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "deleted_at_ms": int(now.timestamp() * 1000),
                },
            )

        logger.info("评论删除成功 comment_id=%s post_id=%s", comment_id, comment_post_id)

    # ------------------------------------------------------------------
    # 读路径：评论列表
    # ------------------------------------------------------------------

    def list_comments(
        self,
        db: Session,
        post_id: int,
        *,
        cursor: int | None = None,
        limit: int = 20,
        sort: str = "latest",
        current_user_id: int | None = None,
    ) -> CommentListResponse:
        """查询帖子的一级评论列表（含作者信息）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            cursor: 分页游标。
            limit: 每页条数。
            sort: 排序方式。
            current_user_id: 当前登录用户ID。

        Returns:
            CommentListResponse分页响应模型。
        """
        post = post_repository.get_by_id(db, post_id)
        if post is None:
            raise PostNotFoundError("帖子不存在")

        comments = comment_repository.list_root_comments(db, post_id, cursor=cursor, limit=limit, sort=sort)
        total = comment_repository.count_root_comments(db, post_id)

        if not comments:
            return CommentListResponse(items=[], next_cursor=None, total=total)

        items = self._assemble_comment_responses(db, comments, current_user_id)

        next_cursor = comments[-1].id if len(comments) == limit else None
        return CommentListResponse(items=items, next_cursor=next_cursor, total=total)

    def list_replies(
        self,
        db: Session,
        root_id: int,
        *,
        cursor: int | None = None,
        limit: int = 10,
        current_user_id: int | None = None,
    ) -> CommentListResponse:
        """查询某条一级评论的回复列表（含作者信息，按时间正序）。

        Args:
            db: 数据库同步会话。
            root_id: 一级评论ID。
            cursor: 分页游标。
            limit: 每页条数。
            current_user_id: 当前登录用户ID。

        Returns:
            CommentListResponse分页响应模型。
        """
        replies = comment_repository.list_replies(db, root_id, cursor=cursor, limit=limit)
        total = comment_repository.count_replies(db, root_id)

        if not replies:
            return CommentListResponse(items=[], next_cursor=None, total=total)

        items = self._assemble_comment_responses(db, replies, current_user_id)

        next_cursor = replies[-1].id if len(replies) == limit else None
        return CommentListResponse(items=items, next_cursor=next_cursor, total=total)

    # ------------------------------------------------------------------
    # 组装辅助方法
    # ------------------------------------------------------------------

    def _assemble_comment_responses(
        self,
        db: Session,
        comments: list[Comment],
        current_user_id: int | None = None,
    ) -> list[CommentResponse]:
        """批量组装评论响应（含作者信息、被回复者信息、点赞状态）。

        Args:
            db: 数据库同步会话。
            comments: Comment ORM对象列表。
            current_user_id: 当前登录用户ID。

        Returns:
            CommentResponse列表。
        """
        from app.schemas.comment import CommentAuthor

        # 收集所有涉及的作者ID
        user_ids: set[int] = set()
        for c in comments:
            user_ids.add(c.author_id)
            if c.reply_user_id is not None:
                user_ids.add(c.reply_user_id)

        # 批量查询用户信息
        users = sync_user_repository.batch_get_by_ids(db, list(user_ids))

        # 批量查询点赞状态
        liked_ids: set[int] = set()
        if current_user_id is not None and comments:
            from app.repositories.comment_like_repository import comment_like_repository

            comment_ids = [c.id for c in comments]
            liked_ids = comment_like_repository.batch_is_liked(db, comment_ids, current_user_id)

        items: list[CommentResponse] = []
        for c in comments:
            author = users.get(c.author_id)
            author_info = None
            if author:
                author_info = CommentAuthor(id=author.id, nickname=author.nickname, avatar=author.avatar)

            reply_to = None
            if c.reply_user_id is not None:
                reply_user = users.get(c.reply_user_id)
                if reply_user:
                    reply_to = CommentAuthor(id=reply_user.id, nickname=reply_user.nickname, avatar=reply_user.avatar)

            items.append(
                CommentResponse(
                    id=c.id,
                    post_id=c.post_id,
                    root_id=c.root_id,
                    author=author_info,
                    reply_to=reply_to,
                    content=c.content,
                    likes_count=c.likes_count,
                    reply_count=c.reply_count,
                    is_liked=c.id in liked_ids,
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                )
            )
        return items


# 模块级单例
comment_service = CommentService()