"""私信流消费端批量落库 Worker（异步）。

从 Redis Stream 写缓冲读取未落库消息，攒批后批量写入 MySQL，并在同一事务内
写入 Outbox 事件（chat.message.sent），最后 XACK + 清理已落库流数据。

运行形态：独立 asyncio task（由 app.mq.runner 挂载，类似 OutboxRelay），
非 RabbitMQ 消费者——因为它消费的是 Redis Stream 而非 MQ 队列。

流程：
    1. 轮询活跃会话集合 chat:convs:flush（写路径 append_message 时 SADD 登记）。
    2. 对每个会话 XREADGROUP 读取一批待落库消息（设消费组初始监控 $）。
    3. 攒批到 CHAT_FLUSH_BATCH 或超 CHAT_FLUSH_INTERVAL 窗口后批量落库：
        - 批量 INSERT dm_message（INSERT IGNORE，client_msg_id 唯一索引幂等去重）；
        - 更新 dm_conversation 最后消息摘要；
        - 同事务写入 outbox_event（chat.message.sent，outbox_relay 域内扇出）。
    4. XACK 已成功落库的消息；消费失败不 ACK，靠 XPENDING 可靠重投（at-least-once）。
    5. 每批落库后按会话移除活跃登记（避免空转）。

幂等：流消息重投由 INSERT IGNORE + unique(client_msg_id) 消化，重复落库无害。
"""

import asyncio
import logging
import time
from datetime import datetime

from app.core.config import settings
from app.db.async_session import AsyncSessionLocal
from app.redis.async_client import AsyncRedisClient
from app.redis.chat_stream import stream_key
from app.repositories.chat_repository import chat_repository

logger = logging.getLogger(__name__)

# 活跃会话登记集合键（写路径 append_message 登记，worker 据此扫描）
_ACTIVE_CONVS_KEY = "chat:convs:flush"
# 消费组名称（每会话独立分组名）
_GROUP_NAME = "chat-flush"
# XREADGROUP 阻塞超时（秒）：有活跃会话时等待新消息
_BLOCK_MS = 1000
# XREADGROUP 单次读取条数（每次每个会话最多读这么多，攒批更可控）
_READ_COUNT = 50


class ChatFlushWorker:
    """私信流消费端批量落库 Worker（asyncio 任务，单实例随 runner 进程运行）。"""

    def __init__(self) -> None:
        """初始化 Worker，预置任务句柄与停止事件。"""
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """启动 Worker 轮询任务（幂等：重复调用不重复启动）。"""
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="chat-flush-worker")
        logger.info("私信流消费Worker已启动 batch=%d interval=%.2fs", settings.CHAT_FLUSH_BATCH, settings.CHAT_FLUSH_INTERVAL)

    async def stop(self) -> None:
        """停止 Worker 轮询任务并等待退出。"""
        self._stop_event.set()
        if self._task is not None:
            try:
                await self._task
            except Exception:
                logger.exception("私信流消费Worker退出异常")
            self._task = None
        logger.info("私信流消费Worker已停止")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """主循环：扫描活跃会话并逐会话攒批落库，异常兜底防进程退出。"""
        while not self._stop_event.is_set():
            try:
                await self._poll_once()
            except Exception:
                logger.exception("私信流消费Worker轮询异常")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._idle_interval())
            except asyncio.TimeoutError:
                pass

    def _idle_interval(self) -> float:
        """空闲轮询间隔（秒）：无人等待时低频扫描，避免空转烧 CPU。"""
        return max(settings.CHAT_FLUSH_INTERVAL, 0.5)

    async def _poll_once(self) -> None:
        """单轮处理：扫描活跃会话，对每个会话攒批并落库。"""
        redis_client = await AsyncRedisClient.get_client()
        conv_ids = await redis_client.smembers(_ACTIVE_CONVS_KEY)
        if not conv_ids:
            return

        for conv_id_str in conv_ids:
            if self._stop_event.is_set():
                return
            try:
                await self._flush_conversation(redis_client, int(conv_id_str))
            except Exception:
                logger.exception("私信会话落库异常 conv=%s", conv_id_str)

    async def _flush_conversation(self, redis_client, conversation_id: int) -> None:
        """对单个会话：读一批待落库消息，达到批量阈值即落库并 XACK。

        Args:
            redis_client: 异步 Redis 客户端。
            conversation_id: 会话ID。
        """
        s_key = stream_key(conversation_id)

        # 确保消费组存在（首次创建从 $ 开始，后续消息被监控）
        try:
            await redis_client.xgroup_create(s_key, _GROUP_NAME, id="0", mkstream=True)
        except Exception:
            # BUSYGROUP：组已存在则忽略
            pass

        entries = await redis_client.xreadgroup(
            groupname=_GROUP_NAME,
            consumername="worker",
            streams={s_key: ">"},
            count=_READ_COUNT,
            block=_BLOCK_MS,
        )
        if not entries:
            return
        # entries: [(stream, [(id, {field: value}), ...]), ...]
        stream_entries = entries[0][1] if entries else []
        if not stream_entries:
            return

        messages = []
        stream_ids = []
        for stream_id, fields in stream_entries:
            messages.append(
                {
                    "conversation_id": conversation_id,
                    "from_user_id": int(fields.get("from_user_id") or 0),
                    "receiver_id": int(fields.get("receiver_id") or 0),
                    "client_msg_id": str(fields.get("client_msg_id") or ""),
                    "content_type": int(fields.get("content_type", 1)),
                    "content": str(fields.get("content") or ""),
                    "seq": int(fields.get("seq", 0)),
                }
            )
            stream_ids.append(stream_id)

        # 攒批窗口：未达阈值且未超时，等待追加或返回（简化：达到 count 即处理）
        await self._flush_batch(redis_client, conversation_id, messages)
        # 成功落库的 XACK（逐条 ack 已返回的 id）
        if stream_ids:
            await redis_client.xack(s_key, _GROUP_NAME, *stream_ids)

        # 清理活跃登记：该会话已消费完当前缓冲则移除（新增消息会再次 SADD）
        await redis_client.srem(_ACTIVE_CONVS_KEY, str(conversation_id))

    async def _flush_batch(
        self, redis_client, conversation_id: int, messages: list[dict]
    ) -> None:
        """批量落库一批消息并在同一事务写 Outbox 事件。

        Args:
            redis_client: 异步 Redis 客户端。
            conversation_id: 会话ID。
            messages: 待落库消息列表。
        """
        started_at = time.monotonic()
        async with AsyncSessionLocal() as db:
            inserted = await chat_repository.batch_insert_messages(db, messages)

            # 更新会话最后消息摘要：用本批 seq 最大（最后）的一条
            last = max(messages, key=lambda m: m["seq"])
            # 回查该条落库后的自增 ID 用作 last_message_id
            last_msg_id = await self._get_last_message_id(db, conversation_id)
            await chat_repository.update_conversation_tail(
                db,
                conversation_id,
                preview=last["content"],
                last_message_id=last_msg_id,
            )

            # 收到新消息自动恢复隐藏：清除接收方在会话中的隐藏标记
            receiver_ids = {m["receiver_id"] for m in messages}
            await chat_repository.unhide_on_new_message(
                db, conversation_id, receiver_ids
            )

            # 同事务为每条消息各写一条 Outbox 事件（chat.message.sent），
            # 扇出消费者逐条 HINCRBY，未读数才能按消息数正确累加。
            for msg in messages:
                await chat_repository.insert_outbox(
                    db,
                    conversation_id,
                    msg["from_user_id"],
                    msg["receiver_id"],
                    msg["client_msg_id"],
                    msg["seq"],
                )
            await db.commit()

        logger.info(
            "私信批量落库完成 conv=%s inserted=%d batch_size=%d elapsed_ms=%d",
            conversation_id,
            inserted,
            len(messages),
            (time.monotonic() - started_at) * 1000,
        )

    @staticmethod
    async def _get_last_message_id(db, conversation_id: int) -> int:
        """查询会话当前最大消息ID（作为 last_message_id 回填）。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。

        Returns:
            当前最大 dm_message.id。
        """
        from sqlalchemy import text

        result = await db.execute(
            text("SELECT COALESCE(MAX(id), 0) FROM dm_message WHERE conversation_id = :cid"),
            {"cid": conversation_id},
        )
        return int(result.scalar() or 0)


chat_flush_worker = ChatFlushWorker()