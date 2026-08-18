"""关注关系缓存模块（ZSET分页 + SET关系判断，同步Redis客户端）。

Redis键设计:
    follow:z:following:{user_id}  ZSET  score=关注时间毫秒时间戳 member=被关注者ID → 关注列表游标分页
    follow:z:followers:{user_id}  ZSET  score=关注时间毫秒时间戳 member=粉丝ID     → 粉丝列表游标分页
    follow:s:following:{user_id}  SET   members=全部被关注者ID                     → O(1)判断"我是否关注TA"
    follow:s:followers:{user_id}  SET   members=全部粉丝ID                         → O(1)判断"TA是否关注我"
    follow:empty:{direction}:{user_id}  STRING  空列表防穿透标记（TTL短）

设计要点:
    - ZSET与SET双存: ZSET管有序分页，SET管批量关系判断（SMISMEMBER仅SET支持），
      冗余一份换极致读性能。
    - ZSET部分回源: 仅加载最近REBUILD_LIMIT条，翻到尽头且DB还有更多时由Service层降级查DB。
    - SET全量回源: 关系判断必须全量才准确（漏报会导致"已关注却显示未关注"）。
    - 回源singleflight: 进程内per-key锁+double-check防缓存击穿；多进程部署需升级为
      Redis分布式锁（见docs/功能模块流程.md边界B-7）。
    - 一致性: 由后续Outbox+MQ在关注/取关时同步维护（最终一致），回源以DB为准可自愈。
"""

import logging
import threading
from datetime import datetime

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.user_repository import sync_user_repository

logger = logging.getLogger(__name__)

# 方向常量：关注列表（我关注的人）/ 粉丝列表（关注我的人）
DIRECTION_FOLLOWING = "following"
DIRECTION_FOLLOWERS = "followers"


class FollowCache:
    """关注关系缓存操作层（同步），不包含业务可见性逻辑。"""

    def _zset_key(self, user_id: int, direction: str) -> str:
        """构建ZSET分页缓存键。

        Args:
            user_id: 列表属主用户ID。
            direction: following或followers。

        Returns:
            Redis键名，如 follow:z:following:123。
        """
        return f"follow:z:{direction}:{user_id}"

    def _set_key(self, user_id: int, direction: str) -> str:
        """构建SET关系判断缓存键。

        Args:
            user_id: 关系属主用户ID。
            direction: following或followers。

        Returns:
            Redis键名，如 follow:s:following:123。
        """
        return f"follow:s:{direction}:{user_id}"

    def _empty_key(self, user_id: int, direction: str) -> str:
        """构建空列表防穿透标记键。

        Args:
            user_id: 列表属主用户ID。
            direction: following或followers。

        Returns:
            Redis键名，如 follow:empty:following:123。
        """
        return f"follow:empty:{direction}:{user_id}"

    # ------------------------------------------------------------------
    # 游标分页（ZSET）
    # ------------------------------------------------------------------

    def get_page(
        self,
        cache_client: redis.Redis,
        user_id: int,
        direction: str,
        cursor_ms: int | None,
        size: int,
    ) -> list[tuple[int, int]] | None:
        """ZSET游标分页查询，多取1条用于判定是否有下一页。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 列表属主用户ID。
            direction: following或followers。
            cursor_ms: 上一页最后一条的毫秒时间戳游标，首页为None。
            size: 页大小。

        Returns:
            [(用户ID, 关注时间毫秒时间戳), ...]按时间倒序（最多size+1条）；
            ZSET不存在（未回源）返回None；ZSET存在但该游标区间无数据返回空列表。
        """
        key = self._zset_key(user_id, direction)
        if not cache_client.exists(key):
            return None
        # 排他上界：严格小于cursor_ms（游标不重复）；首页无上界
        max_score = f"({cursor_ms}" if cursor_ms is not None else "+inf"
        rows = cache_client.zrevrangebyscore(key, max_score, "-inf", start=0, num=size + 1, withscores=True)
        return [(int(member), int(score)) for member, score in rows]

    def zcard(self, cache_client: redis.Redis, user_id: int, direction: str) -> int:
        """统计ZSET成员数（用于判断是否需要降级DB补页）。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 列表属主用户ID。
            direction: following或followers。

        Returns:
            ZSET成员数，键不存在返回0。
        """
        return int(cache_client.zcard(self._zset_key(user_id, direction)))

    # ------------------------------------------------------------------
    # 关系判断（SET批量）
    # ------------------------------------------------------------------

    def batch_relation_flags(
        self, cache_client: redis.Redis, viewer_id: int | None, target_ids: list[int]
    ) -> list[dict[str, bool]]:
        """批量计算访问者与每个目标用户的关注/互关标记（1次pipeline往返）。

        原理: viewer的following SET与followers SET同属访问者，两次SMISMEMBER
        即可覆盖整页20条的关系判断：
            is_following[i] = viewer关注了target[i]
            is_mutual[i]    = viewer关注了target[i] 且 target[i]也关注viewer

        Args:
            cache_client: 同步Redis客户端。
            viewer_id: 当前访问者ID，游客为None（全部返回False）。
            target_ids: 本页目标用户ID列表。

        Returns:
            与target_ids等长的标记字典列表。
        """
        if viewer_id is None or not target_ids:
            return [{"is_following": False, "is_mutual": False} for _ in target_ids]

        pipe = cache_client.pipeline()
        pipe.smismember(self._set_key(viewer_id, DIRECTION_FOLLOWING), [str(i) for i in target_ids])
        pipe.smismember(self._set_key(viewer_id, DIRECTION_FOLLOWERS), [str(i) for i in target_ids])
        i_follow_results, they_follow_results = pipe.execute()
        return [
            {
                "is_following": bool(i_follow_results[i]),
                "is_mutual": bool(i_follow_results[i]) and bool(they_follow_results[i]),
            }
            for i in range(len(target_ids))
        ]

    # ------------------------------------------------------------------
    # 回源重建（ZSET部分 + SET全量）
    # ------------------------------------------------------------------

    def rebuild(
        self,
        cache_client: redis.Redis,
        db: Session,
        user_id: int,
        direction: str,
    ) -> None:
        """从DB回源重建该用户该方向的ZSET与SET（含空列表防穿透标记）。

        singleflight: 进程内per-key互斥锁+double-check，防止并发请求同时回源
        造成缓存击穿。

        Args:
            cache_client: 同步Redis客户端。
            db: 数据库同步会话。
            user_id: 列表属主用户ID。
            direction: following或followers。
        """
        zset_key = self._zset_key(user_id, direction)
        if cache_client.exists(zset_key):
            return  # double-check：已被并发请求重建

        # 进程内单飞锁（多进程部署需换Redis分布式锁，见功能模块流程文档边界B-7）
        lock = self._get_lock(zset_key)
        with lock:
            if cache_client.exists(zset_key):
                return  # double-check

            if direction == DIRECTION_FOLLOWING:
                recent_rows = sync_user_repository.fetch_recent_following(
                    db, user_id, settings.FOLLOW_ZSET_REBUILD_LIMIT
                )
                all_ids = sync_user_repository.fetch_all_following_ids(db, user_id)
                opposite_ids = sync_user_repository.fetch_all_follower_ids(db, user_id)
            else:
                recent_rows = sync_user_repository.fetch_recent_followers(
                    db, user_id, settings.FOLLOW_ZSET_REBUILD_LIMIT
                )
                all_ids = sync_user_repository.fetch_all_follower_ids(db, user_id)
                opposite_ids = sync_user_repository.fetch_all_following_ids(db, user_id)

            pipe = cache_client.pipeline()
            if recent_rows:
                # ZSET部分回源：score=毫秒时间戳（created_at秒级精度，见边界B-7）
                mapping = {str(uid): int(created_at.timestamp() * 1000) for uid, created_at in recent_rows}
                pipe.zadd(zset_key, mapping)
                pipe.expire(zset_key, settings.FOLLOW_CACHE_TTL)
                logger.info(
                    "关注ZSET回源完成: user_id=%s direction=%s count=%d", user_id, direction, len(mapping)
                )
            if all_ids:
                # SET全量回源：保证SMISMEMBER关系判断准确
                set_key = self._set_key(user_id, direction)
                pipe.sadd(set_key, *[str(i) for i in all_ids])
                pipe.expire(set_key, settings.FOLLOW_CACHE_TTL)
            if opposite_ids:
                # 对向SET也全量回源：互关判断需读访问者的两个SET，
                # 若只建当前方向则首次访问时互关必然漏报（B-16实测问题）
                opposite_set_key = self._set_key(
                    user_id, DIRECTION_FOLLOWERS if direction == DIRECTION_FOLLOWING else DIRECTION_FOLLOWING
                )
                pipe.sadd(opposite_set_key, *[str(i) for i in opposite_ids])
                pipe.expire(opposite_set_key, settings.FOLLOW_CACHE_TTL)
            if not all_ids:
                # 空列表防穿透：短期内直接返回空页，避免每次请求都回源DB
                pipe.setex(self._empty_key(user_id, direction), settings.FOLLOW_EMPTY_MARK_TTL, "1")
                logger.info("关注缓存空标记已写入: user_id=%s direction=%s", user_id, direction)
            pipe.execute()

    def is_empty_marked(self, cache_client: redis.Redis, user_id: int, direction: str) -> bool:
        """检查该用户该方向是否存在空列表防穿透标记。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 列表属主用户ID。
            direction: following或followers。

        Returns:
            存在空标记返回True（DB确认为空，直接返回空页）。
        """
        return bool(cache_client.exists(self._empty_key(user_id, direction)))

    # ------------------------------------------------------------------
    # 进程内单飞锁
    # ------------------------------------------------------------------

    _locks: dict[str, threading.Lock] = {}
    _locks_guard = threading.Lock()

    @classmethod
    def _get_lock(cls, key: str) -> threading.Lock:
        """获取指定缓存键的进程内互斥锁（懒创建）。

        Args:
            key: 缓存键名。

        Returns:
            该键专属的threading.Lock实例。
        """
        with cls._locks_guard:
            lock = cls._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                cls._locks[key] = lock
            return lock

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def score_to_datetime(score_ms: int) -> datetime:
        """将ZSET毫秒score还原为datetime（与回源时的时区基准一致）。

        Args:
            score_ms: 毫秒时间戳。

        Returns:
            对应的naive datetime（本地时区，与MySQL DATETIME往返一致）。
        """
        return datetime.fromtimestamp(score_ms / 1000)


follow_cache = FollowCache()
