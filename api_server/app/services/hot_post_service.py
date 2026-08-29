"""热门帖子服务层：浏览数统计、热度增量累加、Redis ZSET 计算与读取。

职责：
  - 浏览数统计：Redis 计数器 INCR + 定时同步到 MySQL（每 5 分钟）
  - 热度增量：互动（点赞/评论/浏览）发生时累加热度分到 Redis ZSET post:hot:score，
    避免定时任务全量扫描数据库
  - 热门计算：定时任务（每 10 分钟）从 post:hot:score ZSET 取候选 Top N，
    仅针对候选批量查 MySQL（IN 查询，不扫全表）应用时间衰减，产出 Top 100
  - 缓存对账：定时校验 Redis ZSET 与 MySQL 一致性
"""

import json
import logging
from datetime import datetime, timedelta

import redis
from sqlalchemy import text, update, func
from sqlalchemy.orm import Session

from app.db.sync_session import SyncSessionLocal
from app.redis.sync_client import get_redis

logger = logging.getLogger(__name__)

# 热门帖子最终 ZSET Key
HOT_ZSET_KEY = "post:hot"
# 热度增量 ZSET Key（互动时累加分数，定时任务读取）
HOT_SCORE_ZSET_KEY = "post:hot:score"
# 浏览数计数器 Key 前缀
VIEWS_PREFIX = "post:views:"
# 浏览数同步锁 Key
VIEWS_SYNC_LOCK_KEY = "lock:views:sync"
# 热门计算锁 Key
HOT_CALC_LOCK_KEY = "lock:hot:calc"
# 缓存对账锁 Key（多实例防重复对账）
RECONCILE_CACHE_LOCK_KEY = "lock:hot:reconcile"

# 热度公式参数
LIKE_WEIGHT = 3          # 点赞权重
COMMENT_WEIGHT = 5       # 评论权重
VIEW_WEIGHT = 0.1        # 浏览权重
DECAY_FACTOR = 1.5       # 时间衰减系数（每小时）
HOT_TOP_N = 100          # 热门帖子 Top N
HOT_RECENT_DAYS = 7      # 统计近 7 天帖子
# 定时任务从增量 ZSET 取的候选数（留出衰减淘汰空间，不必扫全表）
HOT_CANDIDATE_N = 300

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
        """记录一次帖子浏览（Redis 计数器 INCR + 热度分累加）。

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
            # 热度分同步累加（浏览权重）
            self.increment_hot_score(client, post_id, VIEW_WEIGHT)
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
    # 热度分增量维护（互动埋点，避免定时任务全量扫库）
    # ------------------------------------------------------------------

    def add_post_to_hot_score(self, client: redis.Redis, post_id: int) -> None:
        """帖子创建时加入热度增量 ZSET（初始分 0）。

        Args:
            client: Redis 客户端。
            post_id: 帖子 ID。
        """
        try:
            client.zadd(HOT_SCORE_ZSET_KEY, {str(post_id): 0})
            client.expire(HOT_SCORE_ZSET_KEY, HOT_RECENT_DAYS * 86400)
        except Exception:
            logger.exception("帖子加入热度 ZSET 失败 post_id=%s", post_id)

    def increment_hot_score(self, client: redis.Redis, post_id: int, delta: float) -> None:
        """互动时累加热度分（点赞/评论/浏览）。

        Args:
            client: Redis 客户端。
            post_id: 帖子 ID。
            delta: 热度增量（权重值，可为负）。
        """
        try:
            client.zincrby(HOT_SCORE_ZSET_KEY, delta, str(post_id))
            client.expire(HOT_SCORE_ZSET_KEY, HOT_RECENT_DAYS * 86400)
        except Exception:
            logger.exception("热度分累加失败 post_id=%s delta=%s", post_id, delta)

    def remove_post_from_hot_score(self, client: redis.Redis, post_id: int) -> None:
        """删除帖子时从热度增量 ZSET 移除。

        Args:
            client: Redis 客户端。
            post_id: 帖子 ID。
        """
        try:
            client.zrem(HOT_SCORE_ZSET_KEY, str(post_id))
        except Exception:
            logger.exception("热度 ZSET 移除失败 post_id=%s", post_id)

    def _bootstrap_hot_score(self, client: redis.Redis, db: Session, now: datetime) -> None:
        """首次部署迁移：从 DB 一次性加载现有帖子互动数据初始化热度 ZSET。

        仅在增量 ZSET 为空（无任何互动记录）时触发一次，之后全部走增量路径。

        Args:
            client: Redis 客户端。
            db: 数据库会话。
            now: 当前时间。
        """
        from app.models.post import Post, POST_STATUS_NORMAL

        rows = (
            db.query(Post)
            .filter(
                Post.status == POST_STATUS_NORMAL,
                Post.created_at >= now - timedelta(days=HOT_RECENT_DAYS),
                Post.tags.isnot(None),
                func.json_length(Post.tags) > 0,
            )
            .all()
        )
        pipeline = client.pipeline()
        for post in rows:
            base_score = (
                post.likes_count * LIKE_WEIGHT
                + post.comments_count * COMMENT_WEIGHT
                + post.views_count * VIEW_WEIGHT
            )
            pipeline.zadd(HOT_SCORE_ZSET_KEY, {str(post.id): base_score})
        if rows:
            pipeline.expire(HOT_SCORE_ZSET_KEY, HOT_RECENT_DAYS * 86400)
            pipeline.execute()
        logger.info("热门热度 ZSET 初始化完成: 加载 %s 条现有帖子", len(rows))

    # ------------------------------------------------------------------
    # 热门计算
    # ------------------------------------------------------------------

    def calc_hot_posts(self) -> int:
        """计算热门帖子并更新缓存（基于 Redis 增量 ZSET，不扫全表）。

        流程：
          1. 从 post:hot:score ZSET 取候选 Top N（仅互动过的帖子，天然近 7 天）
          2. 批量查 MySQL（IN 查询）过滤状态与标签
          3. 对候选应用时间衰减，计算最终热度分
          4. 更新 Top 100 帖子的 is_hot=1，其余 is_hot=0
          5. 写入 Redis ZSET post:hot

        Returns:
            本次更新的热门帖子数。
        """
        db = SyncSessionLocal()
        try:
            now = datetime.now()
            client = self._get_cache()

            # 1. 从增量 ZSET 取候选（互动过的帖子，不扫全表）
            members = client.zrevrange(HOT_SCORE_ZSET_KEY, 0, HOT_CANDIDATE_N - 1)
            candidate_ids = [int(m) for m in members if str(m).isdigit()]

            from app.models.post import Post, POST_STATUS_NORMAL

            if not candidate_ids:
                # 首次部署/迁移兜底：增量 ZSET 为空时，一次性从 DB 加载现有帖子
                # 的互动数据初始化 ZSET（仅触发一次，之后都走增量路径）
                self._bootstrap_hot_score(client, db, now)
                members = client.zrevrange(HOT_SCORE_ZSET_KEY, 0, HOT_CANDIDATE_N - 1)
                candidate_ids = [int(m) for m in members if str(m).isdigit()]

            if not candidate_ids:
                # 仍无候选：清空所有热门标记，避免历史热门残留
                db.execute(update(Post).where(Post.is_hot == 1).values(is_hot=0))
                db.commit()
                logger.info("热门计算：无互动候选，清空热门标记")
                return 0

            # 2. 批量查 MySQL（IN 查询，仅候选数量，不扫全表）
            posts = (
                db.query(Post)
                .filter(
                    Post.id.in_(candidate_ids),
                    Post.status == POST_STATUS_NORMAL,
                    Post.created_at >= now - timedelta(days=HOT_RECENT_DAYS),
                    Post.tags.isnot(None),
                    func.json_length(Post.tags) > 0,
                )
                .all()
            )

            if not posts:
                db.execute(update(Post).where(Post.is_hot == 1).values(is_hot=0))
                db.commit()
                logger.info("热门计算：候选均无效，清空热门标记")
                return 0

            # 3. 计算最终热度分：互动累计分 - 时间衰减
            #    从 ZSET 读原始累计分作为"热度基础"，再按帖子创建时间衰减
            score_map: dict[int, float] = {}
            for pid, score in client.zrange(HOT_SCORE_ZSET_KEY, 0, -1, withscores=True):
                try:
                    score_map[int(pid)] = float(score)
                except (ValueError, TypeError):
                    continue

            scored: list[tuple[int, float]] = []
            for post in posts:
                hours_elapsed = (now - post.created_at).total_seconds() / 3600
                time_decay = hours_elapsed * DECAY_FACTOR
                base_score = score_map.get(post.id, 0.0)
                score = base_score - time_decay
                scored.append((post.id, max(score, 0)))

            # 按热度分降序排序
            scored.sort(key=lambda x: x[1], reverse=True)
            # 仅热度分 > 0 的帖子有资格成为热门
            eligible = [(pid, score) for pid, score in scored if score > 0]

            # Top 100 为热门
            hot_ids = {pid for pid, _ in eligible[:HOT_TOP_N]}

            # 4. 批量更新 is_hot
            db.execute(update(Post).where(Post.is_hot == 1).values(is_hot=0))
            if hot_ids:
                db.execute(
                    update(Post).where(Post.id.in_(list(hot_ids))).values(is_hot=1)
                )
            db.commit()

            # 5. 写入 Redis ZSET
            pipeline = client.pipeline()
            pipeline.delete(HOT_ZSET_KEY)
            for pid, score in eligible[:HOT_TOP_N]:
                pipeline.zadd(HOT_ZSET_KEY, {str(pid): score})
            pipeline.expire(HOT_ZSET_KEY, 7 * 86400)
            pipeline.execute()

            logger.info("热门计算完成: Top %s, 候选 %s, 无候选扫描", len(hot_ids), len(candidate_ids))
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
                .filter(
                    Post.status == POST_STATUS_NORMAL,
                    Post.is_hot == 1,
                    Post.tags.isnot(None),
                    func.json_length(Post.tags) > 0,
                )
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