"""私信 Redis Stream 写缓冲模块（异步）。

高吞吐写路径（Agent 业务）使用异步 Redis 客户端：
    - 每条消息 XADD 到 stream:conv:{conversation_id}，Redis 自动分配递增 id，天然按会话保序。
    - 用 Lua 脚本一次原子完成三件事：
        1. 幂等校验（cmid 集合里是否已存在该 client_msg_id）；
        2. seq 分配（chat:seq:{conv_id} INCR，非首次重复发送不递增，避免跳号）；
        3. XADD 追加到 Stream。
    - 若已存在（重复发送/断线重发同 client_msg_id），脚本返回 existed 标记，调用方直接回执，
      不重复写缓冲；最终去重由 MySQL dm_message.client_msg_id 唯一索引兜底。

存储约定（与《私信功能文档.md》§4 一致）：
    - stream:conv:{conv_id}         写缓冲 Stream（XADD 后 XTRIM ~MAXLEN 裁剪）
    - chat:cmid:{conv_id}           本会话已写 client_msg_id 集合（幂等快速拦截，带 TTL）
    - chat:seq:{conv_id}            同会话自增序号
"""

import logging
import time
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.redis.async_client import AsyncRedisClient

logger = logging.getLogger(__name__)

# 写入脚本：幂等校验 + seq 分配 + XADD 三者原子完成。
# ARGV 布局（固定字段，避免脚本内做数组/JSON 解析）：
#   ARGV[1]=client_msg_id  ARGV[2]=conversation_id  ARGV[3]=from_user_id
#   ARGV[4]=receiver_id    ARGV[5]=content_type     ARGV[6]=content
#   ARGV[7]=ts
# 返回 [existed, seq]：
#   existed=1 表示该 client_msg_id 已在本会话写入过（重复），seq 为已分配值；
#   existed=0 表示首次写入，seq 为新分配的递增序号。
_WRITE_LUA = """
local cmid = ARGV[1]
local conv_id = ARGV[2]
local from_uid = ARGV[3]
local to_uid = ARGV[4]
local content_type = ARGV[5]
local content = ARGV[6]
local ts = ARGV[7]
local stream_key = KEYS[1]
local cmid_set = KEYS[2]
local seq_key = KEYS[3]

if redis.call("SISMEMBER", cmid_set, cmid) == 1 then
    local seq = redis.call("GET", seq_key)
    if not seq then seq = 0 end
    return {1, tonumber(seq)}
end

local seq = redis.call("INCR", seq_key)
redis.call(
    "XADD", stream_key, "*",
    "conversation_id", conv_id,
    "from_user_id", from_uid,
    "receiver_id", to_uid,
    "client_msg_id", cmid,
    "content_type", content_type,
    "content", content,
    "ts", ts,
    "seq", tostring(seq)
)
redis.call("SADD", cmid_set, cmid)
return {0, seq}
"""

# 幂等集合 TTL（秒）：覆盖"断线重发"足够长时间，同时避免无界增长（权威去重全靠 DB 唯一索引）
_CMID_SET_TTL_SECONDS = 86400 * 7

# 活跃会话登记集合键：写缓冲时登记，流消费Worker据此扫描待落库会话
_ACTIVE_CONVS_KEY = "chat:convs:flush"


def stream_key(conversation_id: int) -> str:
    """构造会话写缓冲 Stream 键。

    Args:
        conversation_id: 会话ID。

    Returns:
        Redis Stream 键字符串。
    """
    return f"stream:conv:{conversation_id}"


def cmid_set_key(conversation_id: int) -> str:
    """构造会话幂等 client_msg_id 集合键。

    Args:
        conversation_id: 会话ID。

    Returns:
        Redis SET 键字符串。
    """
    return f"chat:cmid:{conversation_id}"


def seq_key(conversation_id: int) -> str:
    """构造会话自增序号键。

    Args:
        conversation_id: 会话ID。

    Returns:
        Redis 计数器键字符串。
    """
    return f"chat:seq:{conversation_id}"


async def _get_client() -> aioredis.Redis:
    """获取异步 Redis 客户端单例。

    Returns:
        异步 Redis 客户端实例。
    """
    return await AsyncRedisClient.get_client()


async def append_message(
    conversation_id: int,
    from_user_id: int,
    receiver_id: int,
    client_msg_id: str,
    content: str,
    content_type: int = 1,
) -> tuple[bool, int]:
    """将一条私信写入会话写缓冲（幂等 + 保序）。

    流程：
        1. Lua 原子执行：判重 client_msg_id → 分配 seq → XADD 到 Stream。
        2. 若是首次写入，XTRIM 近似裁剪 Stream，并给幂等集合设置 TTL。
        3. 返回 (is_new, seq)：is_new=False 表示重复消息，配合 seq 幂等回执。

    Args:
        conversation_id: 会话ID。
        from_user_id: 发送方用户ID。
        receiver_id: 接收方用户ID。
        client_msg_id: 客户端UUID幂等键。
        content: 消息内容。
        content_type: 内容类型（1-文本 2-图片 3-文件），默认文本。

    Returns:
        (is_new, seq)：is_new 是否首次写入，seq 该消息在本会话的序号。

    Raises:
        aioredis.RedisError: Redis 写入失败时抛出。
    """
    client = await _get_client()

    stream = stream_key(conversation_id)
    cmid_set = cmid_set_key(conversation_id)
    seq_key_name = seq_key(conversation_id)

    now_ms = int(time.time() * 1000)
    result = await client.eval(
        _WRITE_LUA,
        3,  # numkeys
        stream,
        cmid_set,
        seq_key_name,
        client_msg_id,
        str(conversation_id),
        str(from_user_id),
        str(receiver_id),
        str(content_type),
        content,
        str(now_ms),
    )
    existed = int(result[0])
    seq = int(result[1])

    if existed == 1:
        logger.info("私信重复消息跳过写缓冲 conv=%s cmid=%s seq=%s", conversation_id, client_msg_id, seq)
        return False, seq

    # 首写：近似裁剪 Stream 上限，登记活跃会话集合，幂等集合 TTL（防无界增长）
    await client.xtrim(stream, maxlen=settings.CHAT_STREAM_MAXLEN, approximate=True)
    await client.sadd(_ACTIVE_CONVS_KEY, str(conversation_id))
    await client.expire(cmid_set, _CMID_SET_TTL_SECONDS)

    logger.info(
        "私信已写入写缓冲 conv=%s cmid=%s seq=%s sender=%s",
        conversation_id,
        client_msg_id,
        seq,
        from_user_id,
    )
    return True, seq


async def is_duplicate(conversation_id: int, client_msg_id: str) -> bool:
    """检查 client_msg_id 是否已在会话写缓冲中写入过（快速幂等预检）。

    供 WS 接收处理器在进入 Lua 前做一次低成本判断；最终仍以 Lua/DB 唯一索引为准。

    Args:
        conversation_id: 会话ID。
        client_msg_id: 客户端UUID幂等键。

    Returns:
        True 表示已存在（重复发送）。
    """
    client = await _get_client()
    return bool(await client.sismember(cmid_set_key(conversation_id), client_msg_id))