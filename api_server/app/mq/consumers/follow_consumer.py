"""关注缓存同步消费者模块。

消费 social.follow.cache.queue 队列（由Outbox Relay投递），将关注/取关/注销
事件异步同步到Redis缓存（ZSET分页 + SET关系判断），闭环读路径的缓存一致性。

幂等性: 全部使用天然幂等的Redis命令（ZADD同member同score覆盖、
SADD/SREM/ZREM重复执行结果不变、DEL重复执行无害），重复消费无需去重表；
message_id（=outbox行id）仅用于日志追踪。

事件路由: 按消息routing_key分发（social.follow.created / social.follow.deleted /
social.user.deactivated），与outbox event_type一一对应。

失败处理: pipeline抛异常（如Redis不可用）→ 基类reject(requeue=False) →
经DLX进入死信队列存档，人工重放或等待缓存TTL自愈（回源以DB为准）。
"""

import logging
from typing import Any

import redis.asyncio as aioredis

from app.cache.follow_cache import (
    DIRECTION_FOLLOWERS,
    DIRECTION_FOLLOWING,
    FOLLOW_CHANGE_LUA,
    follow_cache,
)
from app.mq.consumer import BaseConsumer, MQMessage
from app.mq.queues import QueueName
from app.redis.async_client import AsyncRedisClient

logger = logging.getLogger(__name__)

# 注销事件关联键清理的分批大小（每批pipeline命令数，避免大pipeline阻塞事件循环）
DEACTIVATED_BATCH_SIZE = 500

# routing_key常量（与outbox_relay.EVENT_ROUTING_KEY_MAP一致）
ROUTING_FOLLOW_CREATED = "social.follow.created"
ROUTING_FOLLOW_DELETED = "social.follow.deleted"
ROUTING_USER_DEACTIVATED = "social.user.deactivated"


class FollowCacheSyncConsumer(BaseConsumer):
    """关注缓存同步消费者，消费三类Outbox事件并幂等维护Redis缓存。"""

    queue_name = QueueName.SOCIAL_FOLLOW_CACHE

    async def handle_message(self, message: MQMessage) -> None:
        """按routing_key分发到对应事件处理器。

        Args:
            message: 入站消息对象（payload为outbox_event.payload原样透传）。

        Raises:
            ValueError: 未知routing_key或payload缺少必要字段时抛出，进入死信队列。
        """
        payload = message.payload
        if message.routing_key == ROUTING_FOLLOW_CREATED:
            await self._on_follow_created(payload)
        elif message.routing_key == ROUTING_FOLLOW_DELETED:
            await self._on_follow_deleted(payload)
        elif message.routing_key == ROUTING_USER_DEACTIVATED:
            await self._on_user_deactivated(payload)
        else:
            raise ValueError(f"未知routing_key: {message.routing_key} message_id={message.message_id}")

    # ------------------------------------------------------------------
    # 事件处理器
    # ------------------------------------------------------------------

    async def _on_follow_created(self, payload: dict[str, Any]) -> None:
        """处理关注事件：Lua原子增量同步（键存在才ZADD/SADD+清空标记+刷TTL）。

        键不存在（未回源）时跳过增量写，避免建立只含单个成员的残缺缓存
        （残缺缓存会令rebuild的double-check误判已重建而跳过全量回源）；
        写路径已同步执行相同脚本，本消费者作为兜底（幂等，重复执行无害）。

        Args:
            payload: 含follower_id、following_id、created_at_ms的事件负载。
        """
        follower_id = int(payload["follower_id"])
        following_id = int(payload["following_id"])
        # score=服务端写入payload的毫秒时间戳，与读路径回源口径一致（规避时区换算偏差）
        score_ms = int(payload["created_at_ms"])

        client = await AsyncRedisClient.get_client()
        keys_and_args = follow_cache.follow_change_keys_and_args(follower_id, following_id, score_ms)
        await client.eval(FOLLOW_CHANGE_LUA, 6, *keys_and_args)
        logger.info(
            "关注事件缓存同步完成 follower_id=%s following_id=%s score_ms=%s",
            follower_id,
            following_id,
            score_ms,
        )

    async def _on_follow_deleted(self, payload: dict[str, Any]) -> None:
        """处理取关事件：双向ZREM/SREM（不写空标记、不删键，保留剩余数据与TTL）。

        键不存在（未回源）时命令空操作，无害。

        Args:
            payload: 含follower_id、following_id的事件负载。
        """
        follower_id = int(payload["follower_id"])
        following_id = int(payload["following_id"])

        client = await AsyncRedisClient.get_client()
        pipe = client.pipeline()
        pipe.zrem(follow_cache._zset_key(follower_id, DIRECTION_FOLLOWING), str(following_id))
        pipe.zrem(follow_cache._zset_key(following_id, DIRECTION_FOLLOWERS), str(follower_id))
        pipe.srem(follow_cache._set_key(follower_id, DIRECTION_FOLLOWING), str(following_id))
        pipe.srem(follow_cache._set_key(following_id, DIRECTION_FOLLOWERS), str(follower_id))
        await pipe.execute()
        logger.info("取关事件缓存同步完成 follower_id=%s following_id=%s", follower_id, following_id)

    async def _on_user_deactivated(self, payload: dict[str, Any]) -> None:
        """处理注销事件：删自身4键 + 分批清理双向关联键成员（闭环读路径B-14）。

        Args:
            payload: 含user_id、following_ids、follower_ids的事件负载。
        """
        user_id = int(payload["user_id"])
        following_ids = [int(x) for x in payload.get("following_ids", [])]
        follower_ids = [int(x) for x in payload.get("follower_ids", [])]

        client = await AsyncRedisClient.get_client()
        # ① 注销用户自身4键直接删除
        pipe = client.pipeline()
        pipe.delete(
            follow_cache._zset_key(user_id, DIRECTION_FOLLOWING),
            follow_cache._zset_key(user_id, DIRECTION_FOLLOWERS),
            follow_cache._set_key(user_id, DIRECTION_FOLLOWING),
            follow_cache._set_key(user_id, DIRECTION_FOLLOWERS),
        )
        await pipe.execute()

        # ② 从"TA关注的人"的粉丝缓存中移除TA（分批pipeline避免大pipeline阻塞）
        for i in range(0, len(following_ids), DEACTIVATED_BATCH_SIZE):
            batch = following_ids[i : i + DEACTIVATED_BATCH_SIZE]
            pipe = client.pipeline()
            for target_id in batch:
                pipe.zrem(follow_cache._zset_key(target_id, DIRECTION_FOLLOWERS), str(user_id))
                pipe.srem(follow_cache._set_key(target_id, DIRECTION_FOLLOWERS), str(user_id))
            await pipe.execute()

        # ③ 从"TA的粉丝"的关注缓存中移除TA
        for i in range(0, len(follower_ids), DEACTIVATED_BATCH_SIZE):
            batch = follower_ids[i : i + DEACTIVATED_BATCH_SIZE]
            pipe = client.pipeline()
            for target_id in batch:
                pipe.zrem(follow_cache._zset_key(target_id, DIRECTION_FOLLOWING), str(user_id))
                pipe.srem(follow_cache._set_key(target_id, DIRECTION_FOLLOWING), str(user_id))
            await pipe.execute()

        logger.info(
            "注销事件缓存同步完成 user_id=%s following_count=%d follower_count=%d truncated=%s",
            user_id,
            len(following_ids),
            len(follower_ids),
            payload.get("truncated", False),
        )
