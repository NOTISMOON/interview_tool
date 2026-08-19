"""FastAPI 应用入口模块。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.middleware.auth_middleware import AuthMiddleware
from app.services.sse_manager import sse_manager

# 应用日志初始化：uvicorn 只配置自身 logger，root logger 无 handler 时
# app.* 的 INFO 及以下日志会被吞掉（lastResort 仅输出 WARNING+ 到 stderr），
# 必须显式配置才能看到业务埋点日志
setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，在启动和关闭时执行资源初始化与清理。"""
    # 启动时：SSE Manager 在首次 connect 时懒初始化 Pub/Sub
    yield
    # 关闭时：清理 SSE Manager 资源
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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