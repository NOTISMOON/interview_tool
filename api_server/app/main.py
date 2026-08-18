"""FastAPI 应用入口模块。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.middleware.auth_middleware import AuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，在启动和关闭时执行资源初始化与清理。"""
    yield


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
