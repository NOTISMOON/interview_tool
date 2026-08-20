"""评论模块数据访问层，封装 comment 表操作（同步，供普通业务使用）。"""

from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session

from app.models.comment import Comment, COMMENT_STATUS_DELETED, COMMENT_STATUS_NORMAL


class CommentRepository:
    """评论数据访问层（同步），封装评论CRUD与计数维护。"""

    # ------------------------------------------------------------------
    # 基本CRUD
    # ------------------------------------------------------------------

    def create(self, db: Session, *, post_id: int, author_id: int, content: str,
               root_id: int | None = None, reply_user_id: int | None = None) -> Comment:
        """创建评论并返回ORM对象。

        Args:
            db: 数据库同步会话。
            post_id: 所属帖子ID。
            author_id: 评论者用户ID。
            content: 评论内容。
            root_id: 根评论ID（NULL=一级评论）。
            reply_user_id: 被回复者用户ID（NULL=一级评论）。

        Returns:
            创建成功的Comment对象（id已回填）。
        """
        comment = Comment(
            post_id=post_id,
            author_id=author_id,
            content=content,
            root_id=root_id,
            reply_user_id=reply_user_id,
        )
        db.add(comment)
        db.flush()
        return comment

    def get_by_id(self, db: Session, comment_id: int) -> Comment | None:
        """根据ID查询评论（过滤已删除）。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。

        Returns:
            Comment对象，不存在或已删除返回None。
        """
        stmt = select(Comment).where(
            Comment.id == comment_id,
            Comment.status == COMMENT_STATUS_NORMAL,
        )
        return db.execute(stmt).scalar_one_or_none()

    def soft_delete(self, db: Session, comment_id: int) -> bool:
        """软删除评论（status置为0）。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。

        Returns:
            删除成功返回True，评论不存在或已删除返回False。
        """
        result = db.execute(
            update(Comment)
            .where(Comment.id == comment_id, Comment.status == COMMENT_STATUS_NORMAL)
            .values(status=COMMENT_STATUS_DELETED)
        )
        return bool(result.rowcount)

    # ------------------------------------------------------------------
    # 列表查询（一级评论 + 回复分开查）
    # ------------------------------------------------------------------

    def list_root_comments(
        self,
        db: Session,
        post_id: int,
        *,
        cursor: int | None = None,
        limit: int = 20,
        sort: str = "latest",
    ) -> list[Comment]:
        """查询帖子的一级评论列表（root_id IS NULL，游标分页）。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。
            cursor: 游标（上一页最后一条评论ID），为None表示首页。
            limit: 每页条数（默认20，上限50）。
            sort: 排序（"latest"=最新，"hot"=最热）。

        Returns:
            一级评论列表。
        """
        stmt = select(Comment).where(
            Comment.post_id == post_id,
            Comment.root_id.is_(None),
            Comment.status == COMMENT_STATUS_NORMAL,
        )

        if sort == "hot":
            stmt = stmt.order_by(Comment.likes_count.desc(), Comment.id.desc())
        else:
            stmt = stmt.order_by(Comment.id.desc())

        if cursor is not None:
            stmt = stmt.where(Comment.id < cursor)

        stmt = stmt.limit(limit)
        return list(db.execute(stmt).scalars().all())

    def list_replies(
        self,
        db: Session,
        root_id: int,
        *,
        cursor: int | None = None,
        limit: int = 10,
    ) -> list[Comment]:
        """查询某条一级评论的回复列表（root_id=指定值，游标分页）。

        Args:
            db: 数据库同步会话。
            root_id: 一级评论ID。
            cursor: 游标（上一页最后一条回复ID），为None表示首页。
            limit: 每页条数（默认10，上限30）。

        Returns:
            回复列表（按时间正序）。
        """
        stmt = select(Comment).where(
            Comment.root_id == root_id,
            Comment.status == COMMENT_STATUS_NORMAL,
        ).order_by(Comment.id.asc())

        if cursor is not None:
            stmt = stmt.where(Comment.id > cursor)

        stmt = stmt.limit(limit)
        return list(db.execute(stmt).scalars().all())

    def count_root_comments(self, db: Session, post_id: int) -> int:
        """统计帖子的一级评论总数。

        Args:
            db: 数据库同步会话。
            post_id: 帖子ID。

        Returns:
            一级评论总数。
        """
        stmt = select(func.count(Comment.id)).where(
            Comment.post_id == post_id,
            Comment.root_id.is_(None),
            Comment.status == COMMENT_STATUS_NORMAL,
        )
        return db.execute(stmt).scalar_one()

    def count_replies(self, db: Session, root_id: int) -> int:
        """统计某条一级评论的回复总数。

        Args:
            db: 数据库同步会话。
            root_id: 一级评论ID。

        Returns:
            回复总数。
        """
        stmt = select(func.count(Comment.id)).where(
            Comment.root_id == root_id,
            Comment.status == COMMENT_STATUS_NORMAL,
        )
        return db.execute(stmt).scalar_one()

    # ------------------------------------------------------------------
    # 计数维护
    # ------------------------------------------------------------------

    def increment_reply_count(self, db: Session, root_id: int) -> None:
        """将一级评论的回复数加1。

        Args:
            db: 数据库同步会话。
            root_id: 一级评论ID。
        """
        db.execute(
            update(Comment)
            .where(Comment.id == root_id, Comment.status == COMMENT_STATUS_NORMAL)
            .values(reply_count=Comment.reply_count + 1)
        )

    def decrement_reply_count(self, db: Session, root_id: int) -> None:
        """将一级评论的回复数减1（下限0）。

        Args:
            db: 数据库同步会话。
            root_id: 一级评论ID。
        """
        db.execute(
            update(Comment)
            .where(Comment.id == root_id, Comment.status == COMMENT_STATUS_NORMAL)
            .values(reply_count=func.greatest(Comment.reply_count - 1, 0))
        )

    def increment_likes_count(self, db: Session, comment_id: int) -> None:
        """将评论点赞数加1。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。
        """
        db.execute(
            update(Comment)
            .where(Comment.id == comment_id, Comment.status == COMMENT_STATUS_NORMAL)
            .values(likes_count=Comment.likes_count + 1)
        )

    def decrement_likes_count(self, db: Session, comment_id: int) -> None:
        """将评论点赞数减1（下限0）。

        Args:
            db: 数据库同步会话。
            comment_id: 评论ID。
        """
        db.execute(
            update(Comment)
            .where(Comment.id == comment_id, Comment.status == COMMENT_STATUS_NORMAL)
            .values(likes_count=func.greatest(Comment.likes_count - 1, 0))
        )

    def batch_get_by_ids(self, db: Session, comment_ids: list[int]) -> dict[int, Comment]:
        """根据ID批量查询评论（过滤已删除）。

        Args:
            db: 数据库同步会话。
            comment_ids: 评论ID列表。

        Returns:
            {comment_id: Comment}字典。
        """
        if not comment_ids:
            return {}
        stmt = select(Comment).where(
            Comment.id.in_(comment_ids),
            Comment.status == COMMENT_STATUS_NORMAL,
        )
        return {c.id: c for c in db.execute(stmt).scalars().all()}


# 模块级单例
comment_repository = CommentRepository()