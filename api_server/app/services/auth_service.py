"""认证服务模块，负责双Token（access + refresh）的签发、刷新与吊销。

Redis键设计:
    refresh_token:{sha256(token)} → JSON({"user_id", "login", "created_at"})，TTL 7天。
    user:deactivated:{user_id} → 注销吊销标记（用户服务写入），refresh时校验拒绝续签。
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_access_token, hash_token

logger = logging.getLogger(__name__)

# Redis中refresh token键前缀
REFRESH_TOKEN_PREFIX = "refresh_token:"
# 已注销用户吊销标记键前缀（由用户服务在注销时写入）
USER_DEACTIVATED_PREFIX = "user:deactivated:"


class TokenPair(NamedTuple):
    """签发的双Token对。"""

    access_token: str
    refresh_token: str
    jti: str = ""


class AuthService:
    """认证服务，封装refresh token在Redis中的存取与轮转逻辑。"""

    @staticmethod
    def _build_key(refresh_token: str) -> str:
        """根据refresh token明文构建Redis存储键（SHA256哈希）。

        Args:
            refresh_token: refresh token明文。

        Returns:
            Redis键名，如 refresh_token:abc123...。
        """
        return REFRESH_TOKEN_PREFIX + hash_token(refresh_token)

    async def create_auth_tokens(
        self, redis: Redis, user_id: int, login: str, publish_kick_event: bool = True
    ) -> TokenPair:
        """签发双token：access_token (JWT) + refresh_token（存Redis）。

        Args:
            redis: 异步Redis客户端。
            user_id: 本地用户唯一标识。
            login: 用户登录名（GitHub登录时为GitHub用户名）。
            publish_kick_event: 是否在旧 jti 存在时推送 session_kicked 事件。
                登录时 True，token 刷新时 False（避免刷新触发重复通知）。

        Returns:
            TokenPair，包含access_token与refresh_token。
        """
        # 短期JWT访问令牌（30分钟），内含 jti 用于服务端会话校验
        access_token = create_access_token({"sub": str(user_id), "login": login})

        # 解码获取 jti
        payload = decode_access_token(access_token)
        jti = payload.get("jti") if payload else ""

        # 单设备登录校验：先检查是否有旧 jti（另一设备已登录），有则推送下线通知
        jti_key = f"auth:active_jti:{user_id}"
        old_jti = await redis.get(jti_key)
        if jti:
            await redis.set(
                jti_key,
                jti,
                ex=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            )
            # 仅在初次登录时推送下线通知，不做 token 刷新（避免循环通知）
            if old_jti is not None and publish_kick_event:
                try:
                    channel = f"{settings.NOTIFY_PUSH_CHANNEL_PREFIX}:{user_id}"
                    receivers = await redis.publish(
                        json.dumps({
                            "kind": "session_kicked",
                            "message": "账号已在其他设备登录",
                            "jti": jti,  # 新设备的 jti，前端用来判断是否自己
                        }),
                    )
                    if receivers == 0:
                        logger.warning(
                            "session_kicked 推送无实例接收 user_id=%s channel=%s old_jti=%s",
                            user_id, channel, old_jti,
                        )
                    else:
                        logger.info(
                            "session_kicked 已推送 user_id=%s receivers=%s",
                            user_id, receivers,
                        )
                except Exception:
                    logger.warning("推送下线通知失败: user_id=%s", user_id)

        # 长期不透明刷新令牌（7天），Redis中只存SHA256哈希
        refresh_token = create_refresh_token()
        value = json.dumps(
            {
                "user_id": str(user_id),
                "login": login,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await redis.set(
            self._build_key(refresh_token),
            value,
            ex=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        return TokenPair(access_token=access_token, refresh_token=refresh_token, jti=jti)

    async def refresh_tokens(self, redis: Redis, refresh_token: str) -> TokenPair:
        """验证refresh token，轮转签发新token对（旧token立即失效）。

        Args:
            redis: 异步Redis客户端。
            refresh_token: 客户端持有的refresh token明文。

        Returns:
            TokenPair，包含全新的access_token与refresh_token。

        Raises:
            HTTPException: refresh token无效或已过期时返回401。
        """
        key = self._build_key(refresh_token)
        raw = await redis.get(key)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="refresh_token 无效或已过期，请重新登录",
            )

        data = json.loads(raw)
        # 校验用户是否已注销：注销账号时写入吊销标记，拒绝续签
        if await redis.exists(f"{USER_DEACTIVATED_PREFIX}{data.get('user_id')}"):
            await redis.delete(key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号已注销",
            )

        # 轮转：删除旧token，使其立即失效（防重放攻击）
        await redis.delete(key)

        logger.info("刷新token: user_id=%s", data.get("user_id"))
        return await self.create_auth_tokens(redis, data["user_id"], data["login"], publish_kick_event=False)

    async def revoke_refresh_token(self, redis: Redis, refresh_token: str) -> None:
        """删除Redis中的refresh token（幂等，不存在也不报错）。

        Args:
            redis: 异步Redis客户端。
            refresh_token: 客户端持有的refresh token明文。
        """
        await redis.delete(self._build_key(refresh_token))


auth_service = AuthService()
