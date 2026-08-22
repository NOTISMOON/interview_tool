"""API v1 路由聚合模块。"""

from fastapi import APIRouter

from app.api.v1.controllers.auth import router as auth_router
from app.api.v1.controllers.comments import router as comments_router
from app.api.v1.controllers.feed import router as feed_router
from app.api.v1.controllers.interactions import router as interactions_router
from app.api.v1.controllers.messages import router as messages_router
from app.api.v1.controllers.posts import router as posts_router
from app.api.v1.controllers.resumes import router as resumes_router
from app.api.v1.controllers.upload import router as upload_router
from app.api.v1.controllers.users import router as users_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(comments_router)
api_v1_router.include_router(feed_router)
api_v1_router.include_router(interactions_router)
api_v1_router.include_router(messages_router)
api_v1_router.include_router(posts_router)
api_v1_router.include_router(resumes_router)
api_v1_router.include_router(upload_router)
api_v1_router.include_router(users_router)