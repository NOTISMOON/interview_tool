"""认证相关API端点，处理GitHub OAuth登录、双Token签发（HttpOnly Cookie）、刷新与退出。"""

from fastapi import APIRouter, Depends, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db, get_async_redis, get_refresh_token_from_cookie
from app.core.config import settings
from app.schemas.auth import (
    GitHubCallbackRequest,
    RefreshResponse,
    TokenResponse,
)
from app.services.auth_service import auth_service
from app.services.github_oauth_service import github_oauth_service

router = APIRouter(prefix="/auth", tags=["认证"])


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """将双Token写入HttpOnly Cookie（access全路径、refresh仅认证路径）。

    Args:
        response: FastAPI响应对象，用于设置Cookie。
        access_token: 短期JWT访问令牌。
        refresh_token: 长期刷新令牌明文。
    """
    # access_token：所有API路径都携带，30分钟有效
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=settings.COOKIE_ACCESS_PATH,
        domain=settings.COOKIE_DOMAIN,
    )
    # refresh_token：仅在认证端点路径下发送，缩小暴露面
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=settings.COOKIE_REFRESH_PATH,
        domain=settings.COOKIE_DOMAIN,
    )


@router.get("/github/login", summary="获取GitHub OAuth授权URL")
async def github_login() -> dict:
    """返回GitHub OAuth授权页面URL，前端需将用户重定向到该URL。

    Returns:
        包含授权URL的字典。
    """
    url = github_oauth_service.get_authorize_url()
    return {"authorize_url": url}


@router.post("/github/callback", response_model=TokenResponse, summary="GitHub OAuth回调处理")
async def github_callback(
    request: GitHubCallbackRequest,
    response: Response,
    db: AsyncSession = Depends(get_async_db),
    redis: Redis = Depends(get_async_redis),
) -> TokenResponse:
    """处理GitHub OAuth回调：换取用户信息 → 查找/创建本地用户 → 签发双Token并写入HttpOnly Cookie。

    Args:
        request: 包含GitHub回调code参数的请求体。
        response: FastAPI响应对象，用于设置Cookie。
        db: 数据库异步会话。
        redis: 异步Redis客户端。

    Returns:
        TokenResponse: 仅包含用户信息（Token对通过HttpOnly Cookie下发）。

    Raises:
        HTTPException: GitHub认证失败时抛出。
    """
    # OAuth认证并持久化user/user_auth记录
    user_info, user = await github_oauth_service.authenticate(request.code, db)

    # 签发双token：access_token (JWT, 30min) + refresh_token (7天, Redis存SHA256哈希)
    tokens = await auth_service.create_auth_tokens(redis, user.id, user_info.login)

    # 双token写入HttpOnly Cookie，前端JS不可读
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)

    return TokenResponse(user=user_info)


@router.post("/refresh", response_model=RefreshResponse, summary="刷新Token")
async def refresh_token(
    response: Response,
    refresh_token: str = Depends(get_refresh_token_from_cookie),
    redis: Redis = Depends(get_async_redis),
) -> RefreshResponse:
    """从Cookie读取refresh_token，轮转签发新Token对并写入Cookie（旧refresh_token立即失效）。

    Args:
        response: FastAPI响应对象，用于设置Cookie。
        refresh_token: 从Cookie取出的refresh_token明文（依赖注入提供）。
        redis: 异步Redis客户端。

    Returns:
        RefreshResponse: 空响应体（新Token对通过Cookie下发）。

    Raises:
        HTTPException: refresh_token无效或已过期时返回401。
    """
    tokens = await auth_service.refresh_tokens(redis, refresh_token)
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return RefreshResponse()


@router.post("/logout", summary="退出登录")
async def logout(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_async_redis),
) -> dict:
    """删除Redis中的refresh_token并清除客户端Cookie（幂等：会话不存在也返回200）。

    Args:
        request: FastAPI请求对象，用于读取Cookie。
        response: FastAPI响应对象，用于清除Cookie。
        redis: 异步Redis客户端。

    Returns:
        包含退出提示信息的字典。
    """
    # 幂等处理：Cookie存在才吊销，不存在直接视为已退出
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        await auth_service.revoke_refresh_token(redis, refresh_token)

    # 清除客户端Cookie（path/domain必须与设置时一致才能生效）
    response.delete_cookie(
        key="access_token",
        path=settings.COOKIE_ACCESS_PATH,
        domain=settings.COOKIE_DOMAIN,
    )
    response.delete_cookie(
        key="refresh_token",
        path=settings.COOKIE_REFRESH_PATH,
        domain=settings.COOKIE_DOMAIN,
    )
    return {"message": "已退出登录"}
