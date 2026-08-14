"""Redis 异步分布式锁模块。

特性：
- 可重入：同一实例可多次获取同一把锁
- 可续期：后台异步看门狗自动续期，防止业务未完成锁就过期
- 可重试：获取锁失败时自动重试，支持配置重试次数和间隔
- 分布式安全：基于 Redis 原子操作，多实例互斥
"""

import asyncio
import logging
import uuid
from types import TracebackType
from typing import Optional

import redis.asyncio as aioredis

from app.redis.async_client import get_async_redis

logger = logging.getLogger(__name__)

# ============ Lua 脚本 ============

ACQUIRE_SCRIPT = """
if redis.call("EXISTS", KEYS[1]) == 0 then
    redis.call("HINCRBY", KEYS[1], ARGV[1], 1)
    redis.call("PEXPIRE", KEYS[1], ARGV[2])
    return 1
elseif redis.call("HEXISTS", KEYS[1], ARGV[1]) == 1 then
    redis.call("HINCRBY", KEYS[1], ARGV[1], 1)
    redis.call("PEXPIRE", KEYS[1], ARGV[2])
    return 1
else
    return 0
end
"""

RELEASE_SCRIPT = """
if redis.call("HEXISTS", KEYS[1], ARGV[1]) == 0 then
    return 0
end
local count = redis.call("HINCRBY", KEYS[1], ARGV[1], -1)
if count > 0 then
    redis.call("PEXPIRE", KEYS[1], ARGV[2])
    return 1
else
    redis.call("DEL", KEYS[1])
    return 1
end
"""

RENEW_SCRIPT = """
if redis.call("HEXISTS", KEYS[1], ARGV[1]) == 1 then
    redis.call("PEXPIRE", KEYS[1], ARGV[2])
    return 1
else
    return 0
end
"""


class AsyncRedisLock:
    """Redis 异步分布式锁（可重入 + 可续期 + 可重试）。

    用法:
        # 异步上下文管理器
        lock = AsyncRedisLock("my_lock", timeout=30, auto_renewal=True)
        async with lock:
            await do_something()

        # 手动模式
        lock = AsyncRedisLock("my_lock")
        if await lock.acquire():
            try:
                await do_something()
            finally:
                await lock.release()

    Args:
        name: 锁名称（Redis key 前缀）
        timeout: 锁超时时间（秒），默认 30 秒
        retry_count: 获取锁失败时的重试次数，默认 0（不重试）
        retry_interval: 重试间隔（秒），默认 0.5 秒
        auto_renewal: 是否开启自动续期，默认 True
        renew_interval: 续期间隔（秒），不传则自动取 timeout / 3
        client: Redis 异步客户端，不传则使用全局单例
    """

    LOCK_PREFIX = "lock:"

    def __init__(
        self,
        name: str,
        timeout: float = 30.0,
        retry_count: int = 0,
        retry_interval: float = 0.5,
        auto_renewal: bool = True,
        renew_interval: Optional[float] = None,
        client: Optional[aioredis.Redis] = None,
    ):
        self._name = name
        self._key = f"{self.LOCK_PREFIX}{name}"
        self._timeout = int(timeout * 1000)
        self._retry_count = retry_count
        self._retry_interval = retry_interval
        self._auto_renewal = auto_renewal
        if renew_interval is not None:
            self._renew_interval = renew_interval * 1000
        else:
            self._renew_interval = timeout / 3 * 1000
        self._client = client

        self._holder_id = f"{uuid.uuid4().hex}:{id(asyncio.current_task())}"
        self._local_count = 0
        self._watchdog_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

    @property
    def name(self) -> str:
        """锁名称。"""
        return self._name

    @property
    def acquired(self) -> bool:
        """是否已持有锁。"""
        return self._local_count > 0

    async def _get_client(self) -> aioredis.Redis:
        """获取 Redis 异步客户端。"""
        if self._client is not None:
            return self._client
        return await get_async_redis()

    async def acquire(self) -> bool:
        """尝试获取锁，支持重试。

        Returns:
            是否成功获取锁。
        """
        client = await self._get_client()

        for attempt in range(self._retry_count + 1):
            result = await client.eval(
                ACQUIRE_SCRIPT,
                1,
                self._key,
                self._holder_id,
                str(self._timeout),
            )
            if result == 1:
                self._local_count += 1
                if self._local_count == 1 and self._auto_renewal:
                    await self._start_watchdog()
                return True

            if attempt < self._retry_count:
                await asyncio.sleep(self._retry_interval)

        return False

    async def release(self) -> bool:
        """释放锁。

        Returns:
            是否成功释放。
        """
        if self._local_count <= 0:
            return False

        client = await self._get_client()
        result = await client.eval(
            RELEASE_SCRIPT,
            1,
            self._key,
            self._holder_id,
            str(self._timeout),
        )

        if result == 1:
            self._local_count -= 1
            if self._local_count == 0:
                await self._stop_watchdog()
            return True
        else:
            return False

    async def renew(self) -> bool:
        """手动续期。

        Returns:
            是否续期成功。
        """
        if self._local_count <= 0:
            return False

        client = await self._get_client()
        result = await client.eval(
            RENEW_SCRIPT,
            1,
            self._key,
            self._holder_id,
            str(self._timeout),
        )
        return result == 1

    async def _start_watchdog(self) -> None:
        """启动异步看门狗，定时自动续期。"""
        if self._watchdog_task is not None and not self._watchdog_task.done():
            return
        self._stop_event = asyncio.Event()

        async def _run():
            interval = self._renew_interval / 1000
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=interval
                    )
                    break
                except asyncio.TimeoutError:
                    try:
                        if not await self.renew():
                            break
                    except Exception:
                        logger.exception(
                            "Watchdog renew failed for lock %s", self._name
                        )

        self._watchdog_task = asyncio.create_task(_run())

    async def _stop_watchdog(self) -> None:
        """停止异步看门狗。"""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._watchdog_task is not None:
            try:
                await asyncio.wait_for(self._watchdog_task, timeout=2)
            except asyncio.TimeoutError:
                self._watchdog_task.cancel()
            self._watchdog_task = None
            self._stop_event = None

    # ============ 异步上下文管理器 ============

    async def __aenter__(self) -> "AsyncRedisLock":
        if not await self.acquire():
            raise LockAcquireError(
                f"获取锁 '{self._name}' 失败，已重试 {self._retry_count} 次"
            )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.release()

    def __repr__(self) -> str:
        status = "acquired" if self._local_count > 0 else "released"
        return f"<AsyncRedisLock name={self._name!r} status={status}>"


class LockAcquireError(Exception):
    """获取锁失败异常。"""
    pass