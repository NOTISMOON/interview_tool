"""互动缓存模块（Redis SET 快速判断 + 防穿透，同步Redis客户端）。

Redis键设计:
    post:like:{post_id}        SET   点赞用户ID集合（O(1)判断是否已点赞）
    post:favorite:{post_id}    SET   收藏用户ID集合（O(1)判断是否已收藏）
    post:like:empty:{post_id}  STRING 空点赞标记（防穿透，TTL=60s）
    post:favorite:empty:{post_id} STRING 空收藏标记（防穿透，TTL=60s）

设计要点:
    - SET支持SISMEMBER O(1)判断，比查DB快两个数量级。
    - 一致性：由点赞/取消点赞时同步维护（同步SET + DB同事务），以DB为准可自愈。
    - 空标记：冷门帖子无点赞时缓存空标记，防止高频穿透。
"""

import logging

import redis

logger = logging.getLogger(__name__)

# 缓存TTL常量（秒）
SET_CACHE_TTL = 86400  # 点赞/收藏SET缓存1天

# 缓存键前缀
KEY_LIKE_SET = "post:like:{post_id}"
KEY_FAVORITE_SET = "post:favorite:{post_id}"
KEY_LIKE_EMPTY = "post:like:empty:{post_id}"
KEY_FAVORITE_EMPTY = "post:favorite:empty:{post_id}"

# SET容量上限（预留：当前未启用超限降级查DB逻辑）
SET_MAX_SIZE = 5000


class InteractionCache:
    """互动缓存操作层（同步），封装点赞/收藏的Redis SET读写与失效。"""

    # ------------------------------------------------------------------
    # 点赞 SET
    # ------------------------------------------------------------------

    def is_liked(self, cache_client: redis.Redis, post_id: int, user_id: int) -> bool | None:
        """检查用户是否点赞（Redis SET SISMEMBER O(1)）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 用户ID。

        Returns:
            True=已点赞，False=未点赞，None=缓存miss需查DB。
        """
        key = KEY_LIKE_SET.format(post_id=post_id)
        if not cache_client.exists(key):
            return None
        return bool(cache_client.sismember(key, str(user_id)))

    def add_like(self, cache_client: redis.Redis, post_id: int, user_id: int) -> None:
        """向点赞SET添加用户（SADD幂等）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 用户ID。
        """
        key = KEY_LIKE_SET.format(post_id=post_id)
        try:
            pipe = cache_client.pipeline()
            pipe.sadd(key, str(user_id))
            pipe.expire(key, SET_CACHE_TTL)
            pipe.delete(KEY_LIKE_EMPTY.format(post_id=post_id))
            pipe.execute()
        except Exception:
            logger.exception("点赞缓存写入失败 post_id=%s user_id=%s", post_id, user_id)

    def remove_like(self, cache_client: redis.Redis, post_id: int, user_id: int) -> None:
        """从点赞SET中移除用户（SREM幂等）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 用户ID。
        """
        key = KEY_LIKE_SET.format(post_id=post_id)
        try:
            cache_client.srem(key, str(user_id))
        except Exception:
            logger.exception("点赞缓存移除失败 post_id=%s user_id=%s", post_id, user_id)

    # ------------------------------------------------------------------
    # 收藏 SET
    # ------------------------------------------------------------------

    def is_favorited(self, cache_client: redis.Redis, post_id: int, user_id: int) -> bool | None:
        """检查用户是否收藏（Redis SET SISMEMBER O(1)）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 用户ID。

        Returns:
            True=已收藏，False=未收藏，None=缓存miss需查DB。
        """
        key = KEY_FAVORITE_SET.format(post_id=post_id)
        if not cache_client.exists(key):
            return None
        return bool(cache_client.sismember(key, str(user_id)))

    def add_favorite(self, cache_client: redis.Redis, post_id: int, user_id: int) -> None:
        """向收藏SET添加用户（SADD幂等）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 用户ID。
        """
        key = KEY_FAVORITE_SET.format(post_id=post_id)
        try:
            pipe = cache_client.pipeline()
            pipe.sadd(key, str(user_id))
            pipe.expire(key, SET_CACHE_TTL)
            pipe.delete(KEY_FAVORITE_EMPTY.format(post_id=post_id))
            pipe.execute()
        except Exception:
            logger.exception("收藏缓存写入失败 post_id=%s user_id=%s", post_id, user_id)

    def remove_favorite(self, cache_client: redis.Redis, post_id: int, user_id: int) -> None:
        """从收藏SET中移除用户（SREM幂等）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            user_id: 用户ID。
        """
        key = KEY_FAVORITE_SET.format(post_id=post_id)
        try:
            cache_client.srem(key, str(user_id))
        except Exception:
            logger.exception("收藏缓存移除失败 post_id=%s user_id=%s", post_id, user_id)


# 模块级单例
interaction_cache = InteractionCache()