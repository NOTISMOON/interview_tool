"""FastAPI 应用入口模块。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.middleware.auth_middleware import AuthMiddleware
from app.scheduler.tasks import create_scheduler
from app.services.chat_connection_manager import chat_connection_manager
from app.services.sse_manager import sse_manager

# 应用日志初始化：uvicorn 只配置自身 logger，root logger 无 handler 时
# app.* 的 INFO 及以下日志会被吞掉（lastResort 仅输出 WARNING+ 到 stderr），
# 必须显式配置才能看到业务埋点日志
setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)

logger = logging.getLogger(__name__)

# 全局调度器实例
_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，在启动和关闭时执行资源初始化与清理。"""
    global _scheduler
    # 启动时：启动定时任务调度器 + SSE Manager 懒初始化
    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info("定时任务调度器已启动")
    yield
    # 关闭时：停止调度器 + 清理 SSE Manager 资源
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("定时任务调度器已停止")
    await chat_connection_manager.shutdown()
    await sse_manager.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# 中间件注册顺序说明：Starlette栈结构中后注册者位于最外层。
# Auth先注册位于内层、CORS后注册位于最外层，确保Auth返回的302重定向响应也能被CORS补全响应头。
app.add_middleware(AuthMiddleware)

# CORS中间件配置：allow_credentials=True时origins不能用通配符，必须明确白名单
# expose_headers暴露ETag：跨域下前端JS可读取协商缓存头（If-None-Match由浏览器自动携带）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)

# 注册API路由
app.include_router(api_v1_router)


@app.get("/health", tags=["系统"])
def health_check() -> dict:
    """健康检查接口，用于确认服务是否正常运行。

    Returns:
        包含服务状态信息的字典。
    """
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """全局请求校验异常处理器，记录422错误的详细校验信息以便排查。

    Args:
        request: FastAPI请求对象。
        exc: Pydantic校验异常。

    Returns:
        JSONResponse: 包含校验错误详情的422响应。
    """
    logger = logging.getLogger("app.validation")
    body = None
    try:
        body = await request.body()
        body_str = body.decode("utf-8")[:2000]  # 截断长请求体（如base64头像）
    except Exception:
        body_str = "<无法读取请求体>"
    logger.error(
        "请求校验失败 422: path=%s method=%s body=%s errors=%s",
        request.url.path,
        request.method,
        body_str,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )