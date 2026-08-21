"""定时任务定义模块，注册 APScheduler 定时任务。

所有任务内部使用 Redis 分布式锁防止多实例重复执行。
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.redis.sync_lock import RedisLock
from app.services.hot_post_service import (
    HOT_CALC_LOCK_KEY,
    VIEWS_SYNC_LOCK_KEY,
    hot_post_service,
)

logger = logging.getLogger(__name__)


def sync_views_job() -> None:
    """定时任务：同步浏览数从 Redis 到 MySQL（每 5 分钟）。

    使用 Redis 分布式锁防止多实例重复执行。
    """
    lock = RedisLock(
        name=VIEWS_SYNC_LOCK_KEY,
        timeout=120,
        retry_count=0,
        auto_renewal=True,
    )
    if not lock.acquire():
        logger.info("浏览数同步被跳过（其他实例正在执行）")
        return
    try:
        count = hot_post_service.sync_views_to_db()
        logger.info("浏览数同步定时任务完成: 更新 %s 条帖子", count)
    except Exception:
        logger.exception("浏览数同步定时任务失败")
    finally:
        lock.release()


def calc_hot_job() -> None:
    """定时任务：计算热门帖子（每 10 分钟）。

    使用 Redis 分布式锁防止多实例重复执行。
    """
    lock = RedisLock(
        name=HOT_CALC_LOCK_KEY,
        timeout=120,
        retry_count=0,
        auto_renewal=True,
    )
    if not lock.acquire():
        logger.info("热门计算被跳过（其他实例正在执行）")
        return
    try:
        count = hot_post_service.calc_hot_posts()
        logger.info("热门计算定时任务完成: Top %s 帖子", count)
    except Exception:
        logger.exception("热门计算定时任务失败")
    finally:
        lock.release()


def reconcile_hot_cache_job() -> None:
    """定时任务：缓存对账（每 30 分钟）。

    校验 Redis ZSET 与 MySQL is_hot 标记的一致性，差异过大时自动重建。
    """
    try:
        result = hot_post_service.reconcile()
        if result.get("rebuilt"):
            logger.warning("缓存对账触发重建: %s", result)
        else:
            logger.info("缓存对账完成: %s", result)
    except Exception:
        logger.exception("缓存对账定时任务失败")


def create_scheduler() -> BackgroundScheduler:
    """创建并配置 APScheduler 后台调度器。

    Returns:
        配置好的 BackgroundScheduler 实例。
    """
    scheduler = BackgroundScheduler(daemon=True)

    # 浏览数同步：每 5 分钟
    scheduler.add_job(
        sync_views_job,
        trigger=IntervalTrigger(minutes=5),
        id="sync_views",
        name="同步浏览数 Redis→MySQL",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # 热门计算：每 10 分钟
    scheduler.add_job(
        calc_hot_job,
        trigger=IntervalTrigger(minutes=10),
        id="calc_hot",
        name="计算热门帖子",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # 缓存对账：每 30 分钟
    scheduler.add_job(
        reconcile_hot_cache_job,
        trigger=IntervalTrigger(minutes=30),
        id="reconcile_hot_cache",
        name="热门缓存对账",
        replace_existing=True,
        misfire_grace_time=120,
    )

    logger.info("定时任务调度器已创建: 浏览数同步(5min), 热门计算(10min), 缓存对账(30min)")
    return scheduler