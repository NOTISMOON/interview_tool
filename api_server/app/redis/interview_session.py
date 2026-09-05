"""面试会话 Redis 模块：操作锁 + 客户端租约（epoch）+ 状态 Checkpoint。

按《面试流程功能文档》§5/§6/§17 设计，三层并发控制：
    ① 操作锁 interview:lock:{session_id}
       单次状态推进互斥（SET NX EX + Lua compare-and-del），短 TTL 覆盖
       最坏 LLM 处理窗口，请求结束（含异常）在 finally 中释放。
    ② 状态版本校验
       由 Checkpoint 的 question_index + phase 组成版本 token（service 层比对），
       本模块仅负责 Checkpoint 的读写。
    ③ 客户端租约 interview:client:{session_id}
       存储 {tab_id, epoch}，进入面试页 activate（同 tab 幂等返回、新 tab
       epoch+1 接管），写请求携带 epoch 与 Redis 比对，不一致即 409。

Checkpoint（interview:checkpoint:{session_id}）为手写状态 JSON（§6.1），
TTL 24 小时每次写入刷新；状态丢失不影响数据正确性（MySQL 逐题落库为
准，Checkpoint 仅做恢复加速，可由 MySQL 重建）。

面试交互链路为同步 HTTP（普通业务），全部使用同步 Redis 客户端；
操作锁按蓝图要求提供异步变体（后台报告任务等异步链路备用）。
"""

import json
import uuid

# ---- 键前缀与默认 TTL ----
_LOCK_PREFIX = "interview:lock:"
_CLIENT_PREFIX = "interview:client:"
_CHECKPOINT_PREFIX = "interview:checkpoint:"

# 操作锁默认 TTL（秒）：覆盖最坏 LLM 处理窗口（LLM_TIMEOUT=120s + 落库缓冲）
DEFAULT_LOCK_TTL = 150
# 客户端租约 TTL（秒）：覆盖会话生命周期（24 小时），完成后随清理流程删除
DEFAULT_CLIENT_TTL = 24 * 3600
# Checkpoint TTL（秒）：24 小时，每次写入刷新（§6.4）
DEFAULT_CHECKPOINT_TTL = 24 * 3600

# 操作锁释放脚本：仅当锁值匹配本次请求 UUID 时才删除（compare-and-del）
_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""

# 客户端租约激活脚本：同 tab_id 幂等返回当前 epoch；新 tab_id 接管 epoch+1
# （原子完成 读-改-写，避免双客户端并发激活的竞态）
_ACTIVATE_CLIENT_LUA = """
local val = redis.call("GET", KEYS[1])
local lease
if val then
    lease = cjson.decode(val)
    if lease["tab_id"] == ARGV[1] then
        redis.call("EXPIRE", KEYS[1], tonumber(ARGV[2]))
        return lease["epoch"]
    end
    lease["tab_id"] = ARGV[1]
    lease["epoch"] = lease["epoch"] + 1
else
    lease = {["tab_id"] = ARGV[1], ["epoch"] = 1}
end
redis.call("SET", KEYS[1], cjson.encode(lease), "EX", tonumber(ARGV[2]))
return lease["epoch"]
"""


def lock_key(session_id: int) -> str:
    """构造面试操作锁键。

    Args:
        session_id: 面试会话ID（interview 表主键）。

    Returns:
        Redis 键字符串。
    """
    return f"{_LOCK_PREFIX}{session_id}"


def client_key(session_id: int) -> str:
    """构造客户端租约键。

    Args:
        session_id: 面试会话ID。

    Returns:
        Redis 键字符串。
    """
    return f"{_CLIENT_PREFIX}{session_id}"


def checkpoint_key(session_id: int) -> str:
    """构造面试状态 Checkpoint 键。

    Args:
        session_id: 面试会话ID。

    Returns:
        Redis 键字符串。
    """
    return f"{_CHECKPOINT_PREFIX}{session_id}"


# --------------------------------------------------------------------------
# ① 操作锁（同步：API 请求路径）
# --------------------------------------------------------------------------

def generate_lock_token() -> str:
    """生成本次状态推进的操作锁值（UUID）。

    Returns:
        唯一锁值字符串。
    """
    return uuid.uuid4().hex


def acquire_lock_sync(client, session_id: int, token: str, ttl: int = DEFAULT_LOCK_TTL) -> bool:
    """尝试获取面试操作锁（SET NX EX）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。
        token: 本次推进的唯一锁值。
        ttl: 锁有效期（秒）。

    Returns:
        获取成功返回True；已被其他请求持有返回False。
    """
    return bool(client.set(lock_key(session_id), token, nx=True, ex=ttl))


def release_lock_sync(client, session_id: int, token: str) -> bool:
    """释放面试操作锁（仅当锁值匹配时删除，防误删他人锁）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。
        token: 本次推进的锁值。

    Returns:
        是否成功释放。
    """
    return bool(client.eval(_RELEASE_LOCK_LUA, 1, lock_key(session_id), token))


# --------------------------------------------------------------------------
# ① 操作锁（异步变体：异步后台任务备用）
# --------------------------------------------------------------------------

async def acquire_lock_async(client, session_id: int, token: str, ttl: int = DEFAULT_LOCK_TTL) -> bool:
    """尝试获取面试操作锁（异步）。

    Args:
        client: 异步 Redis 客户端（redis.asyncio.Redis）。
        session_id: 面试会话ID。
        token: 本次推进的唯一锁值。
        ttl: 锁有效期（秒）。

    Returns:
        获取成功返回True；已被其他请求持有返回False。
    """
    return bool(await client.set(lock_key(session_id), token, nx=True, ex=ttl))


async def release_lock_async(client, session_id: int, token: str) -> bool:
    """释放面试操作锁（异步，compare-and-del）。

    Args:
        client: 异步 Redis 客户端。
        session_id: 面试会话ID。
        token: 本次推进的锁值。

    Returns:
        是否成功释放。
    """
    return bool(await client.eval(_RELEASE_LOCK_LUA, 1, lock_key(session_id), token))


# --------------------------------------------------------------------------
# ③ 客户端租约（epoch，同步）
# --------------------------------------------------------------------------

def activate_client_sync(client, session_id: int, tab_id: str, ttl: int = DEFAULT_CLIENT_TTL) -> int:
    """激活客户端租约：同标签页幂等返回当前 epoch，新标签页接管 epoch+1。

    Lua 原子实现（§5.6）：读-改-写一步完成，双客户端并发激活不会产生
    相同 epoch；返回值即调用方应持有的 epoch（写请求回带校验）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。
        tab_id: 客户端标签页唯一标识（前端生成，sessionStorage 持久）。
        ttl: 租约有效期（秒）。

    Returns:
        本次客户端持有的 epoch 值（≥1）。
    """
    epoch = client.eval(_ACTIVATE_CLIENT_LUA, 1, client_key(session_id), tab_id, ttl)
    return int(epoch)


def get_client_epoch_sync(client, session_id: int) -> int | None:
    """读取当前有效客户端的 epoch（写请求校验用）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。

    Returns:
        当前 epoch；租约不存在（过期/清理）返回 None。
    """
    raw = client.get(client_key(session_id))
    if raw is None:
        return None
    try:
        return int(json.loads(raw).get("epoch", 0))
    except (ValueError, TypeError):
        return None


def clear_client_sync(client, session_id: int) -> bool:
    """清除客户端租约（面试完成/中断后的清理流程，§14.4）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。

    Returns:
        是否删除成功（键不存在也视为成功）。
    """
    client.delete(client_key(session_id))
    return True


# --------------------------------------------------------------------------
# ② Checkpoint 状态 JSON（同步）
# --------------------------------------------------------------------------

def save_checkpoint_sync(client, session_id: int, state: dict, ttl: int = DEFAULT_CHECKPOINT_TTL) -> None:
    """写入面试状态 Checkpoint（整键覆盖 + 刷新 TTL，§6.4）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。
        state: 状态字典（phase/question_index/epoch 等，见 §6.2）。
        ttl: Checkpoint 有效期（秒）。
    """
    client.set(checkpoint_key(session_id), json.dumps(state, ensure_ascii=False, default=str), ex=ttl)


def load_checkpoint_sync(client, session_id: int) -> dict | None:
    """读取面试状态 Checkpoint。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。

    Returns:
        状态字典；不存在或损坏返回 None（由 MySQL 重建兜底）。
    """
    raw = client.get(checkpoint_key(session_id))
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def delete_checkpoint_sync(client, session_id: int) -> None:
    """删除面试状态 Checkpoint。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。
    """
    client.delete(checkpoint_key(session_id))


# --------------------------------------------------------------------------
# ④ 问题队列镜像（T3.8/T3.9：Redis List 备份恢复，防漏题）
# --------------------------------------------------------------------------

_QUEUE_PREFIX = "interview:q:"


def queue_key(session_id: int) -> str:
    """构造问题队列键。

    Args:
        session_id: 面试会话ID。

    Returns:
        Redis 键字符串。
    """
    return f"{_QUEUE_PREFIX}{session_id}"


def init_queue(
    client, session_id: int, question_ids: list[int], ttl: int = DEFAULT_CHECKPOINT_TTL
) -> None:
    """面试正式启动时初始化问题队列：基础题按发问顺序入队（T3.8）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。
        question_ids: 基础题ID列表（发问顺序）。
        ttl: 队列有效期（秒）。
    """
    if not question_ids:
        return
    key = queue_key(session_id)
    client.delete(key)
    client.rpush(key, *[str(qid) for qid in question_ids])
    client.expire(key, ttl)


def enqueue_head(
    client, session_id: int, question_id: int, ttl: int = DEFAULT_CHECKPOINT_TTL
) -> None:
    """追问生成后插入队首（lpush，队首即下一题，T3.8）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。
        question_id: 追问题ID。
        ttl: 队列有效期（秒）。
    """
    key = queue_key(session_id)
    client.lpush(key, str(question_id))
    client.expire(key, ttl)


def remove_from_queue(client, session_id: int, question_id: int) -> None:
    """从队列移除指定题（当前题处理完成后出队）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。
        question_id: 题目ID。
    """
    client.lrem(queue_key(session_id), 0, str(question_id))


def queue_ids(client, session_id: int) -> list[int]:
    """读取队列全部题目ID（审计/恢复核对用）。

    Args:
        client: 同步 Redis 客户端。
        session_id: 面试会话ID。

    Returns:
        题目ID列表（队首在前）。
    """
    raw = client.lrange(queue_key(session_id), 0, -1)
    return [int(x) for x in raw] if raw else []


def delete_queue(client, session_id: int) -> None:
    """删除问题队列（面试完成/中断/删除后清理，释放 Redis 空间）。"""
    client.delete(queue_key(session_id))
