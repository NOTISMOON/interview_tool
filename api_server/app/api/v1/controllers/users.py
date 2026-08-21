"""用户管理API端点，提供个人资料读写、可见性控制、他人公开资料查询、账号注销、关注/取关与关注/粉丝列表。"""

import hashlib
import json

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_redis
from app.core.config import settings
from app.core.security import decode_access_token
from app.schemas.user import (
    FollowListResponse,
    ProfileVisibilityUpdateRequest,
    UserProfileResponse,
    UserUpdateRequest,
)
from app.services.follow_service import (
    SelfFollowError,
    TargetUserForbiddenError,
    TargetUserNotFoundError,
    follow_service,
)
from app.services.user_service import user_service

router = APIRouter(prefix="/users", tags=["用户管理"])


def _etag_response(request: Request, data: BaseModel) -> Response:
    """对个人资料响应实现ETag协商缓存：数据未变返回304，变化返回200+新ETag。

    策略: Cache-Control: no-cache——浏览器每次点击个人主页都会发请求到服务器
    （带If-None-Match），服务端比对ETag：数据未变返回304（无响应体，仅头开销），
    数据已更新返回200+完整新数据并刷新浏览器缓存条目。
    Vary: Cookie 防止同浏览器不同账号间串用缓存（响应内容依赖登录身份）。

    Args:
        request: FastAPI请求对象，用于读取If-None-Match请求头。
        data: 待序列化的Pydantic响应模型。

    Returns:
        304（协商命中）或200（数据有变）的Response，均携带ETag头。
    """
    body = json.dumps(data.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    etag = f'"{hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]}"'
    headers = {
        "Cache-Control": "no-cache",
        "Vary": "Cookie",
        "ETag": etag,
    }
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and etag in [tag.strip() for tag in if_none_match.split(",")]:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


def _get_user_id(payload: dict) -> int:
    """从认证载荷中解析当前用户ID。

    Args:
        payload: get_current_user依赖返回的JWT载荷字典。

    Returns:
        当前用户唯一标识。
    """
    return int(payload["sub"])


def _try_get_viewer_id(request: Request) -> int | None:
    """尝试从Cookie解析访问者身份（可选认证，游客返回None）。

    用于公开资料端点：中间件已放行GET请求，此处不强制登录。

    Args:
        request: FastAPI请求对象，用于读取Cookie。

    Returns:
        访问者用户ID，未登录或令牌无效返回None。
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    return int(payload["sub"]) if payload else None


@router.get("/me", response_model=UserProfileResponse, summary="获取个人信息")
def get_my_profile(
    request: Request,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> Response:
    """获取当前登录用户的完整资料（ETag协商缓存：数据未变返回304）。

    服务端走Cache-Aside（Redis→DB），HTTP层走协商缓存：
    浏览器每次进入个人主页都发请求（Cache-Control: no-cache），
    If-None-Match命中ETag返回304（无响应体），数据变更返回200+新数据。

    Args:
        request: FastAPI请求对象，用于读取If-None-Match协商头。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        304（数据未变）或200+UserProfileResponse（数据有变），均带ETag头。

    Raises:
        HTTPException: 用户不存在或已注销时返回404。
    """
    profile = user_service.get_profile(db, cache_client, _get_user_id(payload))
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _etag_response(request, profile)


@router.put("/me", response_model=UserProfileResponse, summary="更新个人资料")
def update_my_profile(
    request_body: UserUpdateRequest,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> UserProfileResponse:
    """更新当前用户资料（先更新数据库，事务提交后删除缓存）。

    Args:
        request_body: 待更新字段请求体（部分更新）。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        UserProfileResponse: 更新后的用户资料。

    Raises:
        HTTPException: 用户不存在时返回404，更新失败返回500。
    """
    try:
        profile = user_service.update_profile(db, cache_client, _get_user_id(payload), request_body)
    except Exception:
        raise HTTPException(status_code=500, detail="更新资料失败")
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return profile


@router.put("/me/profile-visibility", response_model=UserProfileResponse, summary="更新资料可见性")
def update_my_profile_visibility(
    request_body: ProfileVisibilityUpdateRequest,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> UserProfileResponse:
    """更新当前用户资料可见性（先更新数据库，事务提交后删除缓存）。

    Args:
        request_body: 可见性更新请求体（0-公开 1-仅关注者 2-仅自己）。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        UserProfileResponse: 更新后的用户资料。

    Raises:
        HTTPException: 用户不存在时返回404，更新失败返回500。
    """
    try:
        profile = user_service.update_profile_visibility(db, cache_client, _get_user_id(payload), request_body)
    except Exception:
        raise HTTPException(status_code=500, detail="更新可见性失败")
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return profile


@router.get("/me/following", response_model=FollowListResponse, summary="我的关注列表")
def list_my_following(
    cursor: int | None = Query(None, ge=0, description="游标：上一页最后一条的followed_at毫秒时间戳"),
    page_size: int = Query(20, ge=1, le=100, description="页大小（1-100）"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> FollowListResponse:
    """查询我的关注列表（ZSET游标分页，含互关标记）。

    注意: 本路由必须注册在 /{user_id}/following 之前，
    否则 "me" 会被路径参数捕获导致 int 解析失败。

    Args:
        cursor: 上一页返回的next_cursor，首页不传。
        page_size: 页大小。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        FollowListResponse: 本页列表 + next_cursor（为空表示没有更多）。
    """
    my_id = _get_user_id(payload)
    return follow_service.list_following(db, cache_client, my_id, my_id, cursor, page_size)


@router.get("/me/followers", response_model=FollowListResponse, summary="我的粉丝列表")
def list_my_followers(
    cursor: int | None = Query(None, ge=0, description="游标：上一页最后一条的followed_at毫秒时间戳"),
    page_size: int = Query(20, ge=1, le=100, description="页大小（1-100）"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> FollowListResponse:
    """查询我的粉丝列表（ZSET游标分页，含互关标记）。

    Args:
        cursor: 上一页返回的next_cursor，首页不传。
        page_size: 页大小。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        FollowListResponse: 本页列表 + next_cursor（为空表示没有更多）。
    """
    my_id = _get_user_id(payload)
    return follow_service.list_followers(db, cache_client, my_id, my_id, cursor, page_size)


@router.get("/{user_id}", summary="查看他人公开资料")
def get_user_public_profile(
    request: Request,
    user_id: int = Path(..., ge=1, description="被查看的用户ID"),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> Response:
    """获取指定用户的公开资料（ETag协商缓存：数据未变返回304）。

    可见性规则:
        - 公开(0): 返回完整公开资料。
        - 仅关注者(1): 关注者返回完整公开资料，其他人仅返回昵称/头像卡片。
        - 仅自己(2): 非本人返回404（等同于不存在）。

    响应内容依赖访问者身份（可见性过滤），配合Vary: Cookie按登录态区分缓存。

    Args:
        request: FastAPI请求对象，用于可选解析访问者身份与If-None-Match。
        user_id: 被查看的用户ID。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        304（数据未变）或200+完整公开资料/受限卡片，均带ETag头。

    Raises:
        HTTPException: 用户不存在、已注销或不可见时返回404。
    """
    viewer_id = _try_get_viewer_id(request)
    result = user_service.get_public_profile(db, cache_client, user_id, viewer_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _etag_response(request, result)


@router.get("/{user_id}/following", response_model=FollowListResponse, summary="他人关注列表")
def list_user_following(
    request: Request,
    user_id: int = Path(..., ge=1, description="被查看的用户ID"),
    cursor: int | None = Query(None, ge=0, description="游标：上一页最后一条的followed_at毫秒时间戳"),
    page_size: int = Query(20, ge=1, le=100, description="页大小（1-100）"),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> FollowListResponse:
    """查询指定用户的关注列表（游客可访问，受其资料可见性限制）。

    可见性规则:
        - 公开(0): 返回完整列表。
        - 仅关注者(1): 关注者返回完整列表，其他人返回restricted受限响应（仅计数）。
        - 仅自己(2): 非本人返回404。

    Args:
        request: FastAPI请求对象，用于可选解析访问者身份。
        user_id: 被查看的用户ID。
        cursor: 上一页返回的next_cursor，首页不传。
        page_size: 页大小。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        FollowListResponse: 本页列表 + next_cursor。

    Raises:
        HTTPException: 用户不存在、已注销或不可见时返回404。
    """
    viewer_id = _try_get_viewer_id(request)
    result = follow_service.list_following(db, cache_client, user_id, viewer_id, cursor, page_size)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return result


@router.get("/{user_id}/followers", response_model=FollowListResponse, summary="他人粉丝列表")
def list_user_followers(
    request: Request,
    user_id: int = Path(..., ge=1, description="被查看的用户ID"),
    cursor: int | None = Query(None, ge=0, description="游标：上一页最后一条的followed_at毫秒时间戳"),
    page_size: int = Query(20, ge=1, le=100, description="页大小（1-100）"),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> FollowListResponse:
    """查询指定用户的粉丝列表（游客可访问，受其资料可见性限制）。

    可见性规则:
        - 公开(0): 返回完整列表。
        - 仅关注者(1): 关注者返回完整列表，其他人返回restricted受限响应（仅计数）。
        - 仅自己(2): 非本人返回404。

    Args:
        request: FastAPI请求对象，用于可选解析访问者身份。
        user_id: 被查看的用户ID。
        cursor: 上一页返回的next_cursor，首页不传。
        page_size: 页大小。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        FollowListResponse: 本页列表 + next_cursor。

    Raises:
        HTTPException: 用户不存在、已注销或不可见时返回404。
    """
    viewer_id = _try_get_viewer_id(request)
    result = follow_service.list_followers(db, cache_client, user_id, viewer_id, cursor, page_size)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return result


@router.post(
    "/{user_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="关注用户",
)
def follow_user(
    user_id: int = Path(..., ge=1, description="被关注的用户ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> Response:
    """关注指定用户（Transactional Outbox写路径，重复关注幂等返回204）。

    单事务内完成: 关注关系 + Outbox事件 + 双方计数 + 关注动态；
    事件由Relay异步投递MQ，Consumer同步Redis缓存（最终一致，秒级）。

    Args:
        user_id: 被关注的用户ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        204 No Content（含重复关注的幂等场景）。

    Raises:
        HTTPException: 关注自己返回400；目标不存在/已注销返回404；目标被禁用返回403。
    """
    try:
        follow_service.follow(db, cache_client, _get_user_id(payload), user_id)
    except SelfFollowError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能关注自己")
    except TargetUserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    except TargetUserForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被禁用")
    except Exception:
        raise HTTPException(status_code=500, detail="关注失败")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{user_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="取消关注",
)
def unfollow_user(
    user_id: int = Path(..., ge=1, description="被取关的用户ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> Response:
    """取消关注指定用户（幂等：取关未关注的人同样返回204，不产生事件）。

    Args:
        user_id: 被取关的用户ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        204 No Content。

    Raises:
        HTTPException: 路径用户不存在/已注销返回404。
    """
    try:
        follow_service.unfollow(db, cache_client, _get_user_id(payload), user_id)
    except TargetUserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    except Exception:
        raise HTTPException(status_code=500, detail="取消关注失败")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me", summary="注销账号")
def delete_my_account(
    request: Request,
    response: Response,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> dict:
    """注销当前账号：单事务内软删除用户、清理关注关系并修正计数，随后清除登录态。

    Args:
        request: FastAPI请求对象。
        response: FastAPI响应对象，用于清除Cookie。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        包含注销提示信息的字典。

    Raises:
        HTTPException: 用户不存在或已注销时返回404，注销失败返回500。
    """
    try:
        deleted = user_service.delete_account(db, cache_client, _get_user_id(payload))
    except Exception:
        raise HTTPException(status_code=500, detail="注销失败")
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 清除客户端Cookie（path/domain必须与设置时一致才能生效）
    response.delete_cookie(
        key="access_token",
        path=settings.COOKIE_ACCESS_PATH,
        domain=settings.COOKIE_DOMAIN,
    )
    response.delete_cookie(
        key="refresh_token",
        path=settings.COOKIE_REFRESH_PATH,
        domain=settings.COOKIE_DOMAIN,
    )
    return {"message": "账号已注销"}
