"""帖子缓存模块（Cache-Aside + 穿透/击穿/雪崩防护，同步Redis客户端）。

Redis键设计:
    post:detail:{post_id}     STRING  帖子详情JSON（含作者信息、标签）
    post:null:{post_id}       STRING  空值标记（"NULL"），TTL短（60s），防缓存穿透
    post:rebuild:{post_id}    LOCK    分布式锁，防缓存击穿（互斥回源）

防护策略:
    - 缓存穿透: 查询不存在的帖子时，缓存空值"NULL"（TTL=60s），避免打到DB。
    - 缓存击穿: 热点帖子过期瞬间，使用Redis分布式锁互斥回源（仅一个请求查DB重建缓存）。
    - 缓存雪崩: TTL叠加随机偏移（base_ttl + random(0, 300)），避免同一时刻大量Key同时过期。
"""

import json
import logging
import random
from typing import Any

import redis
from sqlalchemy.orm import Session

from app.redis.sync_lock import RedisLock

logger = logging.getLogger(__name__)

# 缓存TTL常量（秒）
DETAIL_CACHE_TTL = 3600  # 帖子详情缓存1小时
NULL_CACHE_TTL = 60  # 空值缓存1分钟
TTL_JITTER = 300  # TTL随机偏移上限（秒），防雪崩

# 缓存键前缀
KEY_DETAIL = "post:detail:{post_id}"
KEY_NULL = "post:null:{post_id}"
LOCK_REBUILD = "post:rebuild:{post_id}"

# 缓存空值标记
NULL_VALUE = "NULL"


class PostCache:
    """帖子缓存操作层（同步），封装Cache-Aside读写与穿透/击穿/雪崩防护。"""

    # ------------------------------------------------------------------
    # 详情缓存读（Cache-Aside）
    # ------------------------------------------------------------------

    def get_detail(self, cache_client: redis.Redis, post_id: int) -> dict[str, Any] | None:
        """从缓存读取帖子详情。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。

        Returns:
            帖子详情字典（命中正常数据），或None（缓存miss需回源DB）。
            注意：缓存中"NULL"表示帖子不存在，返回None后由上层判断。
        """
        key = KEY_DETAIL.format(post_id=post_id)
        data = cache_client.get(key)
        if data is None:
            return None
        if data == NULL_VALUE:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("帖子缓存数据损坏 post_id=%s", post_id)
            cache_client.delete(key)
            return None

    def is_null_cached(self, cache_client: redis.Redis, post_id: int) -> bool:
        """检查帖子是否缓存了空值标记（表示帖子不存在或已删除）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。

        Returns:
            True表示缓存了空值，可直接返回404，无需查DB。
        """
        key = KEY_NULL.format(post_id=post_id)
        return cache_client.get(key) == NULL_VALUE

    # ------------------------------------------------------------------
    # 详情缓存写
    # ------------------------------------------------------------------

    def set_detail(self, cache_client: redis.Redis, post_id: int, data: dict[str, Any]) -> None:
        """写入帖子详情缓存（TTL叠加随机偏移防雪崩）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
            data: 帖子详情字典（由Service层组装）。
        """
        ttl = DETAIL_CACHE_TTL + random.randint(0, TTL_JITTER)
        key = KEY_DETAIL.format(post_id=post_id)
        try:
            cache_client.setex(key, ttl, json.dumps(data, ensure_ascii=False))
        except Exception:
            logger.exception("帖子缓存写入失败 post_id=%s", post_id)

    def set_null(self, cache_client: redis.Redis, post_id: int) -> None:
        """写入空值标记（防穿透，TTL短）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
        """
        key = KEY_NULL.format(post_id=post_id)
        try:
            cache_client.setex(key, NULL_CACHE_TTL, NULL_VALUE)
        except Exception:
            logger.exception("空值缓存写入失败 post_id=%s", post_id)

    # ------------------------------------------------------------------
    # 缓存击穿防护（分布式锁互斥回源）
    # ------------------------------------------------------------------

    def acquire_rebuild_lock(self, cache_client: redis.Redis, post_id: int) -> RedisLock:
        """获取缓存重建分布式锁，用于互斥回源。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。

        Returns:
            RedisLock对象，可用于上下文管理器。
        """
        lock_key = LOCK_REBUILD.format(post_id=post_id)
        return RedisLock(
            name=lock_key,
            timeout=10,  # 10秒超时（重建缓存通常很快）
            retry_count=0,  # 不重试，拿不到锁就等
            auto_renewal=False,  # 缓存重建不需要续期
            client=cache_client,
        )

    # ------------------------------------------------------------------
    # 缓存失效
    # ------------------------------------------------------------------

    def invalidate_detail(self, cache_client: redis.Redis, post_id: int) -> None:
        """失效帖子详情缓存（更新/删除帖子后调用）。

        Args:
            cache_client: 同步Redis客户端。
            post_id: 帖子ID。
        """
        try:
            cache_client.delete(KEY_DETAIL.format(post_id=post_id), KEY_NULL.format(post_id=post_id))
        except Exception:
            logger.exception("帖子缓存失效失败 post_id=%s", post_id)


# 模块级单例
post_cache = PostCache()