"""评论缓存模块（Cache-Aside + 穿透防护，同步Redis客户端）。

Redis键设计:
    post:comments:{post_id}:p{cursor}  STRING  帖子一级评论列表JSON（带游标分页，TTL=5分钟）
    post:comments:null:{post_id}       STRING  空评论列表标记（"NULL"，TTL=60s，防穿透）

设计要点:
    - 评论列表变动频繁（新增/删除），TTL设短（5分钟），避免脏读过久。
    - 仅缓存首页（键内游标段固定为 "0"），翻页直接查DB（低频操作，收益低）。
    - 空列表防穿透：缓存"NULL"标记60s，避免恶意刷无评论帖子打DB。
    - 缓存失效：新评论创建时删除首页列表缓存与空值标记（防穿透键），下次查询回源重建。
"""

import logging

import redis

logger = logging.getLogger(__name__)

# 缓存键前缀
KEY_COMMENT_LIST = "post:comments:{post_id}:p{cursor}"
KEY_COMMENT_NULL = "post:comments:null:{post_id}"


class CommentCache:
    """评论缓存操作层（同步），封装评论列表缓存失效。"""

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