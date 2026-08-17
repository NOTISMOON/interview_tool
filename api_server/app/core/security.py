"""安全工具模块，提供JWT令牌的创建与验证、Refresh Token生成与哈希功能。"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings


def create_access_token(data: dict[str, Any], expires_minutes: int | None = None) -> str:
    """创建JWT访问令牌。

    Args:
        data: 要编码到令牌中的数据载荷（如 user_id、login 等）。
        expires_minutes: 令牌过期分钟数，默认使用配置中的 ACCESS_TOKEN_EXPIRE_MINUTES。

    Returns:
        编码后的JWT字符串。
    """
    to_encode = data.copy()
    expire_minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解码并验证JWT访问令牌。

    Args:
        token: JWT令牌字符串。

    Returns:
        解码后的载荷字典，验证失败返回 None。
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        return None


def create_refresh_token() -> str:
    """生成不透明的refresh token（256位随机字符串）。

    Returns:
        URL安全的随机字符串，作为refresh token明文（仅返回给客户端，服务端只存哈希）。
    """
    return secrets.token_urlsafe(settings.REFRESH_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """对token做SHA256哈希，用于Redis存储key。

    Args:
        token: refresh token明文。

    Returns:
        token的SHA256十六进制哈希字符串。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()