"""帖子点赞数据访问层，封装 post_like 表操作（同步，供普通业务使用）。"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.post import Post
from app.models.post_like import PostLike


class LikeRepository:
    """帖子点赞数据访问层（同步），封装点赞/取消点赞与计数维护。"""

    def create_like(self, db: Session, post_id: int, user_id: int) -> bool:
        """创建点赞记录（唯一索引uk_post_user兜底幂等）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            user_id: 点赞用户ID。

        Returns:
            True=新增点赞，False=已点赞（幂等）。
        """
        like = PostLike(post_id=post_id, user_id=user_id)
        db.add(like)
        return True

    def remove_like(self, db: Session, post_id: int, user_id: int) -> bool:
        """删除点赞记录（rowcount判定是否真实删除）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            user_id: 点赞用户ID。

        Returns:
            True=取消成功，False=本来就没点赞（幂等）。
        """
        result = db.execute(
            delete(PostLike).where(
                PostLike.post_id == post_id,
                PostLike.user_id == user_id,
            )
        )
        return bool(result.rowcount)

    def is_liked(self, db: Session, post_id: int, user_id: int) -> bool:
        """判断用户是否点赞了帖子。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            user_id: 用户ID。

        Returns:
            True=已点赞。
        """
        stmt = select(PostLike.id).where(
            PostLike.post_id == post_id,
            PostLike.user_id == user_id,
        )
        return db.execute(stmt).first() is not None

    def batch_is_liked(self, db: Session, post_ids: list[int], user_id: int) -> set[int]:
        """批量判断用户是否点赞了多个帖子（单次IN查询，避免N+1）。

        Args:
            db: 数据库同步会话。
            post_ids: 帖子ID列表。
            user_id: 用户ID。

        Returns:
            已点赞的帖子ID集合。
        """
        if not post_ids:
            return set()
        stmt = select(PostLike.post_id).where(
            PostLike.post_id.in_(post_ids),
            PostLike.user_id == user_id,
        )
        return {row[0] for row in db.execute(stmt).all()}

    def increment_likes_count(self, db: Session, post_id: int) -> None:
        """将帖子点赞数加1。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
        """
        db.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(likes_count=Post.likes_count + 1)
        )

    def decrement_likes_count(self, db: Session, post_id: int) -> None:
        """将帖子点赞数减1（下限0）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
        """
        db.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(likes_count=func.greatest(Post.likes_count - 1, 0))
        )


# 模块级单例
like_repository = LikeRepository()