"""帖子收藏数据访问层，封装 post_favorite 表操作（同步，供普通业务使用）。"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.post_favorite import PostFavorite


class FavoriteRepository:
    """帖子收藏数据访问层（同步），封装收藏/取消收藏操作。"""

    def create_favorite(self, db: Session, post_id: int, user_id: int) -> bool:
        """创建收藏记录（唯一索引uk_post_user兜底幂等）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            user_id: 收藏用户ID。

        Returns:
            True=新增收藏。
        """
        favorite = PostFavorite(post_id=post_id, user_id=user_id)
        db.add(favorite)
        return True

    def remove_favorite(self, db: Session, post_id: int, user_id: int) -> bool:
        """删除收藏记录（rowcount判定是否真实删除）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            user_id: 收藏用户ID。

        Returns:
            True=取消成功，False=本来就没收藏（幂等）。
        """
        result = db.execute(
            delete(PostFavorite).where(
                PostFavorite.post_id == post_id,
                PostFavorite.user_id == user_id,
            )
        )
        return bool(result.rowcount)

    def is_favorited(self, db: Session, post_id: int, user_id: int) -> bool:
        """判断用户是否收藏了帖子。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            user_id: 用户ID。

        Returns:
            True=已收藏。
        """
        stmt = select(PostFavorite.id).where(
            PostFavorite.post_id == post_id,
            PostFavorite.user_id == user_id,
        )
        return db.execute(stmt).first() is not None

    def batch_is_favorited(self, db: Session, post_ids: list[int], user_id: int) -> set[int]:
        """批量判断用户是否收藏了多个帖子（单次IN查询，避免N+1）。

        Args:
            db: 数据库同步会话。
            post_ids: 帖子ID列表。
            user_id: 用户ID。

        Returns:
            已收藏的帖子ID集合。
        """
        if not post_ids:
            return set()
        stmt = select(PostFavorite.post_id).where(
            PostFavorite.post_id.in_(post_ids),
            PostFavorite.user_id == user_id,
        )
        return {row[0] for row in db.execute(stmt).all()}

    def list_favorites(
        self,
        db: Session,
        user_id: int,
        *,
        cursor: int | None = None,
        limit: int = 20,
    ) -> list[PostFavorite]:
        """查询用户收藏列表（游标分页，按收藏时间倒序）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            cursor: 游标（上一页最后一条收藏ID）。
            limit: 每页条数。

        Returns:
            收藏记录列表。
        """
        stmt = select(PostFavorite).where(
            PostFavorite.user_id == user_id,
        ).order_by(PostFavorite.id.desc())

        if cursor is not None:
            stmt = stmt.where(PostFavorite.id < cursor)

        stmt = stmt.limit(limit)
        return list(db.execute(stmt).scalars().all())


# 模块级单例
favorite_repository = FavoriteRepository()