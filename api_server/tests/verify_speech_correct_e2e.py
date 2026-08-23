"""E2E 验证：新建正式面试，提交一条真实乱码 ASR 回答，确认落库的 user_answer 是纠错后文本。
运行方式：在 api_server 目录执行 D:\\conda\\envs\\interview\\python.exe tests/verify_speech_correct_e2e.py
"""
import json
import os
import sys
import time

# 保证以 project 根为包根导入 app（脚本位于 tests/ 子目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jwt
import requests
from sqlalchemy import text

from app.db.sync_session import SyncSessionLocal

# ---- 配置（与服务端一致） ----
BASE = "http://127.0.0.1:8000/api/v1"
SECRET_KEY = "change-me-in-production"
USER_ID = 22  # 用面试记录里的用户，避免新建账号
INTERVIEW_TYPE = 2  # 快速面试（题少、耗时短）

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    """记录单条断言结果。"""
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        FAIL.append((name, detail))
        print(f"  [FAIL] {name} -> {detail}")


def make_token(user_id: int) -> str:
    """生成与服务端一致的 JWT（HS256，sub 为字符串用户ID）。"""
    return jwt.encode({"sub": str(user_id), "login": "verify"}, SECRET_KEY, algorithm="HS256")


def session_for(user_id: int) -> requests.Session:
    """创建携带 access_token Cookie 的会话。"""
    s = requests.Session()
    s.cookies.set("access_token", make_token(user_id))
    return s


def prepare_ready_resume() -> int:
    """落库一份已就绪简历（含解析结果），返回 resume_id。"""
    db = SyncSessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO resume (user_id, file_name, status, parsed_name, parsed_skills, "
                "parsed_education, parsed_projects, is_deleted) VALUES "
                "(:uid, 'verify_speech.pdf', 1, :name, :skills, :edu, :projects, 0)"
            ),
            {
                "uid": USER_ID,
                "name": "验证候选人",
                "skills": json.dumps(["Python", "FastAPI", "MySQL", "Redis", "RabbitMQ"]),
                "edu": json.dumps([{"school": "测试大学", "degree": "本科", "major": "计算机科学", "duration": "2018-2022"}]),
                "projects": json.dumps([
                    {"name": "AI面试平台", "description": "面试会话模块", "tech_stack": ["FastAPI", "Redis"]},
                ]),
            },
        )
        db.commit()
        resume_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
        return resume_id
    finally:
        db.close()


def cleanup(resume_id: int, interview_id: int | None) -> None:
    """清理验证数据（DB行）。"""
    db = SyncSessionLocal()
    try:
        if interview_id is not None:
            db.execute(text("DELETE FROM interview_question WHERE interview_id=:i"), {"i": interview_id})
            db.execute(text("DELETE FROM interview_report WHERE interview_id=:i"), {"i": interview_id})
            db.execute(text("DELETE FROM interview WHERE id=:i"), {"i": interview_id})
        if resume_id is not None:
            db.execute(text("DELETE FROM resume WHERE id=:r"), {"r": resume_id})
        db.commit()
    finally:
        db.close()


def main() -> None:
    """执行验证主流程：新建面试 → 提交乱码回答 → 校验落库纠错文本。"""
    s = session_for(USER_ID)
    resume_id: int | None = None
    interview_id: int | None = None
    try:
        resp = s.get("http://127.0.0.1:8000/health", timeout=5)
        check("服务健康检查", resp.status_code == 200)

        # ---- 创建面试（真实 LLM 出题） ----
        resume_id = prepare_ready_resume()
        t0 = time.time()
        resp = s.post(
            f"{BASE}/interviews",
            json={"resume_id": resume_id, "type": INTERVIEW_TYPE, "tab_id": "tab-V"},
            timeout=180,
        )
        elapsed = time.time() - t0
        check("创建面试201", resp.status_code == 201, resp.text)
        if resp.status_code != 201:
            return
        created = resp.json()
        interview_id = created["interview_id"]
        print(f"  [INFO] 出题耗时 {elapsed:.1f}s 面试id={interview_id}")
        check("返回首题", created["current_question"] is not None)

        # ---- 提交一条真实乱码 ASR 回答 ----
        q = created["current_question"]
        raw = "必包的话简单来说就是寒暑假吃法中忧郁函数能够寄出病访问在定义他蛇的环境变量其实必报最主要的实现是因为"
        resp = s.post(
            f"{BASE}/interviews/{interview_id}/answers",
            json={"question_index": q["question_index"], "answer": raw, "tab_epoch": created["epoch"], "duration": 40},
            timeout=300,
        )
        check("提交回答200", resp.status_code == 200, resp.text)

        # ---- 查库确认落库文本 ----
        db = SyncSessionLocal()
        stored = db.execute(
            text("SELECT user_answer FROM interview_question WHERE interview_id=:i ORDER BY id LIMIT 1"),
            {"i": interview_id},
        ).scalar()
        db.close()
        print(f"\n  [DB] RAW  : {raw}")
        print(f"  [DB] USER_ANSWER : {stored}")

        changed = stored is not None and stored != raw
        check("落库为纠错后文本(≠原文)", bool(changed), f"stored={stored!r}")
        check("关键术语已纠正(含'闭包')", stored is not None and "闭包" in stored, stored or "")
        check("raw垃圾残留已减少", stored is not None and "必包" not in stored, stored or "")

    finally:
        cleanup(resume_id, interview_id)
        print("\n===== 结果 =====")
        print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
        for name, detail in FAIL:
            print(f"  FAIL {name}: {detail}")


if __name__ == "__main__":
    main()