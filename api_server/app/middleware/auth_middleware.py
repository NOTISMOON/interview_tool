"""认证中间件模块，对需要鉴权的接口进行HttpOnly Cookie双Token校验。

策略：
    1. 白名单路径（登录入口、回调、刷新、退出、健康检查、API文档）直接放行。
    2. access_token有效（JWT未过期且签名正确）→ 放行。
    3. access_token失效但refresh_token有效（Redis中存在）→ 自动续签双Token，
       将新Token写回下游响应Cookie后放行。
    4. 长期Token（refresh_token）失效或缺失 → 返回401 JSON响应，
       由前端axios响应拦截器识别401后调用 /auth/refresh 续签，
       续签失败再由前端跳转到登录页（SPA路由跳转，避免跨域302被浏览器
       自动跟随到无CORS头的HTML页面导致请求失败）。
"""

import hashlib
import logging
from datetime import timedelta

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.security import decode_access_token
from app.redis.async_client import AsyncRedisClient
from app.services.auth_service import auth_service

logger = logging.getLogger(__name__)

# 白名单：无需鉴权的路径（精确匹配）。包含认证入口、健康检查、OpenAPI文档
WHITELIST_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/health",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/api/v1/auth/github/login",
        "/api/v1/auth/github/callback",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/dev-login",
    }
)

# 游客可读路径前缀（仅GET放行）：公开资源类接口，写操作仍强制登录。
# /api/v1/users/{user_id} 查看他人公开资料；/users/me 由端点内依赖兜底返回401。
# /api/v1/posts/ 帖子列表/详情/评论列表（游客可浏览）；/posts/favorites 由端点内依赖兜底401。
# /api/v1/comments/{id}/replies 回复列表（游客可浏览）；DELETE /comments/{id} 为写操作不放行。
WHITELIST_GET_PREFIXES: tuple[str, ...] = (
    "/api/v1/users/",
    "/api/v1/posts/",
    "/api/v1/comments/",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """基于HttpOnly Cookie双Token的认证中间件。"""

    def __init__(self, app: ASGIApp) -> None:
        """初始化认证中间件。

        Args:
            app: ASGI应用实例。
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        """对每个请求执行鉴权：白名单放行，否则校验双Token，长期失效返回401。

        Args:
            request: FastAPI请求对象，用于读取Cookie与路径。
            call_next: 下一个中间件或路由处理函数。

        Returns:
            Response对象：鉴权通过则放行；长期Token失效时返回401 JSON响应，
            由前端axios拦截器统一处理续签与登录跳转。
        """
        # OPTIONS预检请求直接放行，交由CORS中间件处理
        if request.method == "OPTIONS":
            return await call_next(request)

        # 白名单路径放行
        if request.url.path in WHITELIST_PATHS:
            return await call_next(request)

        # 游客可读资源：GET请求且路径命中前缀白名单时放行（未登录也可读）
        if request.method == "GET" and request.url.path.startswith(WHITELIST_GET_PREFIXES):
            return await call_next(request)

        # 读取Cookie中的access_token与refresh_token
        access_token = request.cookies.get("access_token")
        refresh_token = request.cookies.get("refresh_token")

        # 1. access_token有效 → 校验 jti 后放行
        if access_token:
            payload = decode_access_token(access_token)
            if payload is not None:
                # 单设备登录校验：检查 jti 是否与 Redis 中一致
                if not await self._verify_jti(payload):
                    logger.info(
                        "jti不匹配，账号已在其他设备登录: path=%s",
                        request.url.path,
                    )
                    return self._build_unauthorized_response()
                return await call_next(request)

        # 2. access_token失效，尝试用refresh_token续签
        if refresh_token:
            try:
                redis = await AsyncRedisClient.get_client()
                tokens = await auth_service.refresh_tokens(redis, refresh_token)
            except Exception:
                # refresh_token无效或已过期（长期Token失效）→ 返回401，
                # 前端拦截器会调 /auth/refresh（白名单），失败再由前端跳转 /login
                logger.info(
                    "refresh_token无效或已过期，返回401: path=%s",
                    request.url.path,
                )
                return self._build_unauthorized_response()

            # 续签成功，将新access_token注入请求头，使下游控制器能正确解析当前用户
            # 避免下游 get_current_user 仍读取旧Cookie导致401
            self._inject_access_token(request, tokens.access_token)

            # 放行下游并将新双Token写回响应Cookie
            response = await call_next(request)
            self._set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
            return response

        # 3. 无任何有效Token → 返回401 JSON响应，前端axios拦截器按既有逻辑跳转
        logger.info(
            "未携带有效Token，返回401: path=%s",
            request.url.path,
        )
        return self._build_unauthorized_response()

    @staticmethod
    async def _verify_jti(payload: dict) -> bool:
        """校验 JWT 中的 jti 是否与 Redis 中存储的一致（单设备登录校验）。

        Args:
            payload: 解码后的 JWT payload。

        Returns:
            True 表示 jti 匹配或无需校验（无 jti 字段），False 表示账号已在其他设备登录。
        """
        jti = payload.get("jti")
        user_id = payload.get("sub")
        if not user_id:
            return True  # 无 user_id 无法校验，放行
        try:
            redis = await AsyncRedisClient.get_client()
            active_jti = await redis.get(f"auth:active_jti:{user_id}")
            # 无 jti：Redis 中有记录 → 账号已在其他设备登录过，旧 token 失效
            #          Redis 中无记录 → 旧 token 首次出现，兼容放行并写入当前 jti
            if not jti:
                if active_jti is not None:
                    return False
                # 首次部署兼容：将当前 token 的 hash 写入 Redis 作为 jti 占位
                # 下次登录时会被真实 jti 覆盖
                placeholder = hashlib.sha256(payload.get("sub", "").encode()).hexdigest()[:16]
                await redis.set(
                    f"auth:active_jti:{user_id}",
                    placeholder,
                    ex=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
                )
                return True
            # 有 jti：必须与 Redis 一致
            if active_jti is None or active_jti != jti:
                return False
        except Exception:
            logger.exception("jti校验时Redis异常，放行以避免误杀")
        return True

    @staticmethod
    def _build_unauthorized_response() -> JSONResponse:
        """构建401未授权JSON响应，供前端axios响应拦截器统一处理。

        Returns:
            JSONResponse对象，状态码401，body包含错误detail。
        """
        return JSONResponse(
            status_code=401,
            content={"detail": "未登录或会话已过期，请重新登录"},
        )

    @staticmethod
    def _inject_access_token(request: Request, access_token: str) -> None:
        """将续签后的access_token注入请求的Cookie头，使下游控制器能正确解析当前用户。

        修改request.scope中的headers，替换旧的access_token cookie值，
        避免下游 get_current_user 仍读取旧Cookie导致401。

        Args:
            request: FastAPI请求对象。
            access_token: 新的JWT访问令牌。
        """
        raw_headers = request.scope.get("headers", [])
        new_headers: list[tuple[bytes, bytes]] = []
        for key, value in raw_headers:
            if key.lower() == b"cookie":
                # 替换或追加 access_token 到现有Cookie头
                new_cookie = AuthMiddleware._replace_cookie_value(value.decode("utf-8"), "access_token", access_token)
                new_headers.append((key, new_cookie.encode("utf-8")))
            else:
                new_headers.append((key, value))
        request.scope["headers"] = new_headers

    @staticmethod
    def _replace_cookie_value(cookie_header: str, target_key: str, new_value: str) -> str:
        """替换Cookie头中指定键的值，若不存在则追加。

        Args:
            cookie_header: 原始Cookie头字符串。
            target_key: 要替换的Cookie键名。
            new_value: 新的Cookie值。

        Returns:
            修改后的Cookie头字符串。
        """
        # 兼容 "key=val; key2=val2" 与 "key=val;key2=val2" 两种格式
        parts = [p.strip() for p in cookie_header.split(";")]
        found = False
        new_parts: list[str] = []
        for part in parts:
            if not part or "=" not in part:
                if part:
                    new_parts.append(part)
                continue
            key = part.split("=", 1)[0].strip()
            if key == target_key:
                new_parts.append(f"{target_key}={new_value}")
                found = True
            else:
                new_parts.append(part)
        if not found:
            new_parts.append(f"{target_key}={new_value}")
        return "; ".join(new_parts)

    @staticmethod
    def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
        """将续签后的双Token写入响应Cookie（覆盖旧Token）。

        Args:
            response: FastAPI响应对象。
            access_token: 新的JWT访问令牌。
            refresh_token: 新的刷新令牌明文。
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