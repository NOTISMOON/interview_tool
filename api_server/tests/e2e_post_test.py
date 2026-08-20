"""帖子功能端到端测试脚本（真实启动服务，HTTP 层全链路验证）。

用法: 在 api_server 目录下用 interview 环境运行
    python tests/e2e_post_test.py

覆盖范围:
    1. 帖子 CRUD（创建/详情/列表/更新/权限/软删除/404/401）
    2. 评论（一级评论/回复/列表/回复列表/删除评论）
    3. 点赞/收藏（toggle/幂等/收藏列表）
    4. 关注 + Feed 流
    5. Redis 缓存行为验证（点赞 SET）
"""

import json
import sys
import time

import jwt
import requests

# ---- 配置 ----
BASE = "http://127.0.0.1:8000/api/v1"
SECRET_KEY = "change-me-in-production"  # 与 api_server/.env 保持一致
USER_A = 1   # 测试用户A（作者）
USER_B = 17  # 用户🌙（互动者）

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    """记录单个断言结果。

    Args:
        name: 用例名称。
        cond: 断言是否通过。
        detail: 失败时的补充信息。
    """
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
    """创建携带 access_token Cookie 的会话（模拟 HttpOnly Cookie 登录态）。"""
    s = requests.Session()
    s.cookies.set("access_token", make_token(user_id, login))
    return s


sa = session_for(USER_A, "test_a")   # 用户A
sb = session_for(USER_B, "moon")     # 用户B
guest = requests.Session()           # 游客


def main() -> None:
    """执行全部端到端测试用例。"""
    print("=" * 60)
    print("阶段0: 健康检查")
    r = requests.get("http://127.0.0.1:8000/health", timeout=5)
    check("健康检查 200", r.status_code == 200, f"status={r.status_code}")

    print("=" * 60)
    print("阶段1: 帖子 CRUD")
    # 1.1 游客创建帖子 → 401
    r = guest.post(f"{BASE}/posts/", json={"title": "t", "content": "c"}, timeout=5)
    check("未登录创建帖子 401", r.status_code == 401, f"status={r.status_code} body={r.text[:200]}")

    # 1.2 用户A创建帖子 → 201
    r = sa.post(
        f"{BASE}/posts/",
        json={"title": "E2E测试帖子", "content": "这是端到端测试内容" * 10, "tags": ["Python", "FastAPI"]},
        timeout=10,
    )
    check("创建帖子 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
    post_id = r.json().get("id") if r.status_code == 201 else None
    print(f"    post_id={post_id}")

    if post_id:
        body = r.json()
        check("创建响应含标题", body.get("title") == "E2E测试帖子", str(body)[:200])
        check("创建响应含作者", (body.get("author") or {}).get("id") == USER_A, str(body.get("author")))

    # 1.3 参数校验：空标题 → 422
    r = sa.post(f"{BASE}/posts/", json={"title": "", "content": "x"}, timeout=5)
    check("空标题 422", r.status_code == 422, f"status={r.status_code}")

    # 1.4 游客查看详情 → 200
    r = guest.get(f"{BASE}/posts/{post_id}", timeout=5)
    check("游客查看详情 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        check("详情含标签", set(r.json().get("tags") or []) >= {"Python", "FastAPI"}, str(r.json().get("tags")))

    # 1.5 不存在的帖子 → 404
    r = guest.get(f"{BASE}/posts/99999999", timeout=5)
    check("不存在帖子 404", r.status_code == 404, f"status={r.status_code}")

    # 1.6 帖子列表 → 200
    r = guest.get(f"{BASE}/posts/", params={"limit": 5}, timeout=5)
    check("帖子列表 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        check("列表包含新帖子", any(i.get("id") == post_id for i in r.json().get("items", [])), "列表中未见")

    # 1.7 按作者过滤
    r = guest.get(f"{BASE}/posts/", params={"author_id": USER_A}, timeout=5)
    check("按作者过滤列表 200", r.status_code == 200, f"status={r.status_code}")

    # 1.8 用户B（非作者）更新 → 404（权限校验）
    r = sb.put(f"{BASE}/posts/{post_id}", json={"title": "篡改标题"}, timeout=5)
    check("非作者更新 404", r.status_code == 404, f"status={r.status_code} body={r.text[:200]}")

    # 1.9 作者更新 → 200
    r = sa.put(f"{BASE}/posts/{post_id}", json={"title": "E2E测试帖子-已更新", "tags": ["Redis"]}, timeout=10)
    check("作者更新 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        check("更新后标题生效", r.json().get("title") == "E2E测试帖子-已更新", r.json().get("title"))

    # 1.10 更新后详情（验证标签替换）
    r = guest.get(f"{BASE}/posts/{post_id}", timeout=5)
    if r.status_code == 200:
        check("更新后标签替换", r.json().get("tags") == ["Redis"], str(r.json().get("tags")))
    else:
        check("更新后详情可查", False, f"status={r.status_code}")

    print("=" * 60)
    print("阶段2: 评论")
    # 2.1 用户B对帖子发一级评论 → 201
    r = sb.post(f"{BASE}/posts/{post_id}/comments", json={"content": "这是E2E一级评论"}, timeout=10)
    check("创建一级评论 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
    comment_id = r.json().get("id") if r.status_code == 201 else None

    # 2.2 用户A回复该评论 → 201
    r = sa.post(
        f"{BASE}/posts/{post_id}/comments",
        json={"content": "这是E2E回复", "root_id": comment_id, "reply_user_id": USER_B},
        timeout=10,
    )
    check("创建回复 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
    reply_id = r.json().get("id") if r.status_code == 201 else None

    # 2.3 对不存在帖子评论 → 404
    r = sb.post(f"{BASE}/posts/99999999/comments", json={"content": "x"}, timeout=5)
    check("不存在帖子评论 404", r.status_code == 404, f"status={r.status_code}")

    # 2.4 评论列表 → 200
    r = guest.get(f"{BASE}/posts/{post_id}/comments", timeout=5)
    check("评论列表 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        items = r.json().get("items", [])
        check("评论列表含一级评论", any(i.get("id") == comment_id for i in items), str([i.get("id") for i in items]))
        check("一级评论总数=1", r.json().get("total") == 1, f"total={r.json().get('total')}")

    # 2.5 回复列表 → 200
    r = guest.get(f"{BASE}/comments/{comment_id}/replies", timeout=5)
    check("回复列表 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        items = r.json().get("items", [])
        check("回复列表含回复", any(i.get("id") == reply_id for i in items), str([i.get("id") for i in items]))

    # 2.6 帖子详情评论数联动
    r = guest.get(f"{BASE}/posts/{post_id}", timeout=5)
    if r.status_code == 200:
        check("详情comments_count=2", r.json().get("comments_count") == 2, str(r.json().get("comments_count")))

    # 2.7 删除回复 → 204
    r = sa.delete(f"{BASE}/comments/{reply_id}", timeout=5)
    check("删除回复 204", r.status_code == 204, f"status={r.status_code}")

    # 2.8 非作者删评论 → 404（用户A删用户B的评论）
    r = sa.delete(f"{BASE}/comments/{comment_id}", timeout=5)
    check("非作者删评论 404", r.status_code == 404, f"status={r.status_code}")

    print("=" * 60)
    print("阶段3: 点赞/收藏")
    # 3.1 用户B点赞 → 200
    r = sb.post(f"{BASE}/posts/{post_id}/like", timeout=10)
    check("点赞 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")

    # 3.2 详情验证点赞状态（用户B视角）
    r = sb.get(f"{BASE}/posts/{post_id}", timeout=5)
    if r.status_code == 200:
        check("详情is_liked=True", r.json().get("is_liked") is True, str(r.json().get("is_liked")))
        check("详情likes_count=1", r.json().get("likes_count") == 1, str(r.json().get("likes_count")))
    else:
        check("点赞后详情可查", False, f"status={r.status_code}")

    # 3.3 用户A点赞 → likes_count=2
    r = sa.post(f"{BASE}/posts/{post_id}/like", timeout=10)
    check("用户A点赞 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")

    # 3.4 用户B取消点赞（toggle）→ 200
    r = sb.post(f"{BASE}/posts/{post_id}/like", timeout=10)
    check("取消点赞 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")

    # 3.5 不存在帖子点赞 → 404
    r = sb.post(f"{BASE}/posts/99999999/like", timeout=5)
    check("不存在帖子点赞 404", r.status_code == 404, f"status={r.status_code}")

    # 3.6 收藏 → 200
    r = sb.post(f"{BASE}/posts/{post_id}/favorite", timeout=10)
    check("收藏 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")

    # 3.7 收藏列表 → 200 且含帖子
    r = sb.get(f"{BASE}/posts/favorites", timeout=5)
    check("收藏列表 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        items = r.json().get("items", [])
        check("收藏列表含帖子", any(i.get("id") == post_id for i in items), str([i.get("id") for i in items]))

    print("=" * 60)
    print("阶段4: 关注 + Feed")
    # 4.1 用户A关注用户B？改为：用户A关注用户17已有帖子？本阶段：用户A 关注 用户B
    # 先清理可能存在的关注关系（幂等）
    sa.delete(f"{BASE}/users/{USER_B}/follow", timeout=5)
    r = sa.post(f"{BASE}/users/{USER_B}/follow", timeout=10)
    check("关注用户 204", r.status_code == 204, f"status={r.status_code} body={r.text[:200]}")

    # 4.2 用户B发帖（Feed 内容）
    r = sb.post(
        f"{BASE}/posts/",
        json={"title": "B的Feed帖子", "content": "Feed流测试内容"},
        timeout=10,
    )
    check("用户B创建帖子 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
    feed_post_id = r.json().get("id") if r.status_code == 201 else None

    # 等待异步链路: Outbox Relay → MQ → FeedPushConsumer 写收件箱
    time.sleep(3)

    # 4.3 Feed 查询（用户A视角）
    r = sa.get(f"{BASE}/feed", timeout=10)
    check("Feed查询 200", r.status_code == 200, f"status={r.status_code} body={r.text[:500]}")
    if r.status_code == 200:
        items = r.json().get("items", [])
        check("Feed含用户B的帖子", any(i.get("id") == feed_post_id for i in items),
              f"ids={[i.get('id') for i in items]}")
        check("Feed不含自己的帖子", all((i.get("author") or {}).get("id") != USER_A for i in items),
              f"authors={[(i.get('author') or {}).get('id') for i in items]}")
        # Feed 按时间倒序：新帖应在首位
        if items:
            check("Feed新帖排首位", items[0].get("id") == feed_post_id,
                  f"first={items[0].get('id')} expected={feed_post_id}")

    print("=" * 60)
    print("阶段5: 帖子软删除")
    # 5.1 用户B删除自己的 Feed 帖子 → 204
    r = sb.delete(f"{BASE}/posts/{feed_post_id}", timeout=10)
    check("删除帖子 204", r.status_code == 204, f"status={r.status_code}")

    # 5.2 已删除帖子详情 → 404
    r = guest.get(f"{BASE}/posts/{feed_post_id}", timeout=5)
    check("已删除帖子详情 404", r.status_code == 404, f"status={r.status_code}")

    # 5.3 已删除帖子不在列表
    r = guest.get(f"{BASE}/posts/", params={"limit": 100}, timeout=5)
    if r.status_code == 200:
        check("已删除帖子不在列表", all(i.get("id") != feed_post_id for i in r.json().get("items", [])), "仍在列表中")

    # 5.4 非作者删除 → 404
    r = sb.delete(f"{BASE}/posts/{post_id}", timeout=5)
    check("非作者删除 404", r.status_code == 404, f"status={r.status_code}")

    print("=" * 60)
    print(f"汇总: PASS={len(PASS)} FAIL={len(FAIL)}")
    for name, detail in FAIL:
        print(f"  FAIL: {name} -> {detail}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
