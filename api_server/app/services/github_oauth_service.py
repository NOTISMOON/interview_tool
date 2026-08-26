"""GitHub OAuth 服务模块，负责与GitHub API交互完成OAuth授权流程。"""

from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.auth import GitHubUserInfo

# GitHub API 请求超时（秒）：连接5秒，读取10秒
_GITHUB_TIMEOUT = httpx.Timeout(5.0, read=10.0)


class GitHubOAuthService:
    """GitHub OAuth 认证服务，提供授权URL生成、令牌交换和用户信息获取功能。"""

    GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
    GITHUB_USER_API_URL = "https://api.github.com/user"

    def get_authorize_url(self, state: str | None = None) -> str:
        """生成GitHub OAuth授权页面URL。

        Args:
            state: 可选的防CSRF状态参数，回调时会原样返回。

        Returns:
            GitHub授权页面的完整URL。
        """
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
            "scope": "read:user user:email",
        }
        if state:
            params["state"] = state
        # urlencode 必须使用：scope 含空格、redirect_uri 含://等特殊字符，手工拼接会生成非法URL
        return f"{self.GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> str:
        """用授权码换取GitHub访问令牌。

        Args:
            code: GitHub回调返回的授权码。

        Returns:
            GitHub访问令牌（access_token）。

        Raises:
            HTTPException: 令牌交换失败（502，网络异常）或授权码无效（400）时抛出。
        """
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=_GITHUB_TIMEOUT) as client:
                response = await client.post(
                    self.GITHUB_TOKEN_URL,
                    data={
                        "client_id": settings.GITHUB_CLIENT_ID,
                        "client_secret": settings.GITHUB_CLIENT_SECRET,
                        "code": code,
                        "redirect_uri": settings.GITHUB_REDIRECT_URI,
                    },
                    headers={"Accept": "application/json"},
                )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub令牌交换请求超时，请稍后重试。",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="无法连接GitHub服务，请检查网络后重试。",
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub令牌交换失败，请检查授权码是否有效。",
            )

        data = response.json()
        access_token = data.get("access_token")
        if not access_token:
            error_desc = data.get("error_description", "未知错误")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub令牌交换失败: {error_desc}",
            )
        return access_token

    async def get_user_info(self, access_token: str) -> GitHubUserInfo:
        """使用GitHub访问令牌获取用户信息。

        Args:
            access_token: GitHub访问令牌。

        Returns:
            GitHubUserInfo: 包含用户基本信息的模型。

        Raises:
            HTTPException: 网络异常（502）或获取用户信息失败（400）时抛出。
        """
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=_GITHUB_TIMEOUT) as client:
                response = await client.get(
                    self.GITHUB_USER_API_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="获取GitHub用户信息请求超时，请稍后重试。",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="无法连接GitHub服务，请检查网络后重试。",
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="获取GitHub用户信息失败，请检查令牌是否有效。",
            )

        user_data = response.json()
        return GitHubUserInfo(
            id=user_data["id"],
            login=user_data["login"],
            name=user_data.get("name"),
            email=user_data.get("email"),
            avatar_url=user_data.get("avatar_url"),
            html_url=user_data.get("html_url"),
        )

    async def authenticate(self, code: str, db: AsyncSession) -> tuple[GitHubUserInfo, User]:
        """完成完整的GitHub OAuth认证流程：换令牌、拉取用户信息、查找/创建本地用户。

        Args:
            code: GitHub回调返回的授权码。
            db: 数据库异步会话，用于持久化user/user_auth记录。

        Returns:
            包含 (GitHub用户信息, 本地User记录含user_id) 的元组。
        """
        github_token = await self.exchange_code_for_token(code)
        user_info = await self.get_user_info(github_token)
        user = await user_repository.get_or_create_github_user(db, user_info)
        return user_info, user


github_oauth_service = GitHubOAuthService()