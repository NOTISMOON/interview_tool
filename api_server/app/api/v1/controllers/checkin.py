"""签到模块API端点，基于Redis Bitmap实现每日签到。"""

from datetime import date

from fastapi import APIRouter, Depends
from redis import Redis

from app.api.deps import get_current_user, get_redis
from app.redis.checkin_service import CheckinService

router = APIRouter(prefix="/checkin", tags=["签到"])


@router.get("/status", summary="获取签到状态（今天是否已签、连续天数、总天数）")
def get_checkin_status(
    current_user: dict = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    """查询当前用户签到状态。

    Args:
        current_user: 当前登录用户信息。
        redis: 同步Redis客户端。

    Returns:
        包含 signedIn（今天是否已签）、streak（连续天数）、totalDays（总天数）的字典。
    """
    user_id = int(current_user["sub"])
    service = CheckinService(redis)
    return service.get_status(user_id)


@router.post("", summary="执行签到")
def do_checkin(
    current_user: dict = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    """执行签到，返回更新后的签到状态。

    Args:
        current_user: 当前登录用户信息。
        redis: 同步Redis客户端。

    Returns:
        包含 signedIn、streak、totalDays 的字典（signedIn 始终为 true）。
    """
    user_id = int(current_user["sub"])
    service = CheckinService(redis)
    return service.checkin(user_id)