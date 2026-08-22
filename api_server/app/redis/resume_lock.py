"""简历分析分布式锁模块。

按蓝图 §3.3/§3.4 设计，调度侧与 Worker 共享同一把 Redis 锁，防止同一简历
被并发调度触发多次分析。

- 键：resume:analysis:lock:{resume_id}
- 值：task_uuid（调度侧生成，随 MQ 消息下发；Worker 提交结果前校验值一致，
      防止锁过期后旧任务重复写入）
- TTL：600 秒（覆盖 10 分钟分析目标；锁续期为 M2 范围）
- 释放：Lua compare-and-del，仅当值匹配才删除，避免误删他人锁

调度侧为同步路径使用同步 Redis 客户端；Worker 为异步路径使用异步 Redis 客户端，
二者操作同一键值，互不干扰。
"""

import uuid

# 锁键前缀
_LOCK_PREFIX = "resume:analysis:lock:"
# 锁默认 TTL（秒），与蓝图一致，覆盖长文本简历的 10 分钟分析目标
DEFAULT_TTL = 600

# 释放脚本：仅当锁值匹配任务uuid时才删除（compare-and-del）
_RELEASE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


def lock_key(resume_id: int) -> str:
    """构造简历分析锁键。

    Args:
        resume_id: 简历ID。

    Returns:
        Redis 锁键字符串。
    """
    return f"{_LOCK_PREFIX}{resume_id}"


def generate_task_uuid(resume_id: int) -> str:
    """生成随任务下发的锁值（task_uuid），并拼接简历ID提升可追溯性。

    Args:
        resume_id: 简历ID。

    Returns:
        task_uuid 字符串（Redis锁值）。
    """
    return f"{resume_id}:{uuid.uuid4().hex}"


# --------------------------------------------------------------------------
# 同步实现（调度侧，上传回调内调用）
# --------------------------------------------------------------------------

def acquire_sync(client, resume_id: int, task_uuid: str, ttl: int = DEFAULT_TTL) -> bool:
    """尝试获取简历分析锁（SET NX EX，幂等保护）。

    Args:
        client: 同步 Redis 客户端。
        resume_id: 简历ID。
        task_uuid: 任务标识（锁值）。
        ttl: 锁有效期（秒）。

    Returns:
        获取成功返回True；锁已被他人持有返回False。
    """
    return bool(client.set(lock_key(resume_id), task_uuid, nx=True, ex=ttl))


def verify_sync(client, resume_id: int, task_uuid: str) -> bool:
    """校验当前锁值是否等于任务uuid（Worker 提交前防重复写入）。

    Args:
        client: 同步 Redis 客户端。
        resume_id: 简历ID。
        task_uuid: 期望的任务标识。

    Returns:
        锁存在且值匹配返回True，否则False。
    """
    return client.get(lock_key(resume_id)) == task_uuid


def release_sync(client, resume_id: int, task_uuid: str) -> bool:
    """释放简历分析锁（仅当锁值匹配时删除）。

    Args:
        client: 同步 Redis 客户端。
        resume_id: 简历ID。
        task_uuid: 任务标识。

    Returns:
        是否成功释放。
    """
    return bool(client.eval(_RELEASE_LUA, 1, lock_key(resume_id), task_uuid))


def delete_sync(client, resume_id: int) -> bool:
    """无条件清除简历分析锁（独立删简历/强制重调度时使用）。

    场景：删除简历或对失败简历一键重试时，需无条件释放可能残留的分析锁，
    避免旧的锁值阻塞后续重新调度（蓝图§3.3 锁要点：finally必释放）。

    Args:
        client: 同步 Redis 客户端。
        resume_id: 简历ID。

    Returns:
        是否清除成功（键不存在也视为成功，幂等）。
    """
    return bool(client.delete(lock_key(resume_id)))


# --------------------------------------------------------------------------
# 异步实现（Worker 侧，消费任务时调用）
# --------------------------------------------------------------------------

async def acquire_async(client, resume_id: int, task_uuid: str, ttl: int = DEFAULT_TTL) -> bool:
    """尝试获取简历分析锁（异步）。

    Args:
        client: 异步 Redis 客户端（redis.asyncio.Redis）。
        resume_id: 简历ID。
        task_uuid: 任务标识（锁值）。
        ttl: 锁有效期（秒）。

    Returns:
        获取成功返回True；锁已被他人持有返回False。
    """
    return bool(await client.set(lock_key(resume_id), task_uuid, nx=True, ex=ttl))


async def verify_async(client, resume_id: int, task_uuid: str) -> bool:
    """校验当前锁值是否等于任务uuid（异步）。

    Args:
        client: 异步 Redis 客户端。
        resume_id: 简历ID。
        task_uuid: 期望的任务标识。

    Returns:
        锁存在且值匹配返回True，否则False。
    """
    return await client.get(lock_key(resume_id)) == task_uuid


async def release_async(client, resume_id: int, task_uuid: str) -> bool:
    """释放简历分析锁（异步，compare-and-del）。

    Args:
        client: 异步 Redis 客户端。
        resume_id: 简历ID。
        task_uuid: 任务标识。

    Returns:
        是否成功释放。
    """
    return bool(await client.eval(_RELEASE_LUA, 1, lock_key(resume_id), task_uuid))
