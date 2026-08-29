"""API公共依赖注入模块（接线板）。

职责：将下层模块的能力注入到路由层，不包含任何业务逻辑。
认证方案：HttpOnly Cookie，token不下发给前端JS，无法被XSS窃取。
"""

import hashlib
from datetime import timedelta

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.sync_session import get_db  # noqa: F401
from app.db.async_session import get_async_db  # noqa: F401
from app.redis.sync_client import SyncRedisClient, get_redis  # noqa: F401
from app.redis.async_client import get_async_redis  # noqa: F401


def get_current_user(request: Request) -> dict:
    """从HttpOnly Cookie中读取access_token并解析当前登录用户。

    Args:
        request: FastAPI请求对象，用于读取Cookie。

    Returns:
        包含用户信息的字典（sub、login等）。

    Raises:
        HTTPException: 未登录或令牌无效/过期时返回401。
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌已过期",
        )

    # 单设备登录校验：检查 jti 是否与 Redis 中一致
    jti = payload.get("jti")
    user_id = payload.get("sub")
    if jti and user_id:
        redis = SyncRedisClient.get_client()
        active_jti = redis.get(f"auth:active_jti:{user_id}")
        if active_jti is None or active_jti != jti:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号已在其他设备登录，请重新登录",
            )
    elif not jti and user_id:
        # 旧 token 无 jti 时的兼容处理
        redis = SyncRedisClient.get_client()
        active_jti = redis.get(f"auth:active_jti:{user_id}")
        if active_jti is not None:
            # Redis 中有记录 → 已在其他设备登录过，拒绝
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号已在其他设备登录，请重新登录",
            )
        # 首次部署兼容：写入占位 jti
        placeholder = hashlib.sha256(user_id.encode()).hexdigest()[:16]
        redis.setex(
            f"auth:active_jti:{user_id}",
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            placeholder,
        )

    return payload


def get_refresh_token_from_cookie(request: Request) -> str:
    """从HttpOnly Cookie中读取refresh_token，供刷新端点使用。

    Args:
        request: FastAPI请求对象，用于读取Cookie。

    Returns:
        refresh_token明文字符串。

    Raises:
        HTTPException: 未携带refresh_token时返回401，需重新登录。
    """
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="会话已过期，请重新登录",
        )
    return token
