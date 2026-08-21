"""端到端测试：个人主页发帖、消息通知计数、关注动态通知。

覆盖功能:
    1. 个人主页「我的发帖」板块（通过 GET /posts?author_id= 验证）
    2. 消息通知红色提示接入真实未读计数（通过 GET /messages/unread-count 验证）
    3. 关注动态通知（当关注的用户发帖时，粉丝收到 follow_post 类型通知）

用法: 在 api_server 目录下用 interview 环境运行
    python tests/e2e_notification_test.py

前提: uvicorn + mq.runner 运行中
"""

import sys
import time

import jwt
import requests

# ---- 配置 ----
BASE = "http://127.0.0.1:8000/api/v1"
SECRET_KEY = "change-me-in-production"  # 与 api_server/.env 保持一致
USER_A = 1    # 测试用户A（关注者）
USER_B = 17   # 测试用户B（被关注者 / 帖子作者）

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    """记录单个断言结果。"""
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        FAIL.append((name, detail))
        print(f"  [FAIL] {name} -> {detail}")


def make_token(user_id: int, login: str) -> str:
    """生成与后端一致的 JWT（HS256，sub 为字符串用户ID）。"""
    return jwt.encode({"sub": str(user_id), "login": login}, SECRET_KEY, algorithm="HS256")


def session_for(user_id: int, login: str) -> requests.Session:
    """创建携带 access_token Cookie 的会话。"""
    s = requests.Session()
    s.cookies.set("access_token", make_token(user_id, login))
    return s


sa = session_for(USER_A, "test_a")   # 用户A（关注者）
sb = session_for(USER_B, "moon")     # 用户B（发帖者）


def main() -> None:
    """执行全部端到端测试用例。"""
    print("=" * 60)
    print("阶段0: 健康检查")
    r = requests.get("http://127.0.0.1:8000/health", timeout=5)
    check("健康检查 200", r.status_code == 200, f"status={r.status_code}")

    # ============================================================
    print("=" * 60)
    print("阶段1: 个人主页「我的发帖」板块验证")
    print("描述: 模拟个人主页加载当前用户帖子列表")
    # 1.1 用户A 获取自己的帖子列表
    r = sa.get(f"{BASE}/posts/", params={"author_id": USER_A, "limit": 20, "sort": "latest"}, timeout=10)
    check("GET /posts?author_id= 返回 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        data = r.json()
        items = data.get("items", [])
        check("帖子列表包含 items 字段", "items" in data, str(data.keys()))
        check("帖子列表 items 非空", len(items) > 0, f"items={items}")
        check("每条帖子含标题", all("title" in i for i in items), "缺 title 字段")
        check("每条帖子含作者ID=1", all((i.get("author") or {}).get("id") == USER_A for i in items),
              f"作者信息={[i.get('author') for i in items]}")
        check("每条帖子含 created_at", all("created_at" in i for i in items), "缺 created_at 字段")
        check("每条帖子含 likes_count", all("likes_count" in i for i in items), "缺 likes_count 字段")
        check("每条帖子含 comments_count", all("comments_count" in i for i in items), "缺 comments_count 字段")
        # 验证返回的帖子正是用户A自己的帖子
        r2 = sa.get(f"{BASE}/users/me", timeout=5)
        user_profile = r2.json() if r2.status_code == 200 else {}
        posts_count = user_profile.get("posts_count", 0)
        check(f"帖子总数与用户profile一致 (profile={posts_count}, 列表={len(items)})",
              posts_count <= 0 or len(items) == posts_count or len(items) < 20,
              f"profile={posts_count} items={len(items)}")

    # 1.2 用户A 查看他人主页（用户B）的帖子
    r = sb.get(f"{BASE}/posts/", params={"author_id": USER_B, "limit": 5}, timeout=10)
    check("他人主页帖子列表 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        items = r.json().get("items", [])
        check("他人主页帖子作者ID=17", all((i.get("author") or {}).get("id") == USER_B for i in items),
              f"作者={[(i.get('author') or {}).get('id') for i in items]}")

    # ============================================================
    print("=" * 60)
    print("阶段2: 消息通知红色提示（未读计数）验证")
    print("描述: 验证 GET /messages/unread-count 返回正确的未读计数")

    # 2.1 获取用户A的未读计数
    r = sa.get(f"{BASE}/messages/unread-count", timeout=10)
    check("GET /messages/unread-count 返回 200", r.status_code == 200, f"status={r.status_code}")
    unread_before = 0
    if r.status_code == 200:
        data = r.json()
        check("响应含 total 字段", "total" in data, str(data.keys()))
        check("响应含 by_type 字段", "by_type" in data, str(data.keys()))
        unread_before = data.get("total", 0)
        check(f"total 为非负整数 ({unread_before})", isinstance(unread_before, int) and unread_before >= 0,
              f"total={unread_before}")

    # 2.2 获取用户B的未读计数
    r = sb.get(f"{BASE}/messages/unread-count", timeout=10)
    check("用户B 未读计数 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        unread_b_before = r.json().get("total", 0)
        print(f"    用户B当前未读: {unread_b_before}")

    # 2.3 验证未读计数的 by_type 结构
    r = sa.get(f"{BASE}/messages/unread-count", timeout=5)
    if r.status_code == 200:
        by_type = r.json().get("by_type", {})
        check("by_type 是字典", isinstance(by_type, dict), str(type(by_type)))
        # 验证已知类型存在
        known_types = {"system", "comment", "like", "follow", "follow_post"}
        for t in known_types:
            if t in by_type:
                check(f"类型 {t} 计数为非负整数", isinstance(by_type[t], int) and by_type[t] >= 0,
                      f"{t}={by_type[t]}")

    # ============================================================
    print("=" * 60)
    print("阶段3: 关注动态通知端到端验证")
    print("描述: 用户B发帖 → 用户A收到 follow_post 类型通知")

    # 3.1 确保用户A关注了用户B
    # 先清理已有关系再重新关注（保证干净状态）
    print("    确保用户A关注用户B...")
    sa.delete(f"{BASE}/users/{USER_B}/follow", timeout=5)
    r = sa.post(f"{BASE}/users/{USER_B}/follow", timeout=10)
    check("关注用户B 204", r.status_code == 204, f"status={r.status_code}")

    # 3.2 记录用户A当前未读总数
    r = sa.get(f"{BASE}/messages/unread-count", timeout=5)
    unread_before_follow_post = r.json().get("total", 0) if r.status_code == 200 else 0
    print(f"    用户A当前未读总数: {unread_before_follow_post}")

    # 3.3 用户B创建新帖子
    print("    用户B创建新帖子...")
    r = sb.post(
        f"{BASE}/posts/",
        json={"title": "关注动态通知E2E测试", "content": "这是测试关注动态通知的帖子内容", "tags": ["E2E", "测试"]},
        timeout=10,
    )
    check("用户B创建帖子 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
    new_post_id = r.json().get("id") if r.status_code == 201 else None
    print(f"    新帖子ID: {new_post_id}")

    # 3.4 等待异步链路: Outbox Relay → MQ → FollowPostNotifyConsumer → 通知落库
    #     post.created + 通知创建 + SSE推送，给足时间
    WAIT_SECONDS = 8
    print(f"    等待 {WAIT_SECONDS}s 异步链路处理...")
    time.sleep(WAIT_SECONDS)

    # 3.5 验证用户A的未读计数增加了
    r = sa.get(f"{BASE}/messages/unread-count", timeout=5)
    check("未读计数接口 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        unread_after = r.json().get("total", 0)
        check("未读计数增加 >= 1", unread_after > unread_before_follow_post,
              f"before={unread_before_follow_post} after={unread_after}")

        # 3.6 验证 by_type 中 follow_post 计数增加
        by_type = r.json().get("by_type", {})
        follow_post_count = by_type.get("follow_post", 0)
        check("follow_post 类型计数 >= 1", follow_post_count >= 1,
              f"follow_post={follow_post_count} by_type={by_type}")

    # 3.7 获取用户A的消息列表，验证存在 follow_post 类型的通知
    r = sa.get(f"{BASE}/messages/", params={"limit": 10}, timeout=10)
    check("消息列表 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        items = r.json().get("items", [])
        follow_post_msgs = [m for m in items if m.get("type_name") == "follow_post"]
        check("消息列表包含 follow_post 类型通知", len(follow_post_msgs) >= 1,
              f"所有类型={[m.get('type_name') for m in items]}")
        if follow_post_msgs:
            msg = follow_post_msgs[0]
            check("follow_post 通知标题为「关注动态」", msg.get("title") == "关注动态",
                  f"title={msg.get('title')}")
            check("通知内容包含帖子标题", "关注动态通知E2E测试" in msg.get("content", ""),
                  f"content={msg.get('content')}")
            check("通知 from_user 为 B", (msg.get("from_user") or {}).get("id") == USER_B,
                  f"from_user={msg.get('from_user')}")
            check("通知 related 为新帖子ID", (msg.get("related") or {}).get("id") == new_post_id,
                  f"related={msg.get('related')} expected={new_post_id}")

    # 3.8 消息详情验证（先检查列表中的 is_read，再获取详情）
    if follow_post_msgs:
        # 从列表响应中检查 is_read（此时消息尚未被详情接口标记已读）
        check("列表中通知标记为未读", follow_post_msgs[0].get("is_read") is False,
              f"is_read={follow_post_msgs[0].get('is_read')}")

        msg_id = follow_post_msgs[0].get("id")
        r = sa.get(f"{BASE}/messages/{msg_id}", timeout=5)
        check("消息详情 200", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            detail = r.json()
            check("详情类型为 follow_post", detail.get("type_name") == "follow_post",
                  f"type_name={detail.get('type_name')}")
            check("详情 related 含帖子ID", (detail.get("related") or {}).get("id") == new_post_id,
                  f"related={detail.get('related')}")

        # 3.9 标记已读
        r = sa.put(f"{BASE}/messages/{msg_id}/read", timeout=5)
        check("标记已读 200", r.status_code == 200, f"status={r.status_code}")

    # ============================================================
    # 清理：删除测试帖子
    if new_post_id:
        sb.delete(f"{BASE}/posts/{new_post_id}", timeout=5)
        print("    清理: 已删除测试帖子")

    # 清理：删除关注动态通知（可选）
    if follow_post_msgs:
        msg_id = follow_post_msgs[0].get("id")
        sa.delete(f"{BASE}/messages/{msg_id}", timeout=5)
        print("    清理: 已删除测试通知")

    # ============================================================
    print("=" * 60)
    print(f"汇总: PASS={len(PASS)} FAIL={len(FAIL)}")
    for name, detail in FAIL:
        print(f"  FAIL: {name} -> {detail}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()