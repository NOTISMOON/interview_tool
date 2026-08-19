"""API v1 路由聚合模块。"""

from fastapi import APIRouter

from app.api.v1.controllers.auth import router as auth_router
from app.api.v1.controllers.messages import router as messages_router
from app.api.v1.controllers.users import router as users_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(messages_router)
api_v1_router.include_router(users_router)