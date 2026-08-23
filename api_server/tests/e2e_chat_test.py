"""端到端测试：私信 M1/M2 全链路（真实 Redis + MySQL + RabbitMQ + MQ runner）。

覆盖《私信功能文档.md》核心链路：
    1. WS 未认证连接 → 4001 关闭
    2. WS 认证连接 send → 写缓冲回执 sent+seq
    3. 消息写入 Redis Stream + 活跃会话登记
    4. flush Worker 批量落库 dm_message + 更新 dm_conversation
    5. Outbox chat.message.sent 事件 → relay 投递 → 扇出未读数 unread:{receiver} +1
    6. 幂等：重复 send 同 client_msg_id → duplicate 回执，不重复落库
    7. 保序：连发多条 seq 严格递增

用法: 在 api_server 目录下用 interview 环境运行
    python tests/e2e_chat_test.py

前提:
    - uvicorn 运行中（加载 chat WS 路由）
    - MQ runner 运行中（私信流消费Worker + chat.fanout 消费者 + Outbox Relay）
    - MySQL/Redis/RabbitMQ 正常。结束自动清理测试数据（dm 表行 + Redis 键）。
"""

import asyncio
import json
import random
import string
import sys
import time
from pathlib import Path

import jwt
import redis
from sqlalchemy import text

# 允许直接 python 运行时从项目根导入 app 包（脚本位于 tests/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.db.sync_session import SyncSessionLocal

# ---- 配置 ----
BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000/api/v1/chat/ws"
SECRET_KEY = "change-me-in-production"  # 与 api_server/.env 保持一致
SENDER_ID = 1  # 发送方用户
RECEIVER_ID = 17  # 接收方用户

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    """记录单个断言结果。"""
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        FAIL.append((name, detail))
        print(f"  [FAIL] {name} -> {detail}")


def make_token(user_id: int) -> str:
    """生成与后端一致的 JWT（HS256，sub 为字符串用户ID）。"""
    return jwt.encode({"sub": str(user_id), "login": f"user_{user_id}"}, SECRET_KEY, algorithm="HS256")


def random_cmid() -> str:
    """生成随机 client_msg_id（模拟客户端UUID，满足 min_length=8）。"""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=24))


def redis_client() -> redis.Redis:
    """获取同步 Redis 客户端（读缓存/未读数验证用）。"""
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def setup_conversation() -> int:
    """创建测试会话（user1 < user2 规范化），返回 conversation_id。"""
    db = SyncSessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO dm_conversation (user1_id, user2_id) VALUES (:a, :b)"
            ),
            {"a": min(SENDER_ID, RECEIVER_ID), "b": max(SENDER_ID, RECEIVER_ID)},
        )
        db.commit()
        cid = db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
        print(f"[SETUP] 会话已创建: conversation_id={cid}")
        return cid
    finally:
        db.close()


async def connect_ws(token: str):
    """建立 WS 连接（携带 Cookie 认证）。

    Args:
        token: JWT 访问令牌。

    Returns:
        (websocket, 是否成功接入)。
    """
    import websockets.asyncio.client as ws_client

    try:
        ws = await ws_client.connect(
            WS_BASE,
            additional_headers={"Cookie": f"access_token={token}"},
            close_timeout=3,
        )
        return ws, True
    except Exception as exc:
        return None, False


async def send_message(ws, conversation_id: int, cmid: str, content: str, content_type: int = 1) -> dict:
    """通过 WS 发送一条私信，返回服务端回执（JSON）。

    Args:
        ws: WS 连接。
        conversation_id: 会话ID。
        cmid: 客户端幂等键。
        content: 消息内容。
        content_type: 内容类型。

    Returns:
        服务端回执字典。
    """
    await ws.send(
        json.dumps(
            {
                "action": "send",
                "conversation_id": conversation_id,
                "receiver_id": RECEIVER_ID,
                "client_msg_id": cmid,
                "content": content,
                "content_type": content_type,
            }
        )
    )
    raw = await asyncio.wait_for(ws.recv(), timeout=10)
    return json.loads(raw)


def wait_for(counter: dict, height: int, timeout: float = 40.0) -> int:
    """轮询数据库直到某消息 seq 落库，返回最终落库条数。

    每轮新建 session 避免事务隔离导致的旧数据快照。

    Args:
        counter: {"conversation_id": cid} 查询上下文。
        height: 期望达到的最小落库条数。
        timeout: 超时秒数。

    Returns:
        实际落库条数。
    """
    deadline = time.time() + timeout
    count = 0
    while time.time() < deadline:
        db = SyncSessionLocal()
        try:
            count = db.execute(
                text("SELECT COUNT(*) FROM dm_message WHERE conversation_id=:c"),
                {"c": counter["conversation_id"]},
            ).scalar_one()
        finally:
            db.close()
        if count >= height:
            return count
        time.sleep(0.5)
    return count


def cleanup(conversation_id: int) -> None:
    """清理本次E2E测试数据（dm 表行 + Redis键）。"""
    db = SyncSessionLocal()
    try:
        db.execute(text("DELETE FROM dm_message WHERE conversation_id=:c"), {"c": conversation_id})
        db.execute(text("DELETE FROM dm_conversation WHERE id=:c"), {"c": conversation_id})
        db.commit()
    finally:
        db.close()

    r = redis_client()
    for conv in (str(conversation_id),):
        for key in (
            f"stream:conv:{conv}",
            f"chat:cmid:{conv}",
            f"chat:seq:{conv}",
        ):
            r.delete(key)
    r.srem("chat:convs:flush", str(conversation_id))
    r.delete(f"unread:{RECEIVER_ID}")
    # 清理 outbox 事件（chat.message.sent）
    db = SyncSessionLocal()
    try:
        db.execute(
            text("DELETE FROM outbox_event WHERE event_type='chat.message.sent' AND aggregate_id=:c"),
            {"c": str(conversation_id)},
        )
        db.commit()
    finally:
        db.close()
    print(f"[CLEANUP] 测试数据已清理: conversation_id={conversation_id}")


async def run_ws_flow() -> None:
    """执行 WS 相关 E2E 断言（异步）。"""
    conversation_id = setup_conversation()
    token = make_token(SENDER_ID)
    r = redis_client()
    try:
        # ---- 1. 未认证连接 → 4001（websockets 会抛连接拒绝异常） ----
        ws_unauthed, ok = await connect_ws("invalid-token")
        if ok:
            await ws_unauthed.close()
            check("未认证连接被拒绝", False, "连接成功未拒绝")
        else:
            check("未认证连接被拒绝(4001)", True)

        # ---- 2. 认证连接 + 发送 ----
        ws, ok = await connect_ws(token)
        check("认证WS连接成功", ok)
        if not ok:
            return

        cmid1 = random_cmid()
        ack1 = await send_message(ws, conversation_id, cmid1, "你好，第一条私信")
        check("发送回执sent", ack1.get("action") == "sent", str(ack1))
        check("回执seq=1", ack1.get("seq") == 1, str(ack1))
        check("回执conversation_id", ack1.get("conversation_id") == conversation_id, str(ack1))

        # ---- 3. 写缓冲已落 Redis Stream + 活跃会话登记 ----
        stream_len = r.xlen(f"stream:conv:{conversation_id}")
        check("Stream已写入消息", stream_len >= 1, f"len={stream_len}")
        check("活跃会话已登记", r.sismember("chat:convs:flush", str(conversation_id)))

        # ---- 4. 幂等：重复发送同 client_msg_id → duplicate ----
        ack_dup = await send_message(ws, conversation_id, cmid1, "重复发送")
        check("重复发送回执duplicate", ack_dup.get("action") == "duplicate", str(ack_dup))
        check("重复回执seq不变", ack_dup.get("seq") == 1, str(ack_dup))
        dup_count = r.xlen(f"stream:conv:{conversation_id}")
        check("重复未重复写Stream", dup_count == stream_len, f"before={stream_len} after={dup_count}")

        # ---- 5. 保序：连发2条 seq=2,3 ----
        cmid2 = random_cmid()
        cmid3 = random_cmid()
        ack2 = await send_message(ws, conversation_id, cmid2, "第二条")
        ack3 = await send_message(ws, conversation_id, cmid3, "第三条")
        check("第二条seq=2", ack2.get("seq") == 2, str(ack2))
        check("第三条seq=3", ack3.get("seq") == 3, str(ack3))

        await ws.close()

        # ---- 6. flush Worker 落库（轮询等待3条） ----
        db_count = wait_for({"conversation_id": conversation_id}, 3, timeout=20)
        check("3条消息落库dm_message", db_count == 3, f"count={db_count}")

        if db_count == 3:
            db = SyncSessionLocal()
            try:
                rows = db.execute(
                    text(
                        "SELECT client_msg_id, seq, receiver_id, content_type FROM dm_message "
                        "WHERE conversation_id=:c ORDER BY seq"
                    ),
                    {"c": conversation_id},
                ).fetchall()
                check("落库seq保序递增", [r[1] for r in rows] == [1, 2, 3], str([r[1] for r in rows]))
                check("落库receiver_id正确", all(r[2] == RECEIVER_ID for r in rows))
                check("落库content_type默认1", all(r[3] == 1 for r in rows))
                cmids = [r[0] for r in rows]
                check("唯一幂等键落库", sorted(cmids) == sorted([cmid1, cmid2, cmid3]))

                conv = db.execute(
                    text("SELECT last_message, last_message_id, last_message_at FROM dm_conversation WHERE id=:c"),
                    {"c": conversation_id},
                ).fetchone()
                check("会话最后消息摘要更新", conv[0] == "第三条", repr(conv[0]))
                check("会话last_message_id回填", conv[1] is not None and conv[1] > 0, str(conv[1]))
                check("会话last_message_at更新", conv[2] is not None)
            finally:
                db.close()

        # ---- 7. Outbox 事件已写 + relay 投递 + 扇出未读数 ----
        db = SyncSessionLocal()
        outbox_events = []
        timeout_ev = time.time() + 15
        while time.time() < timeout_ev:
            db.expire_all()
            outbox_events = db.execute(
                text(
                    "SELECT id, payload, status FROM outbox_event "
                    "WHERE event_type='chat.message.sent' AND aggregate_id=:c ORDER BY id"
                ),
                {"c": str(conversation_id)},
            ).fetchall()
            if not outbox_events or outbox_events[0][2] != 1:
                time.sleep(0.5)
                continue
            break
        check("Outbox事件已写入", len(outbox_events) == 3, f"count={len(outbox_events)}")
        if outbox_events:
            check("Outbox事件已投递(status=1)", outbox_events[0][2] == 1, f"status={outbox_events[0][2]}")
            payload = json.loads(outbox_events[0][1]) if isinstance(outbox_events[0][1], str) else outbox_events[0][1]
            check("Outbox含receiver_id", payload.get("receiver_id") == RECEIVER_ID, str(payload))
        else:
            check("Outbox事件已写入", False, "未查到chat.message.sent事件")
        db.close()

        # ---- 8. 未读数归集：扇出后 unread:{receiver} 应为会话未读数 ----
        unread_val = None
        timeout_un = time.time() + 10
        while time.time() < timeout_un:
            unread_val = r.hget(f"unread:{RECEIVER_ID}", str(conversation_id))
            if unread_val:
                break
            time.sleep(0.5)
        check("扇出未读数HINCRBY", int(unread_val or 0) == 3, f"unread={unread_val}")

    finally:
        cleanup(conversation_id)


def main() -> None:
    """执行私信 M1/M2 E2E 主流程。"""
    print("=== 私信 M1/M2 E2E 测试 ===")
    try:
        asyncio.run(run_ws_flow())
    except Exception as exc:
        check("E2E流程异常", False, f"{type(exc).__name__}: {exc}")

    print("\n========== 结果汇总 ==========")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    for name, detail in FAIL:
        print(f"  FAILED: {name} -> {detail[:200]}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()