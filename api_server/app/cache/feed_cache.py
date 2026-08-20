"""用户Feed缓存模块（Redis ZSET，Push-Pull混合模型，同步Redis客户端）。

Redis键设计:
    feed:user:{user_id}      ZSET   用户Feed收件箱（score=发布时间戳ms，member=post_id）
    feed:inbox:user:{user_id} ZSET  仅关注用户可见的帖子收件箱（Push阶段写入）

Push-Pull流程:
    Push: 发帖时，从关注SET取出粉丝列表，批量ZADD帖子ID到粉丝的 feed:inbox:user:{follower_id}
    Pull: 用户读取Feed时，先读取 feed:user:{user_id}（有热度、编辑推荐等），再合并关注者帖子
          - 合并后排序取Top N，写入 feed:user:{user_id} 带TTL

设计要点:
    - ZSET score = 发帖时间戳（毫秒），天然按时间倒序
    - 容量限制：保留最近1000条，超出ZREMRANGEBYRANK清理
    - TTL=7天，过期自动清理
    - 大V特殊处理：粉丝超过1万时，不Push到粉丝Feed，改为Pull模式（粉丝自己来拉取）
"""

import logging
import random
from typing import Any

import redis

logger = logging.getLogger(__name__)

# 缓存TTL常量（秒）
FEED_CACHE_TTL = 7 * 86400  # 7天
TTL_JITTER = 3600  # TTL随机偏移1小时

# 缓存键前缀
KEY_FEED_USER = "feed:user:{user_id}"
KEY_FEED_INBOX = "feed:inbox:user:{user_id}"

# Feed容量限制
FEED_MAX_SIZE = 1000  # 最多保留1000条
BIG_V_FOLLOWER_THRESHOLD = 10000  # 大V阈值（粉丝超过1万不Push）


class FeedCache:
    """用户Feed缓存操作层（同步），封装ZSET Feed的读写、Push、容量管理。"""

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def push_post(self, cache_client: redis.Redis, follower_id: int, post_id: int, created_at_ms: int) -> None:
        """Push帖子到粉丝的Feed收件箱。

        Args:
            cache_client: 同步Redis客户端。
            follower_id: 粉丝用户ID。
            post_id: 帖子ID。
            created_at_ms: 发帖时间戳（毫秒）。
        """
        key = KEY_FEED_INBOX.format(user_id=follower_id)
        try:
            pipe = cache_client.pipeline()
            pipe.zadd(key, {str(post_id): created_at_ms})
            pipe.zremrangebyrank(key, 0, -(FEED_MAX_SIZE + 1))  # 保留最新1000条
            pipe.expire(key, FEED_CACHE_TTL + random.randint(0, TTL_JITTER))
            pipe.execute()
        except Exception:
            logger.exception("Feed Push失败 follower_id=%s post_id=%s", follower_id, post_id)

    def batch_push_post(
        self,
        cache_client: redis.Redis,
        follower_ids: list[int],
        post_id: int,
        created_at_ms: int,
    ) -> None:
        """批量Push帖子到多个粉丝的Feed收件箱（Pipeline批量写）。

        Args:
            cache_client: 同步Redis客户端。
            follower_ids: 粉丝ID列表。
            post_id: 帖子ID。
            created_at_ms: 发帖时间戳（毫秒）。
        """
        if not follower_ids:
            return
        try:
            pipe = cache_client.pipeline()
            for fid in follower_ids:
                key = KEY_FEED_INBOX.format(user_id=fid)
                pipe.zadd(key, {str(post_id): created_at_ms})
                pipe.zremrangebyrank(key, 0, -(FEED_MAX_SIZE + 1))
                pipe.expire(key, FEED_CACHE_TTL + random.randint(0, TTL_JITTER))
            pipe.execute()
        except Exception:
            logger.exception("Feed批量Push失败 post_id=%s follower_count=%s", post_id, len(follower_ids))

    def merge_feed(
        self,
        cache_client: redis.Redis,
        user_id: int,
        post_ids_with_scores: list[tuple[int, int]],
    ) -> None:
        """合并写入用户Feed（Pull阶段：合并关注者帖子+推荐帖子）。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 用户ID。
            post_ids_with_scores: [(post_id, score_ms), ...] 帖子ID与时间戳对。
        """
        mapping = {str(pid): score for pid, score in post_ids_with_scores}
        key = KEY_FEED_USER.format(user_id=user_id)
        try:
            pipe = cache_client.pipeline()
            if mapping:
                pipe.zadd(key, mapping)
            pipe.zremrangebyrank(key, 0, -(FEED_MAX_SIZE + 1))
            pipe.expire(key, FEED_CACHE_TTL + random.randint(0, TTL_JITTER))
            pipe.execute()
        except Exception:
            logger.exception("Feed合并写入失败 user_id=%s", user_id)

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get_feed(
        self,
        cache_client: redis.Redis,
        user_id: int,
        cursor: int | None = None,
        limit: int = 20,
    ) -> tuple[list[int], int | None]:
        """从缓存读取用户Feed（按score倒序，score游标分页）。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 用户ID。
            cursor: 游标（上一页最后一条的score，即时间戳ms）。
            limit: 每页条数。

        Returns:
            (帖子ID列表, 下一页游标score)，游标为None表示没有更多。
        """
        key = KEY_FEED_USER.format(user_id=user_id)
        if not cache_client.exists(key):
            return [], None

        max_score = cursor - 1 if cursor else "+inf"
        members = cache_client.zrevrangebyscore(key, max_score, "-inf", start=0, num=limit, withscores=True)
        post_ids = [int(m) for m, _ in members]
        next_cursor = int(members[-1][1]) if len(members) == limit else None
        return post_ids, next_cursor

    def get_inbox(
        self,
        cache_client: redis.Redis,
        user_id: int,
        cursor: int | None = None,
        limit: int = 20,
    ) -> list[tuple[int, int]]:
        """读取用户收件箱（关注者帖子原始列表）。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 用户ID。
            cursor: 游标（上一页最后一条的score）。
            limit: 每页条数。

        Returns:
            [(post_id, score), ...] 帖子ID与时间戳对。
        """
        key = KEY_FEED_INBOX.format(user_id=user_id)
        if not cache_client.exists(key):
            return []

        max_score = cursor - 1 if cursor else "+inf"
        items = cache_client.zrevrangebyscore(key, max_score, "-inf", start=0, num=limit, withscores=True)
        return [(int(m), int(s)) for m, s in items]

    def is_feed_cached(self, cache_client: redis.Redis, user_id: int) -> bool:
        """检查用户Feed是否已缓存。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 用户ID。

        Returns:
            True=已缓存。
        """
        return bool(cache_client.exists(KEY_FEED_USER.format(user_id=user_id)))

    def invalidate_feed(self, cache_client: redis.Redis, user_id: int) -> None:
        """失效用户Feed缓存（关注/取关时调用）。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 用户ID。
        """
        try:
            cache_client.delete(KEY_FEED_USER.format(user_id=user_id))
        except Exception:
            logger.exception("Feed缓存失效失败 user_id=%s", user_id)

    def clear_inbox(self, cache_client: redis.Redis, user_id: int) -> None:
        """清空用户收件箱（内容已合并进Feed缓存后调用）。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 用户ID。
        """
        try:
            cache_client.delete(KEY_FEED_INBOX.format(user_id=user_id))
        except Exception:
            logger.exception("清空Feed收件箱失败 user_id=%s", user_id)


# 模块级单例
feed_cache = FeedCache()