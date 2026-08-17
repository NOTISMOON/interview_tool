"""用户数据访问层（异步），封装 user / user_auth 表操作，供认证流程使用。"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_auth import UserAuth
from app.schemas.auth import GitHubUserInfo

# 认证方式常量：2-GitHub
PROVIDER_GITHUB = 2


class UserRepository:
    """用户数据访问层（异步），提供OAuth用户查找与创建。"""

    async def get_auth_by_provider(
        self, db: AsyncSession, provider: int, provider_user_id: str
    ) -> UserAuth | None:
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


user_repository = UserRepository()
