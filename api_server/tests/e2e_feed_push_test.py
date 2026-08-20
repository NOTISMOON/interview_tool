"""Feed Push链路专项验证脚本。

验证点:
    1. 用户B发帖后，FeedPushConsumer 将帖子写入关注者(用户A)的收件箱 feed:inbox:user:{A}
    2. 用户A查询Feed时，缓存命中路径正确合并收件箱新帖并清空收件箱
    3. 新帖出现在Feed首位（按时间倒序）
"""

import sys
import time

import jwt
import requests

BASE = "http://127.0.0.1:8000/api/v1"
SECRET_KEY = "change-me-in-production"
USER_A = 1
USER_B = 17

sys.path.insert(0, ".")
from app.redis.sync_client import SyncRedisClient  # noqa: E402


def make_token(user_id: int, login: str) -> str:
    """生成测试JWT。"""
    return jwt.encode({"sub": str(user_id), "login": login}, SECRET_KEY, algorithm="HS256")


def main() -> None:
    """执行Push链路验证。"""
    ok = True
    sa = requests.Session()
    sa.cookies.set("access_token", make_token(USER_A, "test_a"))
    sb = requests.Session()
    sb.cookies.set("access_token", make_token(USER_B, "moon"))

    r = sb.post(
        f"{BASE}/posts/",
        json={"title": "Push链路验证帖", "content": "验证FeedPushConsumer收件箱写入"},
        timeout=10,
    )
    assert r.status_code == 201, f"发帖失败: {r.status_code} {r.text[:200]}"
    new_post_id = r.json()["id"]
    print(f"[1] 用户B发帖成功 post_id={new_post_id}")

    # 等待 Outbox Relay → MQ → FeedPushConsumer
    time.sleep(4)

    c = SyncRedisClient.get_client()
    inbox = c.zrevrange(f"feed:inbox:user:{USER_A}", 0, -1, withscores=True)
    print(f"[2] 用户A收件箱内容: {inbox}")
    if not any(int(m) == new_post_id for m, _ in inbox):
        print("  [FAIL] 收件箱未见新帖，Push未生效")
        ok = False
    else:
        print("  [PASS] 收件箱已收到新帖（Push生效）")

    # 用户A查Feed：feed:user:1 已存在（上轮缓存），验证命中路径合并inbox
    r = sa.get(f"{BASE}/feed", timeout=10)
    assert r.status_code == 200, f"Feed查询失败: {r.status_code}"
    items = r.json().get("items", [])
    ids = [i.get("id") for i in items]
    print(f"[3] Feed返回: {ids}")
    if new_post_id in ids:
        print("  [PASS] Feed含新帖（缓存命中路径合并inbox生效）")
    else:
        print("  [FAIL] Feed未见新帖")
        ok = False
    if ids and ids[0] == new_post_id:
        print("  [PASS] 新帖排Feed首位（时间倒序正确）")
    else:
        print(f"  [FAIL] 新帖未排首位: first={ids[0] if ids else None}")
        ok = False

    inbox_after = c.zrevrange(f"feed:inbox:user:{USER_A}", 0, -1, withscores=True)
    print(f"[4] 合并后收件箱: {inbox_after}")
    if not inbox_after:
        print("  [PASS] 收件箱已清空（避免重复合并）")
    else:
        print("  [FAIL] 收件箱未清空")
        ok = False

    # 清理验证帖
    sb.delete(f"{BASE}/posts/{new_post_id}", timeout=10)
    print(f"[5] 清理验证帖 post_id={new_post_id}")

    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
