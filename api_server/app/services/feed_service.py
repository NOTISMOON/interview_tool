"""Feed信息流业务逻辑层（Push-Pull混合模型，同步）。

Push-Pull流程:
    Push阶段（发帖时，MQ Consumer异步）:
        1. 从关注SET取出粉丝列表
        2. 大V（粉丝>1万）跳过Push，粉丝自行Pull
        3. 批量ZADD post_id到粉丝 feed:inbox:user:{follower_id}

    Pull阶段（用户读取Feed时，同步）:
        1. 先查缓存 feed:user:{user_id}
        2. 缓存命中 → 直接返回帖子ID列表
        3. 缓存miss → 从MySQL拉取关注者最新帖子 + 收件箱内容 → 合并去重 → 写缓存 → 返回
"""

import logging
from typing import Any

import redis
from sqlalchemy.orm import Session

from app.cache.feed_cache import feed_cache
from app.repositories.post_repository import post_repository

logger = logging.getLogger(__name__)


class FeedService:
    """Feed信息流业务逻辑层（同步），实现Push-Pull混合模型。"""

    def get_feed(
        self,
        db: Session,
        cache_client: redis.Redis,
        user_id: int,
        *,
        cursor: int | None = None,
        limit: int = 20,
    ) -> tuple[list[int], int | None]:
        """获取用户Feed（Pull模式，游标分页）。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            user_id: 用户ID。
            cursor: 游标（上一页最后一条的score）。
            limit: 每页条数。

        Returns:
            (post_ids, next_cursor)，next_cursor=None表示没有更多。
        """
        # 1. 查缓存
        if feed_cache.is_feed_cached(cache_client, user_id):
            post_ids = feed_cache.get_feed(cache_client, user_id, cursor=cursor, limit=limit)
            if post_ids:
                next_cursor = post_ids[-1] if len(post_ids) == limit else None
                return post_ids, next_cursor

        # 2. 缓存miss → Pull重建
        inbox_items = feed_cache.get_inbox(cache_client, user_id, cursor=None, limit=FEED_PULL_LIMIT)

        # 3. 从MySQL补充（补偿Pull：查询关注者最新帖子）
        from app.repositories.user_repository import sync_user_repository as follow_repo
        following_ids = follow_repo.get_following_ids(db, user_id)
        db_posts = post_repository.list_following_posts(
            db,
            following_ids=following_ids,
            cursor=None,
            limit=FEED_PULL_LIMIT,
        )

        # 4. 合并去重，按时间倒序
        all_posts: dict[int, int] = {}
        for pid, score in inbox_items:
            all_posts[pid] = max(all_posts.get(pid, 0), score)
        for p in db_posts:
            score = int(p.created_at.timestamp() * 1000)
            all_posts[p.id] = max(all_posts.get(p.id, 0), score)

        # 5. 排序写入缓存
        sorted_items = sorted(all_posts.items(), key=lambda x: x[1], reverse=True)
        feed_cache.merge_feed(cache_client, user_id, sorted_items[:FEED_MAX_SIZE])

        # 6. 分页返回
        post_ids = [pid for pid, _ in sorted_items]
        if cursor is not None:
            post_ids = [pid for pid in post_ids if pid < cursor]
        page = post_ids[:limit]
        next_cursor = page[-1] if len(page) == limit else None
        return page, next_cursor


# 常量
FEED_PULL_LIMIT = 200  # Pull阶段拉取上限
FEED_MAX_SIZE = 1000  # Feed缓存最大容量

# 模块级单例
feed_service = FeedService()