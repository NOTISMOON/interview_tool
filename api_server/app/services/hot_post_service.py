"""热门帖子服务层：浏览数统计、热门计算、Redis ZSET 缓存读写。

职责：
  - 浏览数统计：Redis 计数器 INCR + 定时同步到 MySQL（每 5 分钟）
  - 热门计算：定时任务（每 10 分钟）按热度公式计算 Top 100，更新 is_hot + ZSET
  - 缓存对账：定时校验 Redis ZSET 与 MySQL 一致性
"""

import json
import logging
from datetime import datetime, timedelta

import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.sync_session import SyncSessionLocal
from app.redis.sync_client import get_redis

logger = logging.getLogger(__name__)

# 热门帖子 ZSET Key
HOT_ZSET_KEY = "post:hot"
# 浏览数计数器 Key 前缀
VIEWS_PREFIX = "post:views:"
# 浏览数同步锁 Key
VIEWS_SYNC_LOCK_KEY = "lock:views:sync"
# 热门计算锁 Key
HOT_CALC_LOCK_KEY = "lock:hot:calc"

# 热度公式参数
LIKE_WEIGHT = 3          # 点赞权重
COMMENT_WEIGHT = 5       # 评论权重
VIEW_WEIGHT = 0.1        # 浏览权重
DECAY_FACTOR = 1.5       # 时间衰减系数（每小时）
HOT_TOP_N = 100          # 热门帖子 Top N
HOT_RECENT_DAYS = 7      # 统计近 7 天帖子

# 缓存对账阈值
RECONCILE_THRESHOLD = 10  # ZSET 大小与 MySQL 标记数差异超过该值则触发重建


class HotPostService:
    """热门帖子业务服务层，提供浏览数追踪、同步、热门计算与缓存管理。"""

    def __init__(self, cache_client: redis.Redis | None = None) -> None:
        """初始化热门帖子服务。

        Args:
            cache_client: 同步 Redis 客户端，不传则使用全局单例。
        """
        self._cache_client = cache_client

    # ------------------------------------------------------------------
    # 浏览数追踪
    # ------------------------------------------------------------------

    def record_view(self, post_id: int) -> None:
        """记录一次帖子浏览（Redis 计数器 INCR）。

        不阻塞、不写 MySQL，纯粹 Redis 计数器累加，定时任务批量同步到 DB。

        Args:
            post_id: 帖子 ID。
        """
        try:
            client = self._get_cache()
            key = f"{VIEWS_PREFIX}{post_id}"
            client.incr(key, 1)
            # 设置过期时间（当天 23:59:59 过期，防止内存泄漏）
            if client.ttl(key) == -1:
                now = datetime.now()
                expire_seconds = int(
                    (now.replace(hour=23, minute=59, second=59) - now).total_seconds()
                )
                if expire_seconds > 0:
                    client.expire(key, expire_seconds)
        except Exception:
            logger.exception("记录浏览数失败 post_id=%s", post_id)

    def sync_views_to_db(self) -> int:
        """同步浏览数从 Redis 到 MySQL。

        扫描所有 post:views:* 计数器，批量 UPDATE post.views_count，
        同步完成后删除计数器（重置）。

        Returns:
            本次同步的帖子数。
        """
        client = self._get_cache()
        db = SyncSessionLocal()
        try:
            # 扫描所有浏览计数器
            cursor = 0
            total_updated = 0
            batch: dict[int, int] = {}

            while True:
                cursor, keys = client.scan(cursor, match=f"{VIEWS_PREFIX}*", count=200)
                for key in keys:
                    try:
                        post_id = int(key.replace(VIEWS_PREFIX, ""))
                        views = int(client.get(key) or 0)
                        if views > 0:
                            batch[post_id] = views
                    except (ValueError, TypeError):
                        continue

                if cursor == 0:
                    break

            if not batch:
                return 0

            # 批量 UPDATE MySQL
            from app.models.post import Post

            for post_id, views in batch.items():
                db.execute(
                    text("UPDATE post SET views_count = views_count + :views WHERE id = :id"),
                    {"views": views, "id": post_id},
                )
                total_updated += 1

            db.commit()

            # 同步成功后删除 Redis 计数器
            if batch:
                redis_keys = [f"{VIEWS_PREFIX}{pid}" for pid in batch]
                client.delete(*redis_keys)

            logger.info("浏览数同步完成: %s 条帖子, 总浏览增量 %s", total_updated, sum(batch.values()))
            return total_updated
        except Exception:
            logger.exception("浏览数同步失败")
            db.rollback()
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 热门计算
    # ------------------------------------------------------------------

    def calc_hot_posts(self) -> int:
        """计算热门帖子并更新缓存。

        流程：
          1. 查询近 7 天正常帖子
          2. 按热度公式计算每条帖子的热度分
          3. 更新 Top 100 帖子的 is_hot=1，其余 is_hot=0
          4. 写入 Redis ZSET post:hot

        Returns:
            本次更新的热门帖子数。
        """
        db = SyncSessionLocal()
        try:
            now = datetime.now()
            since = now - timedelta(days=HOT_RECENT_DAYS)

            # 查询近 7 天正常帖子
            from app.models.post import Post, POST_STATUS_NORMAL

            rows = (
                db.query(Post)
                .filter(
                    Post.status == POST_STATUS_NORMAL,
                    Post.created_at >= since,
                )
                .all()
            )

            if not rows:
                logger.info("热门计算：近 %s 天无帖子", HOT_RECENT_DAYS)
                return 0

            # 计算热度分
            scored: list[tuple[int, float]] = []
            for post in rows:
                hours_elapsed = (now - post.created_at).total_seconds() / 3600
                time_decay = hours_elapsed * DECAY_FACTOR
                score = (
                    post.likes_count * LIKE_WEIGHT
                    + post.comments_count * COMMENT_WEIGHT
                    + post.views_count * VIEW_WEIGHT
                    - time_decay
                )
                scored.append((post.id, max(score, 0)))

            # 按热度分降序排序
            scored.sort(key=lambda x: x[1], reverse=True)

            # Top 100 为热门
            hot_ids = {pid for pid, _ in scored[:HOT_TOP_N]}

            # 批量更新 is_hot
            all_post_ids = [pid for pid, _ in scored]
            if all_post_ids:
                # 全部置为 0
                db.execute(
                    text("UPDATE post SET is_hot = 0 WHERE id IN :ids"),
                    {"ids": all_post_ids},
                )
                # 热门置为 1
                if hot_ids:
                    db.execute(
                        text("UPDATE post SET is_hot = 1 WHERE id IN :ids"),
                        {"ids": list(hot_ids)},
                    )
                db.commit()

            # 写入 Redis ZSET
            client = self._get_cache()
            pipeline = client.pipeline()
            pipeline.delete(HOT_ZSET_KEY)
            for pid, score in scored[:HOT_TOP_N]:
                pipeline.zadd(HOT_ZSET_KEY, {str(pid): score})
            # 设置 TTL：7 天，防内存泄漏
            pipeline.expire(HOT_ZSET_KEY, 7 * 86400)
            pipeline.execute()

            logger.info("热门计算完成: Top %s, 共扫描 %s 条帖子", len(hot_ids), len(rows))
            return len(hot_ids)
        except Exception:
            logger.exception("热门计算失败")
            db.rollback()
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 热门帖子查询
    # ------------------------------------------------------------------

    def get_hot_post_ids(self, top_n: int = 20) -> list[int]:
        """从 Redis ZSET 获取热门帖子 ID 列表。

        Args:
            top_n: 返回条数（默认 20）。

        Returns:
            热门帖子 ID 列表（按热度降序）。
        """
        client = self._get_cache()
        try:
            members = client.zrevrange(HOT_ZSET_KEY, 0, top_n - 1)
            return [int(m) for m in members]
        except Exception:
            logger.exception("查询热门帖子 ZSET 失败")
            return []

    # ------------------------------------------------------------------
    # 缓存对账
    # ------------------------------------------------------------------

    def reconcile(self) -> dict:
        """校验 Redis ZSET 与 MySQL is_hot 标记的一致性。

        检查 ZSET 大小与 MySQL 中 is_hot=1 的帖子数是否一致，
        若差异超过阈值则触发重建。

        Returns:
            对账结果字典，包含 status、zset_size、db_count、rebuilt 等字段。
        """
        client = self._get_cache()
        db = SyncSessionLocal()
        result = {"status": "ok", "zset_size": 0, "db_count": 0, "rebuilt": False}
        try:
            zset_size = client.zcard(HOT_ZSET_KEY) or 0
            from app.models.post import Post, POST_STATUS_NORMAL

            db_count = (
                db.query(Post)
                .filter(Post.status == POST_STATUS_NORMAL, Post.is_hot == 1)
                .count()
            )
            result["zset_size"] = zset_size
            result["db_count"] = db_count

            diff = abs(zset_size - db_count)
            if diff > RECONCILE_THRESHOLD:
                logger.warning(
                    "缓存对账发现差异: ZSET=%s DB=%s diff=%s，触发重建",
                    zset_size,
                    db_count,
                    diff,
                )
                hot_count = self.calc_hot_posts()
                result["status"] = "rebuilt"
                result["rebuilt"] = True
                result["rebuilt_count"] = hot_count
            return result
        except Exception:
            logger.exception("缓存对账失败")
            result["status"] = "error"
            return result
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 删除帖子时清除热门缓存
    # ------------------------------------------------------------------

    def remove_from_hot_cache(self, post_id: int) -> None:
        """从热门帖子 ZSET 中移除指定帖子。

        Args:
            post_id: 帖子 ID。
        """
        try:
            client = self._get_cache()
            client.zrem(HOT_ZSET_KEY, str(post_id))
        except Exception:
            logger.exception("从热门 ZSET 移除失败 post_id=%s", post_id)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_cache(self) -> redis.Redis:
        """获取 Redis 客户端。

        Returns:
            同步 Redis 客户端实例。
        """
        if self._cache_client is not None:
            return self._cache_client
        return get_redis()


# 模块级单例
hot_post_service = HotPostService()