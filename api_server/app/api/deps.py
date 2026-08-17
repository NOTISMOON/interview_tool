"""API公共依赖注入模块（接线板）。

职责：将下层模块的能力注入到路由层，不包含任何业务逻辑。
认证方案：HttpOnly Cookie，token不下发给前端JS，无法被XSS窃取。
"""

from fastapi import HTTPException, Request, status

from app.core.security import decode_access_token
from app.db.sync_session import get_db  # noqa: F401
from app.db.async_session import get_async_db  # noqa: F401
from app.redis.sync_client import get_redis  # noqa: F401
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
