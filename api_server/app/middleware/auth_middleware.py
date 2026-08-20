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

import logging

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

        # 1. access_token有效 → 直接放行
        if access_token and decode_access_token(access_token) is not None:
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

            # 续签成功，放行下游并将新双Token写回响应Cookie
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
