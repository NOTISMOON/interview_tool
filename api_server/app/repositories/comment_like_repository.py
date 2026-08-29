"""评论点赞数据访问层，封装评论点赞的增删查操作。"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.comment import Comment
from app.models.comment_like import CommentLike

logger = logging.getLogger(__name__)


class CommentLikeRepository:
    """评论点赞数据访问层。"""

    def create_like(self, db: Session, comment_id: int, user_id: int) -> bool:
        """创建评论点赞记录。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。
            user_id: 点赞用户ID。

        Returns:
            True 表示创建成功，False 表示已存在（幂等）。
        """
        try:
            db.add(CommentLike(comment_id=comment_id, user_id=user_id))
            db.flush()
            return True
        except IntegrityError:
            db.rollback()
            return False

    def remove_like(self, db: Session, comment_id: int, user_id: int) -> bool:
        """删除评论点赞记录。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。
            user_id: 点赞用户ID。

        Returns:
            True 表示删除成功，False 表示不存在。
        """
        affected = (
            db.query(CommentLike)
            .filter_by(comment_id=comment_id, user_id=user_id)
            .delete()
        )
        return affected > 0

    def is_liked(self, db: Session, comment_id: int, user_id: int) -> bool:
        """查询用户是否已点赞评论。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。
            user_id: 用户ID。

        Returns:
            True 表示已点赞。
        """
        return (
            db.query(CommentLike)
            .filter_by(comment_id=comment_id, user_id=user_id)
            .first()
            is not None
        )

    def increment_likes_count(self, db: Session, comment_id: int) -> None:
        """评论点赞数 +1。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。
        """
        db.query(Comment).filter(Comment.id == comment_id).update(
            {Comment.likes_count: Comment.likes_count + 1}
        )

    def decrement_likes_count(self, db: Session, comment_id: int) -> None:
        """评论点赞数 -1。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。
        """
        db.query(Comment).filter(Comment.id == comment_id).update(
            {Comment.likes_count: Comment.likes_count - 1}
        )

    def batch_is_liked(self, db: Session, comment_ids: list[int], user_id: int) -> set[int]:
        """批量查询用户点赞了哪些评论。

        Args:
            db: 数据库同步会话。
            comment_ids: 评论ID列表。
            user_id: 用户ID。

        Returns:
            已点赞的评论ID集合。
        """
        rows = (
            db.query(CommentLike.comment_id)
            .filter(
                CommentLike.comment_id.in_(comment_ids),
                CommentLike.user_id == user_id,
            )
            .all()
        )
        return {r[0] for r in rows}


comment_like_repository = CommentLikeRepository()