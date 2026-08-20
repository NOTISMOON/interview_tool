"""评论缓存模块（Cache-Aside + 穿透防护，同步Redis客户端）。

Redis键设计:
    post:comments:{post_id}:p{cursor}  STRING  帖子一级评论列表JSON（带游标分页，TTL=5分钟）
    post:comments:null:{post_id}       STRING  空评论列表标记（"NULL"，TTL=60s，防穿透）

设计要点:
    - 评论列表变动频繁（新增/删除），TTL设短（5分钟），避免脏读过久。
    - 仅缓存首页（cursor=None），翻页直接查DB（低频操作，收益低）。
    - 空列表防穿透：缓存"NULL"标记60s，避免恶意刷无评论帖子打DB。
    - 缓存失效：新评论创建时仅删除首页缓存，下次查询回源重建。
"""

import json
import logging
import random
from typing import Any

import redis

logger = logging.getLogger(__name__)

# 缓存TTL常量（秒）
COMMENT_LIST_CACHE_TTL = 300  # 评论列表缓存5分钟
NULL_CACHE_TTL = 60  # 空列表缓存1分钟
TTL_JITTER = 60  # TTL随机偏移上限（秒），防雪崩

# 缓存键前缀
KEY_COMMENT_LIST = "post:comments:{post_id}:p{cursor}"
KEY_COMMENT_NULL = "post:comments:null:{post_id}"

# 缓存空值标记
NULL_VALUE = "NULL"


class CommentCache:
    """评论缓存操作层（同步），封装评论列表缓存读写与失效。"""

    # ------------------------------------------------------------------
    # 评论列表缓存（仅缓存首页）
    # ------------------------------------------------------------------

    def get_list(self, cache_client: redis.Redis, post_id: int) -> list[dict[str, Any]] | None:
        """从缓存读取帖子首页评论列表。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。

        Returns:
            评论列表字典，缓存miss返回None。
        """
        key = KEY_COMMENT_LIST.format(post_id=post_id, cursor="0")
        data = cache_client.get(key)
        if data is None:
            return None
        if data == NULL_VALUE:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("评论缓存数据损坏 post_id=%s", post_id)
            cache_client.delete(key)
            return None

    def is_null_cached(self, cache_client: redis.Redis, post_id: int) -> bool:
        """检查是否缓存了空评论标记。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。

        Returns:
            True表示缓存了空值，可直接返回空列表。
        """
        key = KEY_COMMENT_NULL.format(post_id=post_id)
        return cache_client.get(key) == NULL_VALUE

    def set_list(self, cache_client: redis.Redis, post_id: int, data: list[dict[str, Any]]) -> None:
        """写入帖子首页评论列表缓存（TTL叠加随机偏移防雪崩）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            data: 评论列表字典（由Service层组装）。
        """
        ttl = COMMENT_LIST_CACHE_TTL + random.randint(0, TTL_JITTER)
        key = KEY_COMMENT_LIST.format(post_id=post_id, cursor="0")
        try:
            cache_client.setex(key, ttl, json.dumps(data, ensure_ascii=False))
        except Exception:
            logger.exception("评论缓存写入失败 post_id=%s", post_id)

    def set_null(self, cache_client: redis.Redis, post_id: int) -> None:
        """写入空评论列表标记（防穿透，TTL短）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
        """
        key = KEY_COMMENT_NULL.format(post_id=post_id)
        try:
            cache_client.setex(key, NULL_CACHE_TTL, NULL_VALUE)
        except Exception:
            logger.exception("评论空值缓存写入失败 post_id=%s", post_id)

    # ------------------------------------------------------------------
    # 缓存失效
    # ------------------------------------------------------------------

    def invalidate_list(self, cache_client: redis.Redis, post_id: int) -> None:
        """失效帖子评论列表缓存（新评论创建时调用）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
        """
        key = KEY_COMMENT_LIST.format(post_id=post_id, cursor="0")
        null_key = KEY_COMMENT_NULL.format(post_id=post_id)
        try:
            cache_client.delete(key, null_key)
        except Exception:
            logger.exception("评论缓存失效失败 post_id=%s", post_id)


# 模块级单例
comment_cache = CommentCache()