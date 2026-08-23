"""私信读路径业务服务（异步）。

聚合会话列表/消息分页所需的数据：会话记录 + 对方用户简要信息 + 未读数。
未读数从 Redis `unread:{user_id}`（hash: conversation_id -> 未读数）读取，
与写路径扇出消费者侧 HINCRBY 保持一致。
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.redis.sync_client import SyncRedisClient
from app.repositories.chat_repository import chat_repository
from app.repositories.user_repository import user_repository
from app.schemas.chat import (
    ConversationResponse,
    CreateConversationResponse,
    DmMessageResponse,
    MessageListResponse,
    PeerInfo,
)

logger = logging.getLogger(__name__)

# 未读数 HASH 键前缀（与扇出消费者保持一致）
UNREAD_KEY_PREFIX = "unread:"
# 会话列表每次返回条数
CONV_LIST_LIMIT = 50


class ChatService:
    """私信读路径业务服务。"""

    async def list_conversations(self, db: AsyncSession, user_id: int) -> list[ConversationResponse]:
        """查询当前用户的会话列表（含对方信息与未读数，按最后消息时间倒序）。

        Args:
            db: 数据库异步会话。
            user_id: 当前用户ID。

        Returns:
            会话响应列表（含 peer 信息与未读数）。
        """
        convs = await chat_repository.list_conversations(db, user_id)

        # 收集对方用户ID（批量查，避免 N+1）
        peer_ids = [conv.user2_id if conv.user1_id == user_id else conv.user1_id for conv in convs]
        users = await user_repository.get_users_by_ids(db, peer_ids)
        user_map = {u.id: u for u in users}

        # 读取未读数（同步 Redis 经线程池，避免阻塞事件循环）
        unread_map = {}
        if convs:
            redis_client = SyncRedisClient.get_client()
            unread_map = await asyncio.to_thread(redis_client.hgetall, f"{UNREAD_KEY_PREFIX}{user_id}")

        items = []
        for conv in convs:
            peer = user_map.get(
                conv.user2_id if conv.user1_id == user_id else conv.user1_id
            )
            items.append(
                ConversationResponse(
                    id=conv.id,
                    peer=PeerInfo(
                        id=peer.id,
                        nickname=peer.nickname,
                        avatar=peer.avatar,
                    )
                    if peer
                    else None,
                    last_message=conv.last_message,
                    last_message_at=conv.last_message_at,
                    last_message_id=conv.last_message_id,
                    unread=int(unread_map.get(str(conv.id), 0) or 0),
                )
            )
        return items

    async def get_or_create_conversation(
        self, db: AsyncSession, user_id: int, other_id: int
    ) -> CreateConversationResponse:
        """获取或创建与另一用户（Id>0）的会话。

        不允许与自己私信（其他_id == user_id 时拒绝）。

        Args:
            db: 数据库异步会话。
            user_id: 当前用户ID。
            other_id: 对方用户ID。

        Returns:
            会话创建响应（含 id 与 created 标记）。
        """
        existed = await chat_repository.get_conversation_by_pair(
            db, user_id=user_id, other_id=other_id
        )
        if existed:
            return CreateConversationResponse(id=existed.id, created=False)
        conv = await chat_repository.get_or_create_conversation(db, user_id, other_id)
        await db.commit()
        return CreateConversationResponse(id=conv.id, created=True)

    async def list_messages(
        self, db: AsyncSession, conversation_id: int, user_id: int, cursor: int, size: int
    ) -> MessageListResponse | None:
        """分页查询会话消息（按 seq DESC，最新在前）。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。
            user_id: 当前用户ID（校验会话成员）。
            cursor: 翻页游标（上一页最小 seq 或 0 取最新）。
            size: 每页条数。

        Returns:
            消息列表响应；会话不存在或非成员时返回 None。
        """
        conv = await chat_repository.get_conversation(db, conversation_id, user_id)
        if conv is None:
            return None

        messages = await chat_repository.list_messages(db, conversation_id, cursor, size)
        # 游标下一页 = 本页最小 seq（若本页为空则为 None）
        next_cursor = messages[-1].seq if messages else None
        # 本页无更多时（不足 size）标记无下一页
        if len(messages) < min(size, 50):
            next_cursor = None

        unread_total = await self.get_conversation_unread(db, conversation_id, user_id)
        return MessageListResponse(
            items=[DmMessageResponse.model_validate(m) for m in messages],
            next_cursor=next_cursor,
            unread_total=unread_total,
        )

    async def get_conversation_unread(
        self, db: AsyncSession, conversation_id: int, user_id: int
    ) -> int:
        """查询会话中发给当前用户的未读消息数（DB 兜底，防缓存缺失）。

        Args:
            db: 数据库异步会话。
            conversation_id: 会话ID。
            user_id: 当前用户ID（接收方）。

        Returns:
            未读消息数量。
        """
        return await chat_repository.count_conversation_unread(db, conversation_id, user_id)


chat_service = ChatService()