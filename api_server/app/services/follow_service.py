"""关注关系服务模块。

读路径: 编排"可见性校验 → ZSET分页 → DB批量详情 → SET互关判断"（缓存命中约2-4ms）。
写路径: 关注/取关采用 Transactional Outbox——业务变更与事件写入同一个MySQL本地事务，
    事务提交即保证事件不丢；独立Relay轮询outbox_event投递RabbitMQ，Consumer异步
    同步Redis缓存（最终一致，秒级）。写接口不等待MQ/Redis，DB事务内完成全部操作。

写路径一致性核心: 事件INSERT必须与业务操作共用同一同步Session（同一事务），
    禁止拆成两个会话（拆开则事务提交与事件落库不再原子，宕机可能丢事件）。
"""

import logging
from datetime import datetime

import redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cache.follow_cache import (
    DIRECTION_FOLLOWERS,
    DIRECTION_FOLLOWING,
    follow_cache,
)
from app.models.user_activity import ACTIVITY_TYPE_FOLLOW
from app.repositories.outbox_repository import sync_outbox_repository
from app.repositories.user_repository import sync_user_repository
from app.schemas.user import (
    FollowItemResponse,
    FollowListResponse,
    UserCardResponse,
    UserPublicProfileResponse,
)
from app.services.user_service import user_service

logger = logging.getLogger(__name__)

# 用户状态常量：0-禁用
USER_STATUS_DISABLED = 0


class SelfFollowError(Exception):
    """关注自己异常（路由层转400）。"""


class TargetUserNotFoundError(Exception):
    """目标用户不存在或已注销（路由层转404）。"""


class TargetUserForbiddenError(Exception):
    """目标用户被禁用（路由层转403）。"""


class FollowService:
    """关注/粉丝列表业务编排层（同步），含读路径与关注/取关写路径。"""

    # ------------------------------------------------------------------
    # 写路径：关注/取关（Transactional Outbox）
    # ------------------------------------------------------------------

    def follow(self, db: Session, cache_client: redis.Redis, follower_id: int, following_id: int) -> None:
        """关注用户：单事务内写关系、计数、动态与Outbox事件，幂等。

        校验顺序: 不能关注自己(400) → 目标注销/不存在(404) → 目标禁用(403)；
        重复关注由唯一索引兜底，捕获IntegrityError后幂等返回（不重复计数、不发事件）。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端（事务提交后失效双方资料缓存）。
            follower_id: 关注者（当前登录用户）ID。
            following_id: 被关注者ID。

        Raises:
            SelfFollowError: 关注自己。
            TargetUserNotFoundError: 目标用户不存在或已注销。
            TargetUserForbiddenError: 目标用户被禁用。
        """
        if follower_id == following_id:
            raise SelfFollowError("不能关注自己")

        now = datetime.now()
        try:
            # 校验与写操作同事务（校验查询会触发autobegin，须在begin()内执行）
            with db.begin():
                # get_by_id过滤status=2（注销），目标不可见即等同不存在
                target = sync_user_repository.get_by_id(db, following_id)
                if target is None:
                    raise TargetUserNotFoundError("用户不存在")
                if target.status == USER_STATUS_DISABLED:
                    raise TargetUserForbiddenError("用户已被禁用")

                # ① 关注关系（唯一索引uk_follower_following兜底幂等）
                sync_user_repository.create_follow(db, follower_id, following_id)
                # ② Outbox事件（同一事务，payload由服务端计算created_at_ms，规避时区换算偏差）
                sync_outbox_repository.insert_event(
                    db,
                    event_type="follow_created",
                    aggregate_type="user_follow",
                    aggregate_id=f"{follower_id}:{following_id}",
                    payload={
                        "follower_id": follower_id,
                        "following_id": following_id,
                        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "created_at_ms": int(now.timestamp() * 1000),
                    },
                )
                # ③④ 双方冗余计数各+1
                sync_user_repository.increment_following_count(db, follower_id)
                sync_user_repository.increment_followers_count(db, following_id)
                # ⑤ 关注动态
                sync_user_repository.create_activity(
                    db, follower_id, ACTIVITY_TYPE_FOLLOW, f"关注了 {target.nickname}", following_id
                )
        except IntegrityError:
            # 重复关注（并发或重试场景撞唯一索引）→ 回滚后幂等返回
            logger.info("重复关注，幂等返回 follower_id=%s following_id=%s", follower_id, following_id)
            return

        # 事务提交后失效双方资料缓存（计数已变更，下次查询回填最新值）
        user_service.invalidate_profile_cache(cache_client, follower_id)
        user_service.invalidate_profile_cache(cache_client, following_id)
        logger.info("关注成功 follower_id=%s following_id=%s", follower_id, following_id)

    def unfollow(self, db: Session, cache_client: redis.Redis, follower_id: int, following_id: int) -> None:
        """取消关注：单事务内删关系、修正计数与写Outbox事件，幂等。

        取关无前置状态校验（DELETE rowcount判定）；路径用户不存在/注销返回404；
        关系本就不存在时直接提交并幂等返回（不产生事件）。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端（事务提交后失效双方资料缓存）。
            follower_id: 关注者（当前登录用户）ID。
            following_id: 被关注者ID。

        Raises:
            TargetUserNotFoundError: 目标用户不存在或已注销。
        """
        now = datetime.now()
        # 校验与写操作同事务（校验查询会触发autobegin，须在begin()内执行）
        with db.begin():
            # 注销用户对外等同不存在；禁用用户仍允许被取关（清理关系）
            target = sync_user_repository.get_by_id(db, following_id)
            if target is None:
                raise TargetUserNotFoundError("用户不存在")

            deleted = sync_user_repository.remove_follow(db, follower_id, following_id)
            if not deleted:
                # 未关注过 → 幂等返回，不发事件、不改计数
                logger.info("取关未关注用户，幂等返回 follower_id=%s following_id=%s", follower_id, following_id)
                return

            # ① Outbox事件（仅真实删除时）
            sync_outbox_repository.insert_event(
                db,
                event_type="follow_deleted",
                aggregate_type="user_follow",
                aggregate_id=f"{follower_id}:{following_id}",
                payload={
                    "follower_id": follower_id,
                    "following_id": following_id,
                    "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_at_ms": int(now.timestamp() * 1000),
                },
            )
            # ② 双方冗余计数各-1（复用CAST+GREATEST(0)防无符号溢出）
            sync_user_repository.decrement_following_count(db, [follower_id])
            sync_user_repository.decrement_followers_count(db, [following_id])

        # 事务提交后失效双方资料缓存（计数已变更）
        user_service.invalidate_profile_cache(cache_client, follower_id)
        user_service.invalidate_profile_cache(cache_client, following_id)
        logger.info("取关成功 follower_id=%s following_id=%s", follower_id, following_id)

    # ------------------------------------------------------------------
    # 读路径：关注/粉丝列表
    # ------------------------------------------------------------------

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
