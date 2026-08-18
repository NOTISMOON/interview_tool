"""Redis 同步分布式锁模块。

特性：
- 可重入：同一实例可多次获取同一把锁
- 可续期：后台看门狗自动续期，防止业务未完成锁就过期
- 可重试：获取锁失败时自动重试，支持配置重试次数和间隔
- 分布式安全：基于 Redis 原子操作，多实例互斥
"""

import logging
import threading
import time
import uuid
from types import TracebackType
from typing import Optional

import redis

from app.redis.sync_client import get_redis

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


class RedisLock:
    """Redis 同步分布式锁（可重入 + 可续期 + 可重试）。

    用法:
        # 上下文管理器
        lock = RedisLock("my_lock", timeout=30, auto_renewal=True)
        with lock:
            do_something()

        # 手动模式
        lock = RedisLock("my_lock")
        if lock.acquire():
            try:
                do_something()
            finally:
                lock.release()

    Args:
        name: 锁名称（Redis key 前缀）
        timeout: 锁超时时间（秒），默认 30 秒
        retry_count: 获取锁失败时的重试次数，默认 0（不重试）
        retry_interval: 重试间隔（秒），默认 0.5 秒
        auto_renewal: 是否开启自动续期，默认 True
        renew_interval: 续期间隔（秒），不传则自动取 timeout / 3
        client: Redis 客户端，不传则使用全局单例
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
        client: Optional[redis.Redis] = None,
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

        self._holder_id = f"{uuid.uuid4().hex}:{threading.get_ident()}"
        self._local_count = 0
        self._watchdog: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def name(self) -> str:
        """锁名称。"""
        return self._name

    @property
    def acquired(self) -> bool:
        """是否已持有锁。"""
        return self._local_count > 0

    def _get_client(self) -> redis.Redis:
        """获取 Redis 客户端。"""
        if self._client is not None:
            return self._client
        return get_redis()

    def acquire(self) -> bool:
        """尝试获取锁，支持重试。

        Returns:
            是否成功获取锁。
        """
        client = self._get_client()

        for attempt in range(self._retry_count + 1):
            result = client.eval(
                ACQUIRE_SCRIPT,
                1,
                self._key,
                self._holder_id,
                str(self._timeout),
            )
            if result == 1:
                self._local_count += 1
                if self._local_count == 1 and self._auto_renewal:
                    self._start_watchdog()
                return True

            if attempt < self._retry_count:
                time.sleep(self._retry_interval)

        return False

    def release(self) -> bool:
        """释放锁。

        Returns:
            是否成功释放。
        """
        if self._local_count <= 0:
            return False

        client = self._get_client()
        result = client.eval(
            RELEASE_SCRIPT,
            1,
            self._key,
            self._holder_id,
            str(self._timeout),
        )

        if result == 1:
            self._local_count -= 1
            if self._local_count == 0:
                self._stop_watchdog()
            return True
        else:
            return False

    def renew(self) -> bool:
        """手动续期。

        Returns:
            是否续期成功。
        """
        if self._local_count <= 0:
            return False

        client = self._get_client()
        result = client.eval(
            RENEW_SCRIPT,
            1,
            self._key,
            self._holder_id,
            str(self._timeout),
        )
        return result == 1

    def _start_watchdog(self) -> None:
        """启动看门狗线程，定时自动续期。"""
        if self._watchdog is not None and self._watchdog.is_alive():
            return
        self._stop_event.clear()

        def _run():
            interval = self._renew_interval / 1000
            while not self._stop_event.wait(interval):
                try:
                    if not self.renew():
                        break
                except Exception:
                    logger.exception("Watchdog renew failed for lock %s", self._name)

        self._watchdog = threading.Thread(target=_run, daemon=True)
        self._watchdog.start()

    def _stop_watchdog(self) -> None:
        """停止看门狗。"""
        self._stop_event.set()
        if self._watchdog is not None:
            self._watchdog.join(timeout=2)
            self._watchdog = None

    # ============ 上下文管理器 ============

    def __enter__(self) -> "RedisLock":
        if not self.acquire():
            raise LockAcquireError(f"获取锁 '{self._name}' 失败，已重试 {self._retry_count} 次")
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.release()

    def __repr__(self) -> str:
        status = "acquired" if self._local_count > 0 else "released"
        return f"<RedisLock name={self._name!r} status={status}>"


class LockAcquireError(Exception):
    """获取锁失败异常。"""

    pass
