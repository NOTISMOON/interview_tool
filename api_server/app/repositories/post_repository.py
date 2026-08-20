"""帖子模块数据访问层，封装 post / post_tag 表操作（同步，供普通业务使用）。"""

from datetime import datetime

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import Session

from app.models.post import Post, POST_STATUS_DELETED, POST_STATUS_NORMAL
from app.models.post_tag import PostTag


class PostRepository:
    """帖子数据访问层（同步），封装帖子CRUD与标签关联操作。

    查询默认过滤已删除帖子（status=0），仅内部显式传参时允许查已删除数据。
    计数更新使用 func.greatest(..., 0) 防 UNSIGNED 溢出。
    """

    def create(
        self,
        db: Session,
        *,
        author_id: int,
        title: str,
        content: str,
        cover_url: str | None = None,
        images: list[str] | None = None,
    ) -> Post:
        """创建帖子并返回ORM对象。

        Args:
            db: 数据库同步会话。
            author_id: 作者用户ID。
            title: 帖子标题。
            content: 帖子正文。
            cover_url: 封面图COS URL。
            images: 帖子图片COS URL列表。

        Returns:
            创建成功的Post对象（id已回填）。
        """
        post = Post(
            author_id=author_id,
            title=title,
            content=content,
            cover_url=cover_url,
            images=images if images else None,
        )
        db.add(post)
        db.flush()
        return post

    def get_by_id(self, db: Session, post_id: int, *, include_deleted: bool = False) -> Post | None:
        """根据ID查询帖子。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            include_deleted: 是否包含已删除帖子（默认False，仅返回正常帖子）。

        Returns:
            Post对象，不存在返回None。
        """
        stmt = select(Post).where(Post.id == post_id)
        if not include_deleted:
            stmt = stmt.where(Post.status == POST_STATUS_NORMAL)
        return db.execute(stmt).scalar_one_or_none()

    def update(self, db: Session, post_id: int, update_data: dict) -> bool:
        """更新帖子字段（仅更新update_data中提交的字段）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            update_data: 待更新字段字典，如 {"title": "新标题", "tags": [...]}。

        Returns:
            更新成功返回True，帖子不存在或已删除返回False。
        """
        result = db.execute(
            update(Post)
            .where(Post.id == post_id, Post.status == POST_STATUS_NORMAL)
            .values(**update_data)
        )
        return bool(result.rowcount)

    def soft_delete(self, db: Session, post_id: int) -> bool:
        """软删除帖子（status置为0）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。

        Returns:
            删除成功返回True，帖子不存在或已删除返回False。
        """
        result = db.execute(
            update(Post)
            .where(Post.id == post_id, Post.status == POST_STATUS_NORMAL)
            .values(status=POST_STATUS_DELETED)
        )
        return bool(result.rowcount)

    def list_posts(
        self,
        db: Session,
        *,
        author_id: int | None = None,
        sort: str = "latest",
        cursor: int | None = None,
        limit: int = 20,
    ) -> list[Post]:
        """分页查询帖子列表（游标分页，按帖子ID降序）。

        Args:
            db: 数据库同步会话。
            author_id: 作者ID（为None表示不限定作者，查全站）。
            sort: 排序方式（"latest"=最新，"hot"=热门，"pinned"=置顶优先）。
            cursor: 游标（上一页最后一条帖子ID），为None表示首页。
            limit: 每页条数（默认20，上限100）。

        Returns:
            帖子列表（按排序规则排列）。
        """
        stmt = select(Post).where(Post.status == POST_STATUS_NORMAL)

        if author_id is not None:
            stmt = stmt.where(Post.author_id == author_id)

        if sort == "hot":
            stmt = stmt.order_by(Post.is_hot.desc(), Post.likes_count.desc(), Post.id.desc())
        elif sort == "pinned":
            stmt = stmt.order_by(Post.is_pinned.desc(), Post.id.desc())
        else:
            stmt = stmt.order_by(Post.id.desc())

        if cursor is not None:
            stmt = stmt.where(Post.id < cursor)

        stmt = stmt.limit(limit)
        return list(db.execute(stmt).scalars().all())

    def count_posts(self, db: Session, *, author_id: int | None = None) -> int:
        """统计帖子总数。

        Args:
            db: 数据库同步会话。
            author_id: 作者ID（为None统计全站，否则统计该作者）。

        Returns:
            帖子总数。
        """
        stmt = select(func.count(Post.id)).where(Post.status == POST_STATUS_NORMAL)
        if author_id is not None:
            stmt = stmt.where(Post.author_id == author_id)
        return db.execute(stmt).scalar_one()

    def batch_get_by_ids(self, db: Session, post_ids: list[int]) -> dict[int, Post]:
        """根据ID批量查询帖子（主键IN查询，过滤已删除）。

        用于Feed页：ZSET/时间线分页拿到ID后批量取详情。

        Args:
            db: 数据库同步会话。
            post_ids: 帖子ID列表。

        Returns:
            {post_id: Post}字典，不含已删除或不存在的帖子。
        """
        if not post_ids:
            return {}
        stmt = select(Post).where(Post.id.in_(post_ids), Post.status == POST_STATUS_NORMAL)
        return {post.id: post for post in db.execute(stmt).scalars().all()}

    # ------------------------------------------------------------------
    # 计数维护（点赞/评论/浏览数）
    # ------------------------------------------------------------------

    def increment_likes_count(self, db: Session, post_id: int) -> None:
        """将帖子点赞数加1。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
        """
        db.execute(
            update(Post)
            .where(Post.id == post_id, Post.status == POST_STATUS_NORMAL)
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
            .where(Post.id == post_id, Post.status == POST_STATUS_NORMAL)
            .values(likes_count=func.greatest(Post.likes_count - 1, 0))
        )

    def increment_comments_count(self, db: Session, post_id: int) -> None:
        """将帖子评论数加1。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
        """
        db.execute(
            update(Post)
            .where(Post.id == post_id, Post.status == POST_STATUS_NORMAL)
            .values(comments_count=Post.comments_count + 1)
        )

    def decrement_comments_count(self, db: Session, post_id: int) -> None:
        """将帖子评论数减1（下限0）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
        """
        db.execute(
            update(Post)
            .where(Post.id == post_id, Post.status == POST_STATUS_NORMAL)
            .values(comments_count=func.greatest(Post.comments_count - 1, 0))
        )

    def increment_views_count(self, db: Session, post_id: int, delta: int = 1) -> None:
        """将帖子浏览数增加delta。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            delta: 增量（默认1）。
        """
        db.execute(
            update(Post)
            .where(Post.id == post_id, Post.status == POST_STATUS_NORMAL)
            .values(views_count=Post.views_count + delta)
        )

    def increment_posts_count(self, db: Session, user_id: int) -> None:
        """将用户发帖数加1（User表冗余计数）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
        """
        from app.models.user import User

        db.execute(update(User).where(User.id == user_id).values(posts_count=User.posts_count + 1))

    def decrement_posts_count(self, db: Session, user_id: int) -> None:
        """将用户发帖数减1（下限0）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
        """
        from app.models.user import User

        db.execute(
            update(User)
            .where(User.id == user_id)
            .values(posts_count=func.greatest(User.posts_count - 1, 0))
        )

    # ------------------------------------------------------------------
    # 标签关联
    # ------------------------------------------------------------------

    def create_tags(self, db: Session, post_id: int, tags: list[str]) -> None:
        """批量创建帖子标签关联（唯一索引uk_post_tag兜底幂等）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            tags: 标签名列表（已去重）。
        """
        for tag in tags:
            db.add(PostTag(post_id=post_id, tag=tag))

    def delete_tags_by_post_id(self, db: Session, post_id: int) -> None:
        """删除帖子的所有标签关联。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
        """
        db.execute(delete(PostTag).where(PostTag.post_id == post_id))

    def get_tags_by_post_id(self, db: Session, post_id: int) -> list[str]:
        """查询帖子的标签列表。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。

        Returns:
            标签名列表。
        """
        stmt = select(PostTag.tag).where(PostTag.post_id == post_id)
        return [row[0] for row in db.execute(stmt).all()]

    def get_tags_by_post_ids(self, db: Session, post_ids: list[int]) -> dict[int, list[str]]:
        """批量查询帖子标签（单次IN查询，避免N+1）。

        Args:
            db: 数据库同步会话。
            post_ids: 帖子ID列表。

        Returns:
            {post_id: [tag1, tag2, ...]} 字典。
        """
        if not post_ids:
            return {}
        stmt = select(PostTag.post_id, PostTag.tag).where(PostTag.post_id.in_(post_ids))
        result: dict[int, list[str]] = {}
        for row in db.execute(stmt).all():
            result.setdefault(row[0], []).append(row[1])
        return result

    def list_following_posts(
        self,
        db: Session,
        following_ids: list[int],
        *,
        cursor: int | None = None,
        limit: int = 200,
    ) -> list[Post]:
        """查询关注者最新帖子（Feed Pull补偿查询）。

        Args:
            db: 数据库同步会话。
            following_ids: 关注的用户ID列表。
            cursor: 游标（上一页最后一条帖子ID）。
            limit: 每页条数。

        Returns:
            帖子列表（按创建时间倒序）。
        """
        if not following_ids:
            return []
        stmt = select(Post).where(
            Post.author_id.in_(following_ids),
            Post.status == POST_STATUS_NORMAL,
        ).order_by(Post.id.desc())
        if cursor is not None:
            stmt = stmt.where(Post.id < cursor)
        stmt = stmt.limit(limit)
        return list(db.execute(stmt).scalars().all())


# 模块级单例
post_repository = PostRepository()