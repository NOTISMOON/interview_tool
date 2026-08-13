"""API公共依赖注入模块（接线板）。

职责：将下层模块的能力注入到路由层，不包含任何业务逻辑。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.db.sync_session import get_db  # noqa: F401
from app.db.async_session import get_async_db  # noqa: F401
from app.redis.sync_client import get_redis  # noqa: F401
from app.redis.async_client import get_async_redis  # noqa: F401

security_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """从JWT令牌中解析当前登录用户信息。

    Args:
        credentials: HTTP Bearer令牌认证凭据。

    Returns:
        包含用户信息的字典（sub、login、name、avatar_url等）。

    Raises:
        HTTPException: 令牌无效或过期时返回401。
    """
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌，请重新登录。",
        )
    return payload