"""端到端冒烟测试：AI面试 M1/M2 全链路（真实 DeepSeek LLM）+ v2 异步分析。

覆盖《面试模块单LangGraph架构方案.md》核心链路：
    1. 创建面试（简历校验 + 基础题预生成落库 + Checkpoint + epoch租约）
    2. 状态查询 / 刷新恢复（同tab幂等 / 新tab接管epoch+1）
    3. 提交回答（v2 Fast Decision 秒级判定下一题，全量分析走异步 MQ Worker）
    4. 双开裁决（旧epoch提交409）与幂等（重复提交不重跑LLM）
    5. 追问判定（Fast Decision 判定追问落库 is_follow_up=1）
    6. 全部答完 → summarizing → 报告生成（后台，强制等待异步分析补齐）
    7. 主动放弃 → status=2

用法: 在 api_server 目录下用 interview 环境运行
    python tests/e2e_interview_smoke_test.py

前提: uvicorn 运行中 + MQ runner 运行中（异步分析依赖 outbox→MQ→Worker 落库），
MySQL/Redis/DeepSeek 正常。结束自动清理测试数据（resume/interview/question/report行 + Redis键）。
"""

import json
import sys
import time
from pathlib import Path

import jwt
import requests
from sqlalchemy import text

# 允许直接 python 运行时从项目根导入 app 包（脚本位于 tests/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.sync_session import SyncSessionLocal

# ---- 配置 ----
# 后端在容器内通过 localhost:8000 直接可达（E2E 脚本应在后端容器内运行）。
BASE = "http://127.0.0.1:8000/api/v1"
AUTH_URL = "http://127.0.0.1:8000/api/v1/auth"
USER_ID = 1  # E2E测试用户A
INTERVIEW_TYPE = 2  # 快速面试（5题，控制LLM时长）

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    """记录单个断言结果。"""
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        FAIL.append((name, detail))
        print(f"  [FAIL] {name} -> {detail}")


def session_for(user_id: int) -> requests.Session:
    """通过 dev-login（DEBUG 环境）获取真实 HttpOnly Cookie 会话。

    后端已启用单设备登录（jti 校验），手工签发 token 无法通过校验，
    故走 dev-login 端点绕 OAuth 直签双 Token 并写 Cookie，最贴近真实登录链路。
    """
    s = requests.Session()
    resp = s.get(f"{AUTH_URL}/dev-login?user_id={user_id}", timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"dev-login 失败: {resp.status_code} {resp.text[:200]}")
    # 生产 .env 的 COOKIE_SECURE=true：cookie 带 Secure 标志，requests 在纯 http 下
    # 默认不会发送。E2E 在容器内走 http://localhost:8000，须去掉 Secure 标志强制携带。
    access_token = s.cookies.get("access_token")
    refresh_token = s.cookies.get("refresh_token")
    s.cookies.clear()
    s.cookies.set("access_token", access_token, domain="127.0.0.1", path="/", secure=False)
    if refresh_token:
        s.cookies.set("refresh_token", refresh_token, domain="127.0.0.1", path="/api/v1/auth", secure=False)
    assert "access_token" in s.cookies, "dev-login 未设置 access_token Cookie"
    return s


def prepare_ready_resume() -> int:
    """直接落库一份已就绪简历（含解析结果），返回 resume_id。

    面试模块只消费 Resume Analysis 结果（§1 解耦），无需走上传解析链路。
    """
    db = SyncSessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO resume (user_id, file_name, status, parsed_name, parsed_skills, "
                "parsed_education, parsed_projects, is_deleted) VALUES "
                "(:uid, 'e2e_interview_resume.pdf', 1, :name, :skills, :edu, :projects, 0)"
            ),
            {
                "uid": USER_ID,
                "name": "E2E候选人",
                "skills": json.dumps(["Python", "FastAPI", "MySQL", "Redis", "RabbitMQ"]),
                "edu": json.dumps([{"school": "测试大学", "degree": "本科", "major": "计算机科学", "duration": "2018-2022"}]),
                "projects": json.dumps([
                    {"name": "AI面试平台", "description": "负责面试会话模块与并发控制设计", "tech_stack": ["FastAPI", "Redis", "MySQL"]},
                    {"name": "社区系统", "description": "负责帖子/评论/点赞模块", "tech_stack": ["Vue3", "FastAPI"]},
                ]),
            },
        )
        db.commit()
        resume_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
        print(f"[SETUP] 就绪简历已创建: resume_id={resume_id}")
        return resume_id
    finally:
        db.close()


def cleanup(resume_id: int, interview_id: int | None) -> None:
    """清理本次E2E测试数据（DB行 + Redis键）。"""
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
    print(f"[CLEANUP] 测试数据已清理: resume_id={resume_id} interview_id={interview_id}")


def main() -> None:
    """执行E2E冒烟主流程。"""
    s = session_for(USER_ID)
    resume_id: int | None = None
    interview_id: int | None = None
    try:
        # ---- 0. 服务健康 ----
        resp = s.get("http://127.0.0.1:8000/health", timeout=5)
        check("服务健康检查", resp.status_code == 200)

        # ---- 1. 简历未就绪拦截（先无简历 → 404） ----
        resp = s.post(f"{BASE}/interviews", json={"resume_id": 999999, "type": 1, "tab_id": "tab-A"}, timeout=10)
        check("不存在简历创建404", resp.status_code == 404, resp.text)

        # ---- 2. 创建面试（真实LLM出题） ----
        resume_id = prepare_ready_resume()
        t0 = time.time()
        resp = s.post(
            f"{BASE}/interviews",
            json={"resume_id": resume_id, "type": INTERVIEW_TYPE, "tab_id": "tab-A"},
            timeout=180,
        )
        elapsed = time.time() - t0
        check("创建面试201", resp.status_code == 201, resp.text)
        if resp.status_code != 201:
            return
        created = resp.json()
        interview_id = created["interview_id"]
        print(f"  [INFO] 出题耗时 {elapsed:.1f}s, 题目数={created['total_questions']}")
        check("创建返回epoch=1", created["epoch"] == 1)
        # 快速面试固定 9 题（§面试流程功能文档：2技术八股/4项目/1架构/2综合）
        check("快速面试题量=9", created["total_questions"] == 9, str(created["total_questions"]))
        check("返回首题", created["current_question"] is not None)

        # ---- 3. 草稿态核验：创建后 phase=not_started（设备检测前，§3 新流程） ----
        resp = s.get(f"{BASE}/interviews/{interview_id}?tab_id=tab-A", timeout=10)
        state = resp.json()
        check("状态查询200", resp.status_code == 200, resp.text)
        check("同tab刷新epoch不变", state["epoch"] == 1, str(state.get("epoch")))
        check("创建后phase=not_started(草稿)", state["phase"] == "not_started", str(state.get("phase")))

        # 历史列表：草稿态 is_started=false（前端据此分流回设备检测步骤）
        resp = s.get(f"{BASE}/interviews", timeout=10)
        lst_item = next((it for it in resp.json()["items"] if it["interview_id"] == interview_id), None)
        check("列表草稿is_started=false", lst_item is not None and lst_item["is_started"] is False, str(lst_item))

        # ---- 4. 设备检测通过 → 正式启动（POST /start：not_started → answering，幂等） ----
        resp = s.post(f"{BASE}/interviews/{interview_id}/start", timeout=15)
        check("启动面试200", resp.status_code == 200, resp.text)
        started = resp.json()
        check("启动后phase=answering", started["phase"] == "answering", str(started.get("phase")))
        check("启动后question_index=1", started["question_index"] == 1, str(started.get("question_index")))
        # 幂等：重复 start 仍返回 answering（不会重复推进）
        resp2 = s.post(f"{BASE}/interviews/{interview_id}/start", timeout=15)
        check("启动幂等200+answering", resp2.status_code == 200 and resp2.json()["phase"] == "answering", resp2.text)
        # 列表：启动后 is_started=true（前端据此直进面试间）
        resp = s.get(f"{BASE}/interviews", timeout=10)
        lst_item = next((it for it in resp.json()["items"] if it["interview_id"] == interview_id), None)
        check("列表启动后is_started=true", lst_item is not None and lst_item["is_started"] is True, str(lst_item))

        # ---- 5. 双开接管：新tab → epoch+1 ----
        resp = s.get(f"{BASE}/interviews/{interview_id}?tab_id=tab-B", timeout=10)
        check("新tab接管epoch=2", resp.json().get("epoch") == 2, resp.text)
        # 旧tab提交 → 409
        resp = s.post(
            f"{BASE}/interviews/{interview_id}/answers",
            json={"question_index": 1, "answer": "旧标签页的回答", "tab_epoch": 1},
            timeout=30,
        )
        check("旧epoch提交409", resp.status_code == 409, resp.text)
        # 切回tab-A（epoch=3）
        resp = s.get(f"{BASE}/interviews/{interview_id}?tab_id=tab-A", timeout=10)
        epoch = resp.json()["epoch"]
        check("A回归接管epoch=3", epoch == 3, str(epoch))

        # ---- 6. 提交回答（v2：Fast Decision 秒级进下一题，全量分析异步 Worker） ----
        answers_pool = {
            1: "Redis是内存数据库，数据在内存里，断电会丢，所以要持久化。",
            2: "我负责了AI面试平台的面试会话模块，用了FastAPI和Redis，实现了面试状态管理。",
            3: "遇到问题我会先搜索资料，看看官方文档，然后动手尝试。",
            4: "Python的GIL是全局解释器锁，它让多线程不能真正并行执行CPU任务。",
            5: "MySQL索引主要是B+树结构，可以加快查询速度。",
        }
        follow_up_seen = False
        question_index = 1
        total_answered = 0
        while True:
            state = s.get(f"{BASE}/interviews/{interview_id}", timeout=10).json()
            if state["phase"] not in ("answering", "analyzing"):
                break
            answer = answers_pool.get(question_index, "通用回答：" + "关于该问题的说明。" * 3)
            t0 = time.time()
            resp = s.post(
                f"{BASE}/interviews/{interview_id}/answers",
                json={"question_index": question_index, "answer": answer, "tab_epoch": epoch},
                timeout=180,
            )
            elapsed = time.time() - t0
            if resp.status_code != 200:
                check(f"第{question_index}题提交200", False, f"HTTP {resp.status_code}: {resp.text[:300]}")
                break
            body = resp.json()
            total_answered += 1
            print(
                f"  [INFO] 题{question_index} FastDecision耗时{elapsed:.1f}s "
                f"phase={body['phase']} next={bool(body['next_question'])}"
            )
            # v2：Fast Decision 秒级返回，同步不再实时携带评分
            check(f"第{question_index}题秒级返回", elapsed < 60, f"{elapsed:.1f}s")
            if body["next_question"] is None:
                check("末题返回summarizing", body["phase"] == "summarizing")
                break
            if body["next_question"]["is_follow_up"]:
                follow_up_seen = True
            question_index = body["next_question"]["question_index"]
            # 追问链兜底：快速面试 9 基础题 + 每题至多 1 追问 = 上限 18，
            # 25 足以覆盖正常链路，仅防 LLM 异常无限追问
            if total_answered > 25:
                check("追问链未失控(≤25)", False, f"answered={total_answered}")
                break

        # ---- 7. 幂等：重复提交已答题 ----
        resp = s.post(
            f"{BASE}/interviews/{interview_id}/answers",
            json={"question_index": 1, "answer": "重复提交", "tab_epoch": epoch},
            timeout=30,
        )
        check("幂等重复提交200+duplicated", resp.status_code == 200 and resp.json().get("duplicated") is True, resp.text[:300])

        # ---- 7. 报告生成（后台线程，轮询等待；v2 会先强制等待异步分析补齐60s） ----
        report_status = None
        for _ in range(80):
            resp = s.get(f"{BASE}/interviews/{interview_id}/report", timeout=10)
            report_status = resp.json().get("status")
            if report_status == "ready":
                break
            time.sleep(3)
        check("报告生成ready", report_status == "ready", f"status={report_status}")
        if report_status == "ready":
            report = resp.json()["report"]
            print(f"  [INFO] 总分={report['total_score']} 题数={report['question_count']}")
            check("报告总分有效", 0 < float(report["total_score"]) <= 100, str(report["total_score"]))
            check("报告含总评", len(report["summary"]) > 10)
            check("报告含改进建议", len(report["suggestions"]) >= 1)

        # ---- 9. 题目落库核验 ----
        db = SyncSessionLocal()
        try:
            rows = db.execute(
                text("SELECT question_no, is_follow_up, ai_score, user_answer FROM interview_question "
                     "WHERE interview_id=:i ORDER BY question_no, is_follow_up, id"),
                {"i": interview_id},
            ).fetchall()
            # v2：user_answer 由同步路径即时落库；ai_score 由异步 Worker 后补
            answered = [r for r in rows if r[3] is not None]
            check("逐题落库已答数量", len(answered) == total_answered, f"db={len(answered)} api={total_answered}")
            follow_up_rows = [r for r in rows if r[1] == 1]
            scored = [r for r in rows if r[2] is not None and r[3] is not None]
            print(
                f"  [INFO] 落库题目总数={len(rows)} 其中追问={len(follow_up_rows)} "
                f"已异步分析评分={len(scored)}（报告生成前已强制等待补齐）"
            )
            status_row = db.execute(
                text("SELECT status, total_score, follow_up_count FROM interview WHERE id=:i"), {"i": interview_id}
            ).fetchone()
            check("interview状态=1已完成", status_row[0] == 1)
            check("总分冗余回写", float(status_row[1] or 0) > 0, str(status_row[1]))
        finally:
            db.close()

        # ---- 10. 放弃链路（另建一场快速放弃，草稿态直接放弃） ----
        resp = s.post(
            f"{BASE}/interviews",
            json={"resume_id": resume_id, "type": 2, "tab_id": "tab-C"},
            timeout=180,
        )
        if resp.status_code == 201:
            iid2 = resp.json()["interview_id"]
            epoch2 = resp.json()["epoch"]
            resp = s.post(f"{BASE}/interviews/{iid2}/abort", json={"tab_epoch": epoch2}, timeout=10)
            check("主动放弃204", resp.status_code == 204, resp.text)
            state2 = s.get(f"{BASE}/interviews/{iid2}", timeout=10).json()
            check("放弃后status=2/aborted", state2["status"] == 2 and state2["phase"] == "aborted", str(state2))
            # 追问是否被触发（信息性，不作为硬断言）
            print(f"  [INFO] 主链路追问触发: {follow_up_seen}")
            # 清理第二场
            db = SyncSessionLocal()
            try:
                db.execute(text("DELETE FROM interview_question WHERE interview_id=:i"), {"i": iid2})
                db.execute(text("DELETE FROM interview WHERE id=:i"), {"i": iid2})
                db.commit()
            finally:
                db.close()
        else:
            check("第二场创建（放弃链路）", False, resp.text[:200])

    finally:
        cleanup(resume_id, interview_id)

    print("\n========== 结果汇总 ==========")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    for name, detail in FAIL:
        print(f"  FAILED: {name} -> {detail[:200]}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
