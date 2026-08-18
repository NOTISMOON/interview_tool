"""关注关系服务模块，编排"可见性校验 → ZSET分页 → DB批量详情 → SET互关判断"读路径。

读路径（3次网络往返，缓存命中时约2-4ms）:
    1. 可见性校验: 复用user_service.get_public_profile（走资料缓存），
       visibility=2对外不存在；visibility=1非关注者返回restricted受限响应。
    2. ZSET游标分页: 1次Redis往返（ZREVRANGEBYSCORE，多取1条判定has_more）。
    3. DB批量详情: 1次主键IN查询（过滤注销用户）。
    4. SET互关判断: 1次Redis pipeline（2次SMISMEMBER覆盖整页）。

降级策略:
    ZSET仅回源最近REBUILD_LIMIT条，翻页到ZSET尽头且冗余计数表明DB还有更多时，
    自动降级为DB游标查询补页（老数据访问频率低，性能不敏感）。

一致性: 由后续Outbox+MQ在关注/取关时维护ZSET/SET（最终一致）；
    缓存未命中时以DB为准回源，可自愈短期不一致。
"""

import logging
from datetime import datetime

import redis
from sqlalchemy.orm import Session

from app.cache.follow_cache import (
    DIRECTION_FOLLOWERS,
    DIRECTION_FOLLOWING,
    follow_cache,
)
from app.repositories.user_repository import sync_user_repository
from app.schemas.user import (
    FollowItemResponse,
    FollowListResponse,
    UserCardResponse,
    UserPublicProfileResponse,
)
from app.services.user_service import user_service

logger = logging.getLogger(__name__)


class FollowService:
    """关注/粉丝列表业务编排层（同步）。"""

    def list_following(
        self,
        db: Session,
        cache_client: redis.Redis,
        target_user_id: int,
        viewer_id: int | None,
        cursor_ms: int | None,
        size: int,
    ) -> FollowListResponse | None:
        """查询关注列表（target关注了谁），游标分页。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            target_user_id: 列表属主用户ID。
            viewer_id: 当前访问者ID（游客为None）。
            cursor_ms: 上一页最后一条的毫秒时间戳游标，首页为None。
            size: 页大小。

        Returns:
            FollowListResponse；属主不存在/注销/仅自己可见时返回None（路由层转404）。
        """
        return self._list(
            db, cache_client, target_user_id, viewer_id, cursor_ms, size, DIRECTION_FOLLOWING
        )

    def list_followers(
        self,
        db: Session,
        cache_client: redis.Redis,
        target_user_id: int,
        viewer_id: int | None,
        cursor_ms: int | None,
        size: int,
    ) -> FollowListResponse | None:
        """查询粉丝列表（谁关注了target），游标分页。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            target_user_id: 列表属主用户ID。
            viewer_id: 当前访问者ID（游客为None）。
            cursor_ms: 上一页最后一条的毫秒时间戳游标，首页为None。
            size: 页大小。

        Returns:
            FollowListResponse；属主不存在/注销/仅自己可见时返回None（路由层转404）。
        """
        return self._list(
            db, cache_client, target_user_id, viewer_id, cursor_ms, size, DIRECTION_FOLLOWERS
        )

    # ------------------------------------------------------------------
    # 内部编排
    # ------------------------------------------------------------------

    def _list(
        self,
        db: Session,
        cache_client: redis.Redis,
        target_user_id: int,
        viewer_id: int | None,
        cursor_ms: int | None,
        size: int,
        direction: str,
    ) -> FollowListResponse | None:
        """列表查询统一编排：可见性 → ZSET分页（含回源/降级） → 组装。"""
        # 1. 可见性校验（复用资料缓存与可见性规则）
        access = user_service.get_public_profile(db, cache_client, target_user_id, viewer_id)
        if access is None:
            # 不存在/已注销/仅自己可见 → 对外等同于不存在
            return None
        if isinstance(access, UserCardResponse):
            # 属主开启"仅关注者可见"且访问者未关注 → 受限响应（不暴露列表与计数）
            return FollowListResponse(items=[], next_cursor=None, restricted=True)
        profile: UserPublicProfileResponse = access
        total = profile.following_count if direction == DIRECTION_FOLLOWING else profile.followers_count

        # 2. ZSET分页（未回源则回源后重查）
        rows = follow_cache.get_page(cache_client, target_user_id, direction, cursor_ms, size)
        if rows is None:
            if follow_cache.is_empty_marked(cache_client, target_user_id, direction):
                return self._empty_response(profile)
            follow_cache.rebuild(cache_client, db, target_user_id, direction)
            rows = follow_cache.get_page(cache_client, target_user_id, direction, cursor_ms, size) or []

        # 3. ZSET有数据 → 组装本页
        if rows:
            has_more = len(rows) > size
            # ZSET翻到尽头但DB可能还有更老数据（部分回源）→ 继续给游标
            if not has_more and total > follow_cache.zcard(cache_client, target_user_id, direction):
                has_more = True
            page_rows = rows[:size]
            next_cursor = page_rows[-1][1] if page_rows and has_more else None
            items = self._assemble_items(cache_client, db, viewer_id, page_rows)
            return FollowListResponse(
                items=items,
                next_cursor=next_cursor,
                following_count=profile.following_count,
                followers_count=profile.followers_count,
            )

        # 4. ZSET本页无数据 → 判断是否降级DB补页（部分回源的更早数据）
        #    仅翻页场景（cursor非空）且ZSET成员数少于冗余计数时触发
        if cursor_ms is not None and total > follow_cache.zcard(cache_client, target_user_id, direction):
            return self._page_from_db(db, cache_client, target_user_id, viewer_id, cursor_ms, size, direction, profile)

        return self._empty_response(profile)

    def _page_from_db(
        self,
        db: Session,
        cache_client: redis.Redis,
        target_user_id: int,
        viewer_id: int | None,
        cursor_ms: int,
        size: int,
        direction: str,
        profile: UserPublicProfileResponse,
    ) -> FollowListResponse:
        """DB降级补页：ZSET部分回源尽头后的老数据查询（JOIN已过滤注销用户）。"""
        before = datetime.fromtimestamp(cursor_ms / 1000)
        if direction == DIRECTION_FOLLOWING:
            db_rows = sync_user_repository.fetch_following_page_from_db(db, target_user_id, before, size + 1)
        else:
            db_rows = sync_user_repository.fetch_followers_page_from_db(db, target_user_id, before, size + 1)

        has_more = len(db_rows) > size
        db_rows = db_rows[:size]
        ids = [user.id for user, _ in db_rows]
        flags = follow_cache.batch_relation_flags(cache_client, viewer_id, ids)
        items = [
            FollowItemResponse(
                id=user.id,
                nickname=user.nickname,
                avatar=user.avatar,
                bio=user.bio,
                location=user.location,
                followed_at=created_at,
                is_following=flag["is_following"],
                is_mutual=flag["is_mutual"],
            )
            for (user, created_at), flag in zip(db_rows, flags)
        ]
        next_cursor = int(db_rows[-1][1].timestamp() * 1000) if db_rows and has_more else None
        return FollowListResponse(
            items=items,
            next_cursor=next_cursor,
            following_count=profile.following_count,
            followers_count=profile.followers_count,
        )

    def _assemble_items(
        self,
        cache_client: redis.Redis,
        db: Session,
        viewer_id: int | None,
        page_rows: list[tuple[int, int]],
    ) -> list[FollowItemResponse]:
        """组装ZSET路径的列表项：批量详情（过滤注销）+ 批量关系标记。

        注意: next_cursor由调用方基于ZSET原始行计算（非过滤后的items），
        避免注销用户被过滤后游标回退造成死循环。
        """
        ids = [uid for uid, _ in page_rows]
        users = sync_user_repository.batch_get_by_ids(db, ids)
        flags = follow_cache.batch_relation_flags(cache_client, viewer_id, ids)
        items = []
        for (uid, score_ms), flag in zip(page_rows, flags):
            user = users.get(uid)
            if user is None:
                continue  # 已注销用户不展示（本页条数可能少于页大小）
            items.append(
                FollowItemResponse(
                    id=user.id,
                    nickname=user.nickname,
                    avatar=user.avatar,
                    bio=user.bio,
                    location=user.location,
                    followed_at=follow_cache.score_to_datetime(score_ms),
                    is_following=flag["is_following"],
                    is_mutual=flag["is_mutual"],
                )
            )
        return items

    @staticmethod
    def _empty_response(profile: UserPublicProfileResponse) -> FollowListResponse:
        """构造空页响应（列表为空或已翻到尽头）。"""
        return FollowListResponse(
            items=[],
            next_cursor=None,
            following_count=profile.following_count,
            followers_count=profile.followers_count,
        )


follow_service = FollowService()
