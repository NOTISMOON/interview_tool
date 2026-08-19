"""用户数据访问层，封装 user / user_auth / user_follow 表操作。

包含两个类:
    - UserRepository: 异步实现，供认证（Agent类高并发）流程使用。
    - SyncUserRepository: 同步实现，供用户管理等普通业务（增删改查）使用。
"""

from datetime import datetime

from sqlalchemy import Integer, cast, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_activity import UserActivity
from app.models.user_auth import UserAuth
from app.models.user_follow import UserFollow
from app.schemas.auth import GitHubUserInfo

# 认证方式常量：2-GitHub
PROVIDER_GITHUB = 2


class UserRepository:
    """用户数据访问层（异步），提供OAuth用户查找与创建。"""

    async def get_auth_by_provider(self, db: AsyncSession, provider: int, provider_user_id: str) -> UserAuth | None:
        """根据认证方式与第三方用户标识查询认证记录。

        Args:
            db: 数据库异步会话。
            provider: 认证方式（1-邮箱 2-GitHub 3-QQ 4-微信）。
            provider_user_id: 第三方平台用户唯一标识。

        Returns:
            UserAuth对象，不存在返回None。
        """
        stmt = select(UserAuth).where(
            UserAuth.provider == provider,
            UserAuth.provider_user_id == provider_user_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> User | None:
        """根据用户ID查询用户。

        Args:
            db: 数据库异步会话。
            user_id: 用户唯一标识。

        Returns:
            User对象，不存在返回None。
        """
        return await db.get(User, user_id)

    async def get_users_by_ids(self, db: AsyncSession, user_ids: list[int]) -> list[User]:
        """批量查询用户（IN 单次查询，避免 N+1）。

        Args:
            db: 数据库异步会话。
            user_ids: 用户ID列表（空列表直接返回空结果）。

        Returns:
            User对象列表，仅包含实际存在的用户。
        """
        if not user_ids:
            return []
        stmt = select(User).where(User.id.in_(user_ids))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create_github_user(self, db: AsyncSession, user_info: GitHubUserInfo) -> User:
        """根据GitHub用户信息查找本地用户，不存在则创建（含user_auth绑定记录）。

        Args:
            db: 数据库异步会话。
            user_info: GitHub用户信息。

        Returns:
            本地User对象。

        Raises:
            RuntimeError: 用户创建重试后仍失败时抛出。
        """
        github_id = str(user_info.id)

        # 已绑定 → 直接返回对应用户
        auth = await self.get_auth_by_provider(db, PROVIDER_GITHUB, github_id)
        if auth is not None:
            user = await self.get_user_by_id(db, auth.user_id)
            if user is not None:
                return user

        # 未绑定 → 创建新用户（首次GitHub登录即注册）
        user = await self._create_github_user(db, user_info, github_id, with_email=True)
        if user is not None:
            return user

        # 邮箱唯一索引冲突（该邮箱已被其他账号占用）→ 置空邮箱重试一次
        user = await self._create_github_user(db, user_info, github_id, with_email=False)
        if user is not None:
            return user

        # 并发场景：另一请求已创建该GitHub用户的绑定 → 回查返回
        auth = await self.get_auth_by_provider(db, PROVIDER_GITHUB, github_id)
        if auth is not None:
            user = await self.get_user_by_id(db, auth.user_id)
            if user is not None:
                return user

        raise RuntimeError(f"GitHub用户创建失败: github_id={github_id}")

    async def _create_github_user(
        self, db: AsyncSession, user_info: GitHubUserInfo, github_id: str, with_email: bool
    ) -> User | None:
        """创建user与user_auth记录，冲突时返回None由调用方决定重试策略。

        Args:
            db: 数据库异步会话。
            user_info: GitHub用户信息。
            github_id: GitHub用户唯一标识字符串。
            with_email: 是否写入邮箱（False用于邮箱冲突后置空重试）。

        Returns:
            创建成功的User对象，发生唯一键冲突返回None。
        """
        user = User(
            email=user_info.email if with_email else None,
            nickname=user_info.name or user_info.login,
            avatar=user_info.avatar_url,
        )
        db.add(user)
        await db.flush()  # 提前获取自增主键，供user_auth外键使用

        db.add(
            UserAuth(
                user_id=user.id,
                provider=PROVIDER_GITHUB,
                provider_user_id=github_id,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            # 唯一键冲突：邮箱被占用或并发创建同一GitHub用户
            await db.rollback()
            return None
        await db.refresh(user)
        return user


class SyncUserRepository:
    """用户数据访问层（同步），供用户管理普通业务使用。

    查询统一过滤 status IN (0, 1)，注销用户（status=2）对外不可见。
    """

    # 用户可见状态集合：0-禁用 1-正常（2-注销不可见）
    VISIBLE_STATUS = (0, 1)

    def get_by_id(self, db: Session, user_id: int) -> User | None:
        """根据ID查询用户（注销用户不可见）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。

        Returns:
            User对象，不存在或已注销返回None。
        """
        stmt = select(User).where(User.id == user_id, User.status.in_(self.VISIBLE_STATUS))
        return db.execute(stmt).scalar_one_or_none()

    def update_profile(self, db: Session, user_id: int, update_data: dict) -> None:
        """更新用户个人资料字段（仅更新update_data中提交的字段）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。
            update_data: 待更新字段字典，如 {"nickname": "新昵称"}。
        """
        db.execute(update(User).where(User.id == user_id, User.status.in_(self.VISIBLE_STATUS)).values(**update_data))

    def soft_delete(self, db: Session, user_id: int) -> None:
        """软删除用户（status置为2-注销），不物理删除数据。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。
        """
        db.execute(update(User).where(User.id == user_id, User.status == 1).values(status=2))

    # ------------------------------------------------------------------
    # 关注/取关写路径（与Outbox事件同事务，见follow_service）
    # ------------------------------------------------------------------

    def create_follow(self, db: Session, follower_id: int, following_id: int) -> None:
        """新增一条关注关系（唯一索引uk_follower_following兜底幂等）。

        Args:
            db: 数据库同步会话。
            follower_id: 关注者用户ID。
            following_id: 被关注者用户ID。
        """
        db.add(UserFollow(follower_id=follower_id, following_id=following_id))

    def remove_follow(self, db: Session, follower_id: int, following_id: int) -> bool:
        """删除一条关注关系（rowcount判定是否真实删除）。

        Args:
            db: 数据库同步会话。
            follower_id: 关注者用户ID。
            following_id: 被关注者用户ID。

        Returns:
            删除成功返回True；关系本就不存在返回False（幂等取关）。
        """
        result = db.execute(
            delete(UserFollow).where(
                UserFollow.follower_id == follower_id,
                UserFollow.following_id == following_id,
            )
        )
        return bool(result.rowcount)

    def increment_following_count(self, db: Session, user_id: int) -> None:
        """将用户关注数加1（关注事务内维护冗余计数）。

        Args:
            db: 数据库同步会话。
            user_id: 关注者用户ID。
        """
        db.execute(
            update(User).where(User.id == user_id).values(following_count=User.following_count + 1)
        )

    def increment_followers_count(self, db: Session, user_id: int) -> None:
        """将用户粉丝数加1（关注事务内维护冗余计数）。

        Args:
            db: 数据库同步会话。
            user_id: 被关注者用户ID。
        """
        db.execute(
            update(User).where(User.id == user_id).values(followers_count=User.followers_count + 1)
        )

    def create_activity(self, db: Session, user_id: int, activity_type: int, content: str, related_id: int | None) -> None:
        """写入一条用户动态（如"关注了 xxx"）。

        Args:
            db: 数据库同步会话。
            user_id: 产生动态的用户ID。
            activity_type: 动态类型（1-点赞 2-评论 3-关注 4-发帖）。
            content: 动态描述文本。
            related_id: 关联实体ID（关注动态为被关注者ID）。
        """
        db.add(
            UserActivity(
                user_id=user_id,
                type=activity_type,
                content=content,
                related_id=related_id,
            )
        )

    def get_following_ids(self, db: Session, user_id: int) -> list[int]:
        """查询用户关注的人的ID列表（注销时用于修正对方粉丝计数）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。

        Returns:
            被关注用户ID列表。
        """
        stmt = select(UserFollow.following_id).where(UserFollow.follower_id == user_id)
        return [row[0] for row in db.execute(stmt).all()]

    def get_follower_ids(self, db: Session, user_id: int) -> list[int]:
        """查询用户的粉丝ID列表（注销时用于修正对方关注计数）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。

        Returns:
            粉丝用户ID列表。
        """
        stmt = select(UserFollow.follower_id).where(UserFollow.following_id == user_id)
        return [row[0] for row in db.execute(stmt).all()]

    def delete_follow_relations(self, db: Session, user_id: int) -> None:
        """删除用户的所有关注关系（双向：作为关注者与被关注者）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。
        """
        db.execute(delete(UserFollow).where(or_(UserFollow.follower_id == user_id, UserFollow.following_id == user_id)))

    def decrement_following_count(self, db: Session, user_ids: list[int]) -> None:
        """批量将指定用户的关注数减1（下限0），注销清理时修正冗余计数。

        Args:
            db: 数据库同步会话。
            user_ids: 待修正的用户ID列表。
        """
        if not user_ids:
            return
        db.execute(
            update(User).where(User.id.in_(user_ids))
            # 列为INT UNSIGNED，先CAST成有符号避免0-1无符号溢出（MySQL 1690）
            .values(following_count=func.greatest(cast(User.following_count, Integer) - 1, 0))
        )

    def decrement_followers_count(self, db: Session, user_ids: list[int]) -> None:
        """批量将指定用户的粉丝数减1（下限0），注销清理时修正冗余计数。

        Args:
            db: 数据库同步会话。
            user_ids: 待修正的用户ID列表。
        """
        if not user_ids:
            return
        db.execute(
            update(User).where(User.id.in_(user_ids))
            # 列为INT UNSIGNED，先CAST成有符号避免0-1无符号溢出（MySQL 1690）
            .values(followers_count=func.greatest(cast(User.followers_count, Integer) - 1, 0))
        )

    def is_following(self, db: Session, follower_id: int, following_id: int) -> bool:
        """判断follower_id是否关注了following_id（命中uk_follower_following索引）。

        Args:
            db: 数据库同步会话。
            follower_id: 关注者用户ID。
            following_id: 被关注者用户ID。

        Returns:
            存在关注关系返回True，否则False。
        """
        stmt = select(UserFollow.id).where(
            UserFollow.follower_id == follower_id,
            UserFollow.following_id == following_id,
        )
        return db.execute(stmt).first() is not None

    def batch_get_by_ids(self, db: Session, user_ids: list[int]) -> dict[int, User]:
        """根据ID批量查询用户（主键IN查询，注销用户过滤）。

        用于关注/粉丝列表：ZSET分页拿到ID后批量取详情。

        Args:
            db: 数据库同步会话。
            user_ids: 用户ID列表。

        Returns:
            {user_id: User}字典，不含不存在或已注销的用户。
        """
        if not user_ids:
            return {}
        stmt = select(User).where(User.id.in_(user_ids), User.status.in_(self.VISIBLE_STATUS))
        return {user.id: user for user in db.execute(stmt).scalars().all()}

    def fetch_recent_following(self, db: Session, user_id: int, limit: int) -> list[tuple[int, datetime]]:
        """查询用户最近N条关注记录（ZSET回源用，命中idx_follower_created覆盖索引）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。
            limit: 最多返回条数。

        Returns:
            [(被关注用户ID, 关注时间), ...]按关注时间倒序。
        """
        stmt = (
            select(UserFollow.following_id, UserFollow.created_at)
            .where(UserFollow.follower_id == user_id)
            .order_by(UserFollow.created_at.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in db.execute(stmt).all()]

    def fetch_recent_followers(self, db: Session, user_id: int, limit: int) -> list[tuple[int, datetime]]:
        """查询用户最近N条粉丝记录（ZSET回源用，命中idx_following_created覆盖索引）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。
            limit: 最多返回条数。

        Returns:
            [(粉丝用户ID, 关注时间), ...]按关注时间倒序。
        """
        stmt = (
            select(UserFollow.follower_id, UserFollow.created_at)
            .where(UserFollow.following_id == user_id)
            .order_by(UserFollow.created_at.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in db.execute(stmt).all()]

    def fetch_all_following_ids(self, db: Session, user_id: int) -> list[int]:
        """查询用户全部关注ID（SET回源用，全量保证SMISMEMBER判断准确）。

        注意: 关注数超过10万后此查询变慢，届时需演进为分批SADD（见功能模块流程文档）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。

        Returns:
            被关注用户ID全量列表。
        """
        stmt = select(UserFollow.following_id).where(UserFollow.follower_id == user_id)
        return [row[0] for row in db.execute(stmt).all()]

    def fetch_all_follower_ids(self, db: Session, user_id: int) -> list[int]:
        """查询用户全部粉丝ID（SET回源用，全量保证SMISMEMBER判断准确）。

        Args:
            db: 数据库同步会话。
            user_id: 用户唯一标识。

        Returns:
            粉丝用户ID全量列表。
        """
        stmt = select(UserFollow.follower_id).where(UserFollow.following_id == user_id)
        return [row[0] for row in db.execute(stmt).all()]

    def fetch_following_page_from_db(
        self, db: Session, user_id: int, before: datetime | None, limit: int
    ) -> list[tuple[User, datetime]]:
        """DB降级查询关注列表页（ZSET部分重建尽头后的补页，JOIN过滤注销用户）。

        Args:
            db: 数据库同步会话。
            user_id: 列表属主用户ID。
            before: 游标时间（查询created_at严格早于该值的记录），首页为None。
            limit: 最多返回条数。

        Returns:
            [(User, 关注时间), ...]按关注时间倒序，已过滤注销用户。
        """
        conditions = [UserFollow.follower_id == user_id]
        if before is not None:
            conditions.append(UserFollow.created_at < before)
        stmt = (
            select(User, UserFollow.created_at)
            .join(User, User.id == UserFollow.following_id)
            .where(*conditions, User.status.in_(self.VISIBLE_STATUS))
            .order_by(UserFollow.created_at.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in db.execute(stmt).all()]

    def fetch_followers_page_from_db(
        self, db: Session, user_id: int, before: datetime | None, limit: int
    ) -> list[tuple[User, datetime]]:
        """DB降级查询粉丝列表页（ZSET部分重建尽头后的补页，JOIN过滤注销用户）。

        Args:
            db: 数据库同步会话。
            user_id: 列表属主用户ID。
            before: 游标时间（查询created_at严格早于该值的记录），首页为None。
            limit: 最多返回条数。

        Returns:
            [(User, 关注时间), ...]按关注时间倒序，已过滤注销用户。
        """
        conditions = [UserFollow.following_id == user_id]
        if before is not None:
            conditions.append(UserFollow.created_at < before)
        stmt = (
            select(User, UserFollow.created_at)
            .join(User, User.id == UserFollow.follower_id)
            .where(*conditions, User.status.in_(self.VISIBLE_STATUS))
            .order_by(UserFollow.created_at.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in db.execute(stmt).all()]


sync_user_repository = SyncUserRepository()
user_repository = UserRepository()
