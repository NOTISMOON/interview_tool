"""面试模块单元测试：创建校验/三层并发控制/幂等/追问判定/逐题落库/报告。

覆盖《面试流程功能文档》M1/M2 核心链路（LLM 调用全部桩化，
真实链路验证由 e2e 冒烟承担）。Redis 桩实现 set NX EX / get / delete /
setex / eval（Lua 脚本以 Python 等价逻辑模拟）。
"""

import json

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db, get_redis
from app.api.v1.controllers.interviews import router as interviews_router
from app.llm.schemas.interview import (
    GeneratedQuestion,
    InterviewReportResult,
    QuestionGenerationResult,
)
from app.redis import interview_session as isess
from app.services import interview_service as isvc

# --------------------------------------------------------------------------
# SQLite 兼容 DDL（不含 MySQL 专有 ON UPDATE 子句）
# --------------------------------------------------------------------------

_DDL_STATEMENTS = [
    """
    CREATE TABLE interview (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        resume_id INTEGER NOT NULL,
        type INTEGER NOT NULL DEFAULT 1,
        status INTEGER NOT NULL DEFAULT 0,
        current_question_index INTEGER NOT NULL DEFAULT 0,
        total_score NUMERIC(5,2),
        total_duration INTEGER,
        follow_up_count INTEGER NOT NULL DEFAULT 0,
        device_check_passed INTEGER NOT NULL DEFAULT 0,
        interview_time DATETIME,
        is_deleted INTEGER NOT NULL DEFAULT 0,
        deleted_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE interview_question (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        interview_id INTEGER NOT NULL,
        question_no INTEGER NOT NULL,
        question_type INTEGER NOT NULL,
        category INTEGER,
        is_follow_up INTEGER NOT NULL DEFAULT 0,
        parent_question_id INTEGER,
        question_text TEXT NOT NULL,
        user_answer TEXT,
        audio_url VARCHAR(512),
        answer_duration INTEGER,
        thinking_duration INTEGER,
        ai_score INTEGER,
        ai_comment TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE interview_report (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        interview_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        total_score NUMERIC(5,2) NOT NULL,
        dimension_scores JSON,
        summary TEXT NOT NULL,
        strengths JSON NOT NULL,
        weaknesses JSON NOT NULL,
        capability_profile JSON,
        suggestions JSON NOT NULL,
        question_count INTEGER NOT NULL DEFAULT 0,
        follow_up_count INTEGER NOT NULL DEFAULT 0,
        total_duration INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE resume (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        file_name VARCHAR(255) NOT NULL,
        file_url VARCHAR(512),
        file_size INTEGER,
        file_hash VARCHAR(64),
        status INTEGER NOT NULL DEFAULT 0,
        parsed_name VARCHAR(128),
        parsed_skills JSON,
        parsed_education JSON,
        parsed_projects JSON,
        error_message VARCHAR(512),
        is_deleted INTEGER NOT NULL DEFAULT 0,
        deleted_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE resume_work_experience (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id INTEGER NOT NULL,
        company VARCHAR(128) NOT NULL,
        role VARCHAR(128) NOT NULL,
        duration VARCHAR(64) NOT NULL,
        description TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE outbox_event (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type VARCHAR(64) NOT NULL,
        aggregate_type VARCHAR(64) NOT NULL,
        aggregate_id VARCHAR(64) NOT NULL,
        payload JSON,
        status INTEGER NOT NULL DEFAULT 0,
        retry_count INTEGER NOT NULL DEFAULT 0,
        next_retry_at DATETIME,
        published_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


class FakeRedis:
    """内存版Redis桩：实现面试模块用到的 set/get/delete/setex/eval 语义。

    eval 按脚本内容路由：含 "tab_id" 为租约激活脚本（同tab幂等/新tab
    epoch+1），含 "DEL" 为锁释放脚本（compare-and-del）。
    """

    def __init__(self) -> None:
        """初始化字符串/列表存储与TTL记录。"""
        self.strings: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        """SET语义：nx=True时键已存在返回False。"""
        if nx and key in self.strings:
            return False
        self.strings[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key: str) -> str | None:
        """GET语义。"""
        return self.strings.get(key)

    def exists(self, *keys: str) -> int:
        """EXISTS语义（T2.2 同题处理中标记判定）。"""
        return sum(1 for k in keys if k in self.strings or k in self.lists)

    def delete(self, *keys: str) -> int:
        """DELETE语义，返回实际删除数。"""
        removed = 0
        for key in keys:
            if key in self.strings:
                del self.strings[key]
                removed += 1
            if key in self.lists:
                del self.lists[key]
                removed += 1
        return removed

    def setex(self, key: str, seconds: int, value: str) -> bool:
        """SETEX语义（TTL仅记录不实现过期）。"""
        self.strings[key] = value
        self.ttls[key] = seconds
        return True

    def rpush(self, key: str, *values: object) -> int:
        """RPUSH语义（问题队列初始化入队）。"""
        self.lists.setdefault(key, []).extend(str(v) for v in values)
        return len(self.lists[key])

    def lpush(self, key: str, *values: object) -> int:
        """LPUSH语义（追问插入队首）。"""
        self.lists.setdefault(key, [])
        self.lists[key] = [str(v) for v in values] + self.lists[key]
        return len(self.lists[key])

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        """LRANGE语义（队列审计/恢复）。"""
        items = self.lists.get(key, [])
        if not items:
            return []
        n = len(items)
        s = start if start >= 0 else max(n + start, 0)
        e = end if end >= 0 else n + end
        return items[s : e + 1]

    def lrem(self, key: str, count: int = 0, value: str = "") -> int:
        """LREM语义（当前题出队；仅支持 count=0 全删。"""
        lst = self.lists.get(key)
        if lst is None:
            return 0
        target = str(value)
        kept = [x for x in lst if x != target]
        removed = len(lst) - len(kept)
        self.lists[key] = kept
        return removed

    def expire(self, key: str, seconds: int) -> bool:
        """记录键的TTL（仅记录不实现过期）。"""
        self.ttls[key] = seconds
        return True

    def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        """模拟两类Lua脚本：租约激活 / 锁释放。"""
        keys = list(keys_and_args[:numkeys])
        args = list(keys_and_args[numkeys:])
        if "tab_id" in script:
            # 租约激活：同tab幂等返回，新tab epoch+1接管
            key, tab_id, _ttl = keys[0], str(args[0]), args[1]
            raw = self.strings.get(key)
            if raw:
                lease = json.loads(raw)
                if lease["tab_id"] == tab_id:
                    return lease["epoch"]
                lease["tab_id"] = tab_id
                lease["epoch"] += 1
            else:
                lease = {"tab_id": tab_id, "epoch": 1}
            self.strings[key] = json.dumps(lease)
            return lease["epoch"]
        if "DEL" in script:
            # 锁释放：值匹配才删除（compare-and-del）
            key, token = keys[0], str(args[0])
            if self.strings.get(key) == token:
                del self.strings[key]
                return 1
            return 0
        raise ValueError(f"未知脚本: {script[:50]}")


# --------------------------------------------------------------------------
# 固件
# --------------------------------------------------------------------------

@pytest.fixture()
def db_session(monkeypatch: pytest.MonkeyPatch) -> Session:
    """提供每个测试独立的内存SQLite会话（自动建面试相关表）。

    同时将服务层的后台任务会话工厂（SyncSessionLocal）替换为测试工厂，
    使报告后台生成等独立会话路径同样命中内存库。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        for ddl in _DDL_STATEMENTS:
            conn.execute(text(ddl))
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(isvc, "SyncSessionLocal", factory)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def fake_redis() -> FakeRedis:
    """提供干净的FakeRedis实例。"""
    return FakeRedis()


@pytest.fixture()
def auth_user_id() -> int:
    """当前认证用户ID。"""
    return 1


@pytest.fixture()
def client(db_session: Session, fake_redis: FakeRedis, auth_user_id: int) -> TestClient:
    """构建挂载面试路由的测试客户端（覆盖DB/Redis/认证依赖）。"""

    def _override_get_db():
        """复用测试会话。"""
        yield db_session

    def _override_get_redis() -> FakeRedis:
        """返回FakeRedis。"""
        return fake_redis

    def _override_get_current_user() -> dict:
        """返回固定测试用户载荷。"""
        return {"sub": str(auth_user_id)}

    test_app = FastAPI()
    api = APIRouter(prefix="/api/v1")
    api.include_router(interviews_router)
    test_app.include_router(api)
    test_app.dependency_overrides[get_db] = _override_get_db
    test_app.dependency_overrides[get_redis] = _override_get_redis
    test_app.dependency_overrides[get_current_user] = _override_get_current_user
    return TestClient(test_app)


@pytest.fixture()
def ready_resume(db_session: Session, auth_user_id: int) -> int:
    """创建一份已就绪（status=1）的简历，返回ID。"""
    db_session.execute(
        text(
            "INSERT INTO resume (user_id, file_name, status, parsed_name, parsed_skills) "
            "VALUES (:uid, 'resume.pdf', 1, '张三', :skills)"
        ),
        {"uid": auth_user_id, "skills": json.dumps(["Python", "FastAPI"])},
    )
    db_session.commit()
    return db_session.execute(text("SELECT MAX(id) FROM resume")).scalar_one()


@pytest.fixture()
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> dict:
    """桩化面试相关 LLM 工作流入口，返回可变调用记录。

    默认行为：
        - 出题 3 道基础题；
        - 流式追问生成：输出 NONE（不追问，走下一基础题/结束）；
        - 报告 85 分。
    全量分析已异步化，同步路径不再调用 analyze_answer。
    """
    calls: dict = {"questions": [], "follow_ups": [], "reports": 0}

    def _fake_generate_questions(resume_context: dict, interview_type: int) -> QuestionGenerationResult:
        """返回3道固定基础题。"""
        calls["questions"].append({"type": interview_type, "context": resume_context})
        return QuestionGenerationResult(
            questions=[
                GeneratedQuestion(question_text="题目一：Python GIL 是什么？", question_type=1, category=1),
                GeneratedQuestion(question_text="题目二：介绍一个项目", question_type=2, category=2),
                GeneratedQuestion(question_text="题目三：如何学习新技术？", question_type=3, category=3),
            ]
        )

    def _fake_follow_up_stream(
        question: str, answer: str, resume_context: dict,
    ):
        """返回固定流式追问输出：默认 NONE；可通过 calls["follow_up_behavior"] 调整。

        behavior: {"text": "..."} → 流式输出追问文本；text 为 None/缺省 → NONE。
        """
        calls["follow_ups"].append({"question": question, "answer": answer})
        behavior = calls.get("follow_up_behavior") or {"text": None}
        text = behavior.get("text")
        if not text:
            yield "NONE"
            return
        for ch in text:
            yield ch

    def _fake_generate_report(resume_context: dict, records: list) -> InterviewReportResult:
        """返回固定报告。"""
        calls["reports"] += 1
        return InterviewReportResult(
            total_score=85.5,
            dimension_scores={"技术能力": 85.0},
            strengths=["基础扎实"],
            weaknesses=["深度不足"],
            capability_profile={"技术水平": "中级"},
            suggestions=["加强底层原理"],
            summary="整体表现良好",
        )

    monkeypatch.setattr(isvc, "generate_questions", _fake_generate_questions)
    monkeypatch.setattr(isvc, "generate_follow_up_stream", _fake_follow_up_stream)
    monkeypatch.setattr(isvc, "correct_speech_text", lambda question, transcript, resume_context: transcript)
    monkeypatch.setattr(isvc, "generate_report", _fake_generate_report)
    # SSE推送桩化（避免测试内起事件循环连Redis）
    monkeypatch.setattr(isvc.interview_service, "_publish_sse", lambda *a, **k: None)
    # 异步分析投递桩化（测试内不落 outbox，避免依赖 DB 表/事件循环）
    monkeypatch.setattr(isvc.interview_service, "_dispatch_async_analysis", lambda *a, **k: None)
    # 报告生成投递桩化（MQ 异步化：测试内不落 outbox，避免依赖 DB 表）
    monkeypatch.setattr(isvc.interview_service, "_dispatch_report_generation", lambda *a, **k: None)
    # 报告前等待异步分析补齐桩化（测试内分析未真实落库，避免 60s 轮询挂起）
    monkeypatch.setattr(isvc.interview_service, "_wait_analysis_complete", lambda *a, **k: None)
    return calls


def _create_interview(client: TestClient, resume_id: int, tab_id: str = "tab-A", type_: int = 1) -> dict:
    """测试辅助：创建面试并返回响应JSON。"""
    resp = client.post("/api/v1/interviews", json={"resume_id": resume_id, "type": type_, "tab_id": tab_id})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _submit(client: TestClient, interview_id: int, question_index: int, answer: str, epoch: int) -> object:
    """测试辅助：提交回答（v3·受理化），返回原始响应对象。"""
    return client.post(
        f"/api/v1/interviews/{interview_id}/answers",
        json={"question_index": question_index, "answer": answer, "tab_epoch": epoch},
    )


def _consume(cache: FakeRedis, interview_id: int, question_index: int, answer: str, epoch: int) -> bool:
    """测试辅助：模拟 Answer Consumer 异步编排（判题/追问/落库/推进）。

    请求线程已毫秒返回"已受理"；本函数在测试内同步执行 Consumer 侧编排，
    以便断言落库与 checkpoint 结果。
    """
    return isvc.interview_service.process_answer_submitted(
        cache, interview_id, question_index, answer, epoch, None
    )


# --------------------------------------------------------------------------
# 创建面试（§3）
# --------------------------------------------------------------------------

class TestCreateInterview:
    """创建面试测试。"""

    def test_create_success_with_questions_and_checkpoint(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试创建成功：题目落库、Checkpoint初始化、epoch=1、返回首题。"""
        data = _create_interview(client, ready_resume)
        assert data["interview_id"] == 1
        assert data["epoch"] == 1
        assert data["total_questions"] == 3
        assert data["current_question"]["question_text"].startswith("题目一")
        # 题目逐题落库（is_follow_up=0，question_no 顺序即面试顺序）
        rows = db_session.execute(
            text("SELECT question_no, is_follow_up FROM interview_question WHERE interview_id=1 ORDER BY id")
        ).fetchall()
        assert [r[0] for r in rows] == [1, 2, 3]
        assert all(r[1] == 0 for r in rows)
        # Checkpoint 初始化（§6.2）：创建为草稿态 not_started（设备检测前，BUG3 后）
        checkpoint = isess.load_checkpoint_sync(fake_redis, 1)
        assert checkpoint["phase"] == "not_started"
        assert checkpoint["question_index"] == 1
        assert checkpoint["base_question_count"] == 3
        # 设备检测后正式启动 → answering（BUG3：started_at 在启动时重置）
        resp = client.post("/api/v1/interviews/1/start")
        assert resp.status_code == 200, resp.text
        checkpoint = isess.load_checkpoint_sync(fake_redis, 1)
        assert checkpoint["phase"] == "answering"
        assert checkpoint["base_question_count"] == 3

    def test_create_resume_analyzing_conflict(self, client: TestClient, db_session: Session, stub_llm: dict) -> None:
        """测试简历分析中创建面试返回409 analyzing。"""
        db_session.execute(
            text("INSERT INTO resume (user_id, file_name, status) VALUES (1, 'r.pdf', 0)")
        )
        db_session.commit()
        resp = client.post("/api/v1/interviews", json={"resume_id": 1, "type": 1, "tab_id": "tab-A"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "analyzing"

    def test_create_resume_failed_conflict(self, client: TestClient, db_session: Session, stub_llm: dict) -> None:
        """测试简历分析失败创建面试返回409 analysis_failed。"""
        db_session.execute(
            text("INSERT INTO resume (user_id, file_name, status) VALUES (1, 'r.pdf', 2)")
        )
        db_session.commit()
        resp = client.post("/api/v1/interviews", json={"resume_id": 1, "type": 1, "tab_id": "tab-A"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "analysis_failed"

    def test_create_resume_not_found(
        self, client: TestClient, db_session: Session, stub_llm: dict, auth_user_id: int,
    ) -> None:
        """测试他人简历/不存在简历返回404。"""
        db_session.execute(
            text("INSERT INTO resume (user_id, file_name, status) VALUES (999, 'r.pdf', 1)")
        )
        db_session.commit()
        resp = client.post("/api/v1/interviews", json={"resume_id": 1, "type": 1, "tab_id": "tab-A"})
        assert resp.status_code == 404
        resp = client.post("/api/v1/interviews", json={"resume_id": 42, "type": 1, "tab_id": "tab-A"})
        assert resp.status_code == 404

    def test_create_llm_failure_no_dirty_data(
        self, client: TestClient, db_session: Session, ready_resume: int, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """测试LLM出题失败返回503且无脏数据（interview行删除，§21）。"""
        def _boom(resume_context: dict, interview_type: int):
            """模拟LLM出题异常。"""
            raise RuntimeError("LLM不可用")

        monkeypatch.setattr(isvc, "generate_questions", _boom)
        monkeypatch.setattr(isvc.interview_service, "_publish_sse", lambda *a, **k: None)
        resp = client.post("/api/v1/interviews", json={"resume_id": ready_resume, "type": 1, "tab_id": "tab-A"})
        assert resp.status_code == 503
        count = db_session.execute(text("SELECT COUNT(*) FROM interview")).scalar_one()
        assert count == 0


# --------------------------------------------------------------------------
# 提交回答：三层并发控制 + 幂等 + 逐题落库（§8/§9/§10/§14）
# --------------------------------------------------------------------------

class TestSubmitAnswer:
    """提交回答测试。"""

    def test_submit_answer_normal_flow(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试正常提交（v3 受理化）：受理 accepted → Consumer 消费后落库推进（§8/§12）。

        请求线程毫秒返回"已受理"（phase=analyzing、next_question=null）；判题/落库/推进
        由 Answer Consumer 异步完成（测试内以 _consume 同步模拟）。
        """
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        resp = _submit(client, iid, 1, "GIL是全局解释器锁", epoch)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # 受理态：不再返回评分与下一题（判题在消费端）
        assert body["accepted"] is True
        assert body["phase"] == "analyzing"
        assert body["next_question"] is None
        # 模拟 Consumer 消费：判题 + 落库 + 推进
        assert _consume(fake_redis, iid, 1, "GIL是全局解释器锁", epoch) is True
        # 消费后幂等重发：拿到既有结果与下一题
        second = _submit(client, iid, 1, "重发", epoch)
        assert second.status_code == 200
        body2 = second.json()
        assert body2["duplicated"] is True
        assert body2["next_question"]["question_index"] == 2
        # user_answer 逐题落库（§14.2）；ai_score 待 Worker 后补（此时为 NULL）
        row = db_session.execute(
            text("SELECT user_answer, ai_score, ai_comment FROM interview_question WHERE interview_id=:i AND question_no=1"),
            {"i": iid},
        ).fetchone()
        assert row[0] == "GIL是全局解释器锁"
        assert row[1] is None  # 异步分析未落库
        assert row[2] is None

    def test_submit_answer_idempotent(
        self, client: TestClient, fake_redis: FakeRedis, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试幂等（v3）：已落库题重复提交直接返回既有结果，不重跑 Fast Decision（§5.9）。"""
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        _submit(client, iid, 1, "答案A", epoch)
        assert _consume(fake_redis, iid, 1, "答案A", epoch) is True
        llm_calls_before = len(stub_llm["follow_ups"])
        second = _submit(client, iid, 1, "答案A重发", epoch)
        assert second.status_code == 200
        body = second.json()
        assert body["duplicated"] is True
        assert body["analysis"]["score"] == 0  # ai_score 未异步落库 → 待补充
        assert len(stub_llm["follow_ups"]) == llm_calls_before  # 未重跑追问生成

    def test_submit_answer_epoch_mismatch(
        self, client: TestClient, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试epoch租约不符返回409（双开裁决，§5.6）。"""
        created = _create_interview(client, ready_resume)
        iid = created["interview_id"]
        resp = _submit(client, iid, 1, "旧标签页回答", epoch=99)
        assert resp.status_code == 409
        assert resp.json()["detail"]["reason"] == "epoch_mismatch"
        # 携带最新状态（前端强制同步）
        assert resp.json()["detail"]["latest_state"]["question_index"] == 1

    def test_submit_after_finish_idempotent_retry(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试面试已结束后重试已答题仍返回幂等结果（§5.9超时重试安全）。

        最后一题判题完成转 status=1 且租约被清理，前端超时重发必须
        拿到幂等响应而不是 409 finished。
        """
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        for idx in (1, 2, 3):
            resp = _submit(client, iid, idx, f"回答{idx}", epoch)
            assert resp.status_code == 200
            assert _consume(fake_redis, iid, idx, f"回答{idx}", epoch) is True
        # 面试已完成（末期消费内 finish + 投递报告事件）
        retry = _submit(client, iid, 3, "最后一题超时重发", epoch)
        assert retry.status_code == 200
        body = retry.json()
        assert body["duplicated"] is True
        assert body["analysis"]["score"] == 0  # 异步分析，ai_score 未落库 → 待补充

    def test_submit_answer_version_mismatch(
        self, client: TestClient, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试状态版本不符（题序错位）返回409（§5.5）。"""
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        resp = _submit(client, iid, 3, "跳题回答", epoch)  # 当前应为第1题
        assert resp.status_code == 409
        assert resp.json()["detail"]["reason"] == "version_mismatch"

    def test_submit_answer_lock_not_blocking_accept(
        self, client: TestClient, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试操作锁占用不再阻塞受理（v3，T3.7）：提交链路 409 busy 消失。

        受理接口不持操作锁（只做校验+投事件）；判题/推进才短持锁（在消费端）。
        """
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        # 预置他人持有的操作锁（不影响受理）
        isess.acquire_lock_sync(fake_redis, iid, "other-token")
        resp = _submit(client, iid, 1, "并发回答", epoch)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accepted"] is True
        assert body["phase"] == "analyzing"
        # 消费端短持锁推进仍可正常完成（锁由已提交请求释放）
        assert _consume(fake_redis, iid, 1, "并发回答", epoch) is True

    def test_submit_same_question_repeat_accepts_without_redundant_event(
        self, client: TestClient, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """测试同题重复提交（T3.5）：analyzing 去重返回"已受理"，不重复投递事件。

        前端超时/重试场景：同题已受理判题中 → 直接 accepted（前端继续轮询），
        不再产生第二份判题工作，回归幂等语义。
        """
        events: list[str] = []
        original = isvc.sync_outbox_repository.insert_event

        def _counting(db, event_type, aggregate_type, aggregate_id, payload):
            """计数投递事件并转调真实实现。"""
            events.append(event_type)
            return original(db, event_type, aggregate_type, aggregate_id, payload)

        monkeypatch.setattr(isvc.sync_outbox_repository, "insert_event", _counting)
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        first = _submit(client, iid, 1, "第一次提交", epoch)
        assert first.status_code == 200
        assert first.json()["accepted"] is True
        assert events.count("interview.answer.submitted") == 1
        # 同题重复提交：analyzing 去重 → 仍返回已受理，不新增事件
        second = _submit(client, iid, 1, "第一次提交重试", epoch)
        assert second.status_code == 200
        body = second.json()
        assert body["accepted"] is True
        assert events.count("interview.answer.submitted") == 1

    def test_follow_up_rule_triggered(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试追问判定通过（v3）：Consumer 判题产出追问并落库作为下一题（§10/§11）。"""
        stub_llm["follow_up_behavior"] = {
            "text": "Redis持久化机制RDB与AOF的区别？",
        }
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        _submit(client, iid, 1, "因为Redis是内存数据库", epoch)
        assert _consume(fake_redis, iid, 1, "因为Redis是内存数据库", epoch) is True
        # 消费后重发同题：幂等复用，next 为已落库的追问题
        resp = _submit(client, iid, 1, "重发", epoch)
        body = resp.json()
        assert body["duplicated"] is True
        assert body["next_question"]["is_follow_up"] is True
        assert body["next_question"]["question_no"] == 1  # 与父题同号
        assert "持久化" in body["next_question"]["question_text"]
        # 追问题落库校验（§11）
        row = db_session.execute(
            text("SELECT is_follow_up, parent_question_id FROM interview_question "
                 "WHERE interview_id=:i AND is_follow_up=1"),
            {"i": iid},
        ).fetchone()
        assert row is not None and row[0] == 1
        # Checkpoint 指向追问题（题序=2）
        checkpoint = isess.load_checkpoint_sync(fake_redis, iid)
        assert checkpoint["question_index"] == 2
        assert checkpoint["total_follow_up_used"] == 1

    def test_follow_up_rule_not_triggered_when_answer_strong(
        self, client: TestClient, fake_redis: FakeRedis, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试回答优秀不追问，直接下一题（§10）。"""
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        _submit(client, iid, 1, "完整且深入的回答", epoch)
        assert _consume(fake_redis, iid, 1, "完整且深入的回答", epoch) is True
        resp = _submit(client, iid, 1, "重发", epoch)
        body = resp.json()
        assert body["duplicated"] is True
        assert body["next_question"]["is_follow_up"] is False
        assert body["next_question"]["question_index"] == 2

    def test_follow_up_per_base_limit(
        self, client: TestClient, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试每道基础题最多追问1次：追问回答再薄弱也不二次追问（§10）。"""
        stub_llm["follow_up_behavior"] = {
            "text": "再次追问？",
        }
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        _submit(client, iid, 1, "浅回答", epoch)
        assert _consume(fake_redis, iid, 1, "浅回答", epoch) is True
        first = _submit(client, iid, 1, "重发", epoch).json()
        assert first["next_question"]["is_follow_up"] is True
        # 回答追问题（题序2）后：per_base=1 已满 → 不再追问，进入下一基础题
        _submit(client, iid, 2, "追问的浅回答", epoch)
        assert _consume(fake_redis, iid, 2, "追问的浅回答", epoch) is True
        second = _submit(client, iid, 2, "重发", epoch).json()
        assert second["next_question"]["is_follow_up"] is False
        assert second["next_question"]["question_no"] == 2  # 下一基础题

    def test_all_questions_done_enters_summarizing(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试全部题目答完：末期消费进入 summarizing、status=1（§12/§13.1）。"""
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        for idx in (1, 2, 3):
            resp = _submit(client, iid, idx, f"回答{idx}", epoch)
            assert resp.status_code == 200
            assert _consume(fake_redis, iid, idx, f"回答{idx}", epoch) is True
        # 末期消费后幂等重发：phase=summarizing、next 为空
        body = _submit(client, iid, 3, "重发", epoch).json()
        assert body["duplicated"] is True
        assert body["phase"] == "summarizing"
        assert body["next_question"] is None
        status_row = db_session.execute(
            text("SELECT status FROM interview WHERE id=:i"), {"i": iid}
        ).fetchone()
        assert status_row[0] == 1
        checkpoint = isess.load_checkpoint_sync(fake_redis, iid)
        assert checkpoint["phase"] in ("summarizing", "completed")

    def test_analysis_failure_skips_after_two_tries(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """测试同题连续2次 Fast Decision 失败：跳过追问推进下一题（§21）。

        Fast Decision 失败不计用户失败（分析异步化），仅跳过本次追问判定并继续。
        user_answer 仍落库；ai_score 由异步 Worker 后补。
        """
        monkeypatch.setattr(isvc.interview_service, "_publish_sse", lambda *a, **k: None)
        monkeypatch.setattr(isvc.interview_service, "_dispatch_async_analysis", lambda *a, **k: None)
        monkeypatch.setattr(isvc.interview_service, "_dispatch_report_generation", lambda *a, **k: None)

        calls = {"n": 0}

        def _flaky_stream(question: str, answer: str, resume_context: dict):
            """流式追问生成：前两次抛异常，第三次正常输出 NONE。"""
            calls["n"] += 1
            if calls["n"] <= 2:
                raise RuntimeError("LLM超时")
            yield "NONE"

        monkeypatch.setattr(isvc, "generate_questions", lambda ctx, t: QuestionGenerationResult(
            questions=[GeneratedQuestion(question_text="Q1", question_type=1, category=1),
                       GeneratedQuestion(question_text="Q2", question_type=1, category=1)]
        ))
        monkeypatch.setattr(isvc, "generate_follow_up_stream", _flaky_stream)
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]

        # 第一次受理 + 消费：追问流式生成失败（未达跳过阈值）→ 消费返回 False，
        # checkpoint 回退 answering 允许重新受理
        resp1 = _submit(client, iid, 1, "答案", epoch)
        assert resp1.status_code == 200
        assert resp1.json()["accepted"] is True
        assert _consume(fake_redis, iid, 1, "答案", epoch) is False
        checkpoint = isess.load_checkpoint_sync(fake_redis, iid)
        assert checkpoint["phase"] == "answering"
        # 重新受理（answering → 可再投事件）→ 第二次消费：失败达阈值 → 跳过追问继续落库
        resp2 = _submit(client, iid, 1, "答案", epoch)
        assert resp2.status_code == 200
        assert resp2.json()["accepted"] is True
        assert _consume(fake_redis, iid, 1, "答案", epoch) is True
        row = db_session.execute(
            text("SELECT ai_score, ai_comment, user_answer FROM interview_question "
                 "WHERE interview_id=:i AND question_no=1"), {"i": iid},
        ).fetchone()
        assert row[0] is None  # ai_score 由异步分析后补
        assert row[2] == "答案"  # user_answer 已落库
        # 第三次成功：Fast Decision 正常返回 next_base
        resp3 = _submit(client, iid, 2, "第二题答案", epoch)
        assert resp3.status_code == 200
        assert resp3.json()["accepted"] is True
        assert _consume(fake_redis, iid, 2, "第二题答案", epoch) is True


# --------------------------------------------------------------------------
# 状态查询 / 刷新恢复 / 双开接管（§5.6/§15）
# --------------------------------------------------------------------------

class TestStateAndRecovery:
    """状态查询与恢复测试。"""

    def test_state_refresh_same_tab_keeps_epoch(
        self, client: TestClient, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试刷新恢复：同tab_id（sessionStorage保留）epoch不变。"""
        created = _create_interview(client, ready_resume)
        iid = created["interview_id"]
        resp = client.get(f"/api/v1/interviews/{iid}?tab_id=tab-A")
        assert resp.status_code == 200
        assert resp.json()["epoch"] == 1

    def test_state_new_tab_takes_over(
        self, client: TestClient, fake_redis: FakeRedis, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试双开接管：新tab_id激活 → epoch+1，旧tab写请求被拒（§5.6/§5.8）。"""
        created = _create_interview(client, ready_resume)
        iid = created["interview_id"]
        # 复制标签页产生B：新tab_id → epoch=2
        resp = client.get(f"/api/v1/interviews/{iid}?tab_id=tab-B")
        assert resp.json()["epoch"] == 2
        # 旧tab A（epoch=1）提交 → 409
        denied = _submit(client, iid, 1, "旧tab回答", epoch=1)
        assert denied.status_code == 409
        assert denied.json()["detail"]["reason"] == "epoch_mismatch"
        # 新tab B（epoch=2）提交 → 成功
        ok = _submit(client, iid, 1, "新tab回答", epoch=2)
        assert ok.status_code == 200

    def test_checkpoint_rebuild_from_mysql(
        self, client: TestClient, fake_redis: FakeRedis, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试Checkpoint丢失由MySQL重建：恢复到第一道未答题目（§6.4/§15）。"""
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        _submit(client, iid, 1, "第一题回答", epoch)
        assert _consume(fake_redis, iid, 1, "第一题回答", epoch) is True
        # 模拟Redis故障丢失Checkpoint
        fake_redis.strings.pop(isess.checkpoint_key(iid), None)
        fake_redis.delete(isess.queue_key(iid))  # 队列一并丢失，验证 MySQL 重建兜底
        resp = client.get(f"/api/v1/interviews/{iid}")
        body = resp.json()
        assert body["question_index"] == 2  # 重建到第2题
        assert body["current_question"]["question_index"] == 2
        # 重建后可继续受理作答
        cont = _submit(client, iid, 2, "第二题回答", epoch)
        assert cont.status_code == 200
        assert cont.json()["accepted"] is True


# --------------------------------------------------------------------------
# 主动放弃 / 超时中断（§21）
# --------------------------------------------------------------------------

class TestAbort:
    """放弃与超时测试。"""

    def test_abort_marks_interrupted(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试主动放弃：status=2、已答数据保留、租约清理（§21）。"""
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        _submit(client, iid, 1, "已有回答", epoch)
        assert _consume(fake_redis, iid, 1, "已有回答", epoch) is True
        resp = client.post(f"/api/v1/interviews/{iid}/abort", json={"tab_epoch": epoch})
        assert resp.status_code == 204
        status_row = db_session.execute(
            text("SELECT status FROM interview WHERE id=:i"), {"i": iid}
        ).fetchone()
        assert status_row[0] == 2
        # 已答题目与评分保留
        answered = db_session.execute(
            text("SELECT COUNT(*) FROM interview_question WHERE interview_id=:i AND user_answer IS NOT NULL"),
            {"i": iid},
        ).scalar_one()
        assert answered == 1
        # 租约已清理
        assert isess.get_client_epoch_sync(fake_redis, iid) is None
        # 中断后不可再提交
        denied = _submit(client, iid, 2, "再回答", epoch)
        assert denied.status_code == 409

    def test_inactivity_timeout_auto_abort(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试30分钟无活动自动中断（§21）。"""
        from datetime import datetime, timedelta

        created = _create_interview(client, ready_resume)
        iid = created["interview_id"]
        # 先正式启动（草稿态 not_started 不参与无活动自动中断，§3；BUG3 后）
        resp = client.post(f"/api/v1/interviews/{iid}/start")
        assert resp.status_code == 200, resp.text
        # 将Checkpoint最后活动时间改写为35分钟前
        checkpoint = isess.load_checkpoint_sync(fake_redis, iid)
        checkpoint["last_activity_at"] = (
            datetime.now() - timedelta(minutes=35)
        ).isoformat()
        isess.save_checkpoint_sync(fake_redis, iid, checkpoint)
        resp = client.get(f"/api/v1/interviews/{iid}")
        assert resp.json()["status"] == 2
        assert resp.json()["phase"] == "aborted"


# --------------------------------------------------------------------------
# 报告（§13）
# --------------------------------------------------------------------------

class TestReport:
    """报告生成与查询测试。"""

    def _simulate_async_analysis(self, db_session: Session, iid: int) -> None:
        """模拟异步 Worker 已补齐各题 ai_score/ai_comment（§六）。

        报告生成前 _wait_analysis_complete 需等待 ai_score 落库；测试内无法
        跑真实 Worker，故直接写入各已答题评分，模拟异步分析已完成。
        """
        questions = db_session.execute(
            text("SELECT id FROM interview_question WHERE interview_id=:i AND user_answer IS NOT NULL"),
            {"i": iid},
        ).fetchall()
        for (qid,) in questions:
            db_session.execute(
                text("UPDATE interview_question SET ai_score=4, ai_comment='回答完整' WHERE id=:q"),
                {"q": qid},
            )
        db_session.commit()

    def _finish_interview(self, client: TestClient, fake_redis: FakeRedis, resume_id: int) -> int:
        """测试辅助：受理并消费完3题，使面试进入summarizing（v3）。"""
        created = _create_interview(client, resume_id)
        iid, epoch = created["interview_id"], created["epoch"]
        for idx in (1, 2, 3):
            resp = _submit(client, iid, idx, f"回答{idx}", epoch)
            assert resp.status_code == 200
            assert _consume(fake_redis, iid, idx, f"回答{idx}", epoch) is True
        return iid

    def test_report_generation_and_query(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试报告后台生成：落库、总分回写、phase=completed、查询ready（§13）。

        模拟异步分析已补齐评分后生成报告，避免 _wait_analysis_complete 长时间轮询。
        """
        iid = self._finish_interview(client, fake_redis, ready_resume)
        self._simulate_async_analysis(db_session, iid)
        # 直接同步执行后台任务（测试内不依赖线程）
        isvc.interview_service.generate_report_background(fake_redis, iid)
        resp = client.get(f"/api/v1/interviews/{iid}/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        report = body["report"]
        assert report["total_score"] == 85.5
        assert report["question_count"] == 3
        assert "整体表现良好" in report["summary"]
        # interview总分冗余回写（§14.4）
        row = db_session.execute(
            text("SELECT total_score, status FROM interview WHERE id=:i"), {"i": iid}
        ).fetchone()
        assert float(row[0]) == 85.5
        assert row[1] == 1
        # phase=completed + 租约清理（§14.4）
        checkpoint = isess.load_checkpoint_sync(fake_redis, iid)
        assert checkpoint["phase"] == "completed"
        assert isess.get_client_epoch_sync(fake_redis, iid) is None

    def test_report_generating_then_lazy_trigger(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试未生成时返回generating（§13.1）。

        GET /report 惰性兜底触发后台生成线程；因 ai_score 未补齐会在
        _wait_analysis_complete 内等待 60s，故此处先模拟补齐以免测试挂起。
        """
        iid = self._finish_interview(client, fake_redis, ready_resume)
        self._simulate_async_analysis(db_session, iid)
        resp = client.get(f"/api/v1/interviews/{iid}/report")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("generating", "ready")

    def test_report_invalid_before_finish(
        self, client: TestClient, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试面试未结束时查询报告返回invalid。"""
        created = _create_interview(client, ready_resume)
        resp = client.get(f"/api/v1/interviews/{created['interview_id']}/report")
        assert resp.json()["status"] == "invalid"

    def test_report_regenerate_conflict_when_not_finished(
        self, client: TestClient, ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试未完成面试regenerate返回409。"""
        created = _create_interview(client, ready_resume)
        resp = client.post(f"/api/v1/interviews/{created['interview_id']}/report/regenerate")
        assert resp.status_code == 409


# --------------------------------------------------------------------------
# v2·异步分析投递 + Fast Decision 即时判定（单LangGraph架构方案 v2）
# --------------------------------------------------------------------------

class TestV2AsyncAnalysis:
    """v3·受理化：受理事件投递 + Consumer 判题 / end 终止 / 追问防御回归。"""

    def test_submit_dispatches_answer_submitted_outbox(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """测试受理接口投递 interview.answer.submitted outbox 事件（T3.1）。

        桩化 outbox insert_event 捕获事件列表，校验受理事件类型与 payload。
        """
        events: list[dict] = []
        monkeypatch.setattr(
            isvc.sync_outbox_repository, "insert_event",
            lambda db, event_type, aggregate_type, aggregate_id, payload: events.append(
                {
                    "event_type": event_type,
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "payload": payload,
                }
            ) or 1,
        )
        monkeypatch.setattr(isvc.interview_service, "_wait_analysis_complete", lambda *a, **k: None)

        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        resp = _submit(client, iid, 1, "关于GIL的回答", epoch)
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True
        # 受理即投递 answer.submitted 事件（请求线程不再等判题）
        captured = events[0]
        assert captured["event_type"] == "interview.answer.submitted"
        assert captured["aggregate_type"] == "interview"
        assert captured["aggregate_id"] == str(iid)
        payload = captured["payload"]
        assert payload["interview_id"] == iid
        assert payload["answer"] == "关于GIL的回答"
        assert payload["priority_ref"].startswith(f"interview:{iid}:q")
        # 受理请求本身不再产生 analysis 事件（判题在消费端）
        assert len(events) == 1

    def test_finish_dispatches_report_generation_outbox(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """测试末题消费进入 summarizing 时投递 report 生成 outbox 事件（§13.1）。

        桩化 outbox insert_event 捕获事件列表，断言末题 finish 同事务投递
        interview.report.generate（MQ 异步化链路不变）。
        """
        events: list[dict] = []
        monkeypatch.setattr(
            isvc.sync_outbox_repository, "insert_event",
            lambda db, event_type, aggregate_type, aggregate_id, payload: events.append(
                {
                    "event_type": event_type,
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "payload": payload,
                }
            ) or 1,
        )
        monkeypatch.setattr(isvc.interview_service, "_wait_analysis_complete", lambda *a, **k: None)
        # stub_llm 默认桩化了两类 outbox 投递；本用例恢复真实投递以捕获 report 事件
        monkeypatch.setattr(
            isvc.interview_service, "_dispatch_async_analysis",
            isvc.InterviewService._dispatch_async_analysis.__get__(isvc.interview_service),
        )
        monkeypatch.setattr(
            isvc.interview_service, "_dispatch_report_generation",
            isvc.InterviewService._dispatch_report_generation.__get__(isvc.interview_service),
        )

        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        for idx in (1, 2, 3):
            resp = _submit(client, iid, idx, f"对第{idx}题的回答", epoch)
            assert resp.status_code == 200
            assert _consume(fake_redis, iid, idx, f"对第{idx}题的回答", epoch) is True
        # 末题 finish：report 事件正确投递（与 finish 同事务）
        report_events = [e for e in events if e["event_type"] == "interview.report.generate"]
        assert report_events, events
        captured = report_events[0]
        assert captured["aggregate_type"] == "interview"
        assert captured["aggregate_id"] == str(iid)
        payload = captured["payload"]
        assert payload["interview_id"] == iid
        assert payload["user_id"] == 1
        assert payload["resume_id"] == ready_resume
        # 每题消费均投递 analysis 事件（3 题）
        analysis_events = [e for e in events if e["event_type"] == "interview.analysis"]
        assert len(analysis_events) == 3

    def test_fast_decision_end_terminates(
        self, client: TestClient, db_session: Session, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试 Fast Decision 判定 end 且无剩余基础题 → summarizing（§12/§四）。

        路由节点防御：fast 判 end 但仍有未答基础题时回退 next_base（防误中断）；
        只有末题（unanswered_after=0）才真正终止。
        """
        stub_llm["follow_up_behavior"] = {"text": None}  # NONE：无追问（问尽由规则判定）
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        for idx in (1, 2, 3):
            resp = _submit(client, iid, idx, f"对第{idx}题的回答", epoch)
            assert resp.status_code == 200
            assert resp.json()["accepted"] is True
            assert _consume(fake_redis, iid, idx, f"对第{idx}题的回答", epoch) is True
        # 末题：fast 判 end 且无剩余 → summarizing（消费后幂等复用可见）
        r3 = _submit(client, iid, 3, "对第三题的回答", epoch).json()
        assert r3["duplicated"] is True
        assert r3["phase"] == "summarizing"
        assert r3["next_question"] is None

    def test_follow_up_without_text_falls_back_to_next_base(
        self, client: TestClient, fake_redis: FakeRedis,
        ready_resume: int, stub_llm: dict,
    ) -> None:
        """测试追问生成输出为空/无文本 → 回退下一基础题（NONE 语义）。"""
        stub_llm["follow_up_behavior"] = {"text": None}  # NONE：无追问
        created = _create_interview(client, ready_resume)
        iid, epoch = created["interview_id"], created["epoch"]
        _submit(client, iid, 1, "浅回答", epoch)
        assert _consume(fake_redis, iid, 1, "浅回答", epoch) is True
        body = _submit(client, iid, 1, "重发", epoch).json()
        assert body["duplicated"] is True
        assert body["next_question"]["is_follow_up"] is False
        assert body["next_question"]["question_index"] == 2


# --------------------------------------------------------------------------
# Redis 层单元测试（§5/§6）
# --------------------------------------------------------------------------

class TestRedisSessionModule:
    """Redis面试会话模块（锁/租约/Checkpoint）语义测试。"""

    def test_lock_acquire_release(self, fake_redis: FakeRedis) -> None:
        """测试操作锁互斥与compare-and-del释放（§5.4）。"""
        token = isess.generate_lock_token()
        assert isess.acquire_lock_sync(fake_redis, 42, token) is True
        # 互斥：他人无法获取
        assert isess.acquire_lock_sync(fake_redis, 42, "other") is False
        # 误删保护：值不匹配释放失败
        assert isess.release_lock_sync(fake_redis, 42, "wrong") is False
        assert isess.release_lock_sync(fake_redis, 42, token) is True
        # 释放后可重新获取
        assert isess.acquire_lock_sync(fake_redis, 42, "next") is True

    def test_client_lease_epoch_semantics(self, fake_redis: FakeRedis) -> None:
        """测试客户端租约：同tab幂等、新tab接管epoch+1（§5.6）。"""
        assert isess.activate_client_sync(fake_redis, 7, "tab-A") == 1
        assert isess.activate_client_sync(fake_redis, 7, "tab-A") == 1  # 同tab幂等
        assert isess.activate_client_sync(fake_redis, 7, "tab-B") == 2  # 新tab接管
        assert isess.activate_client_sync(fake_redis, 7, "tab-B") == 2
        assert isess.activate_client_sync(fake_redis, 7, "tab-A") == 3  # A回归再接管
        assert isess.get_client_epoch_sync(fake_redis, 7) == 3
        isess.clear_client_sync(fake_redis, 7)
        assert isess.get_client_epoch_sync(fake_redis, 7) is None

    def test_checkpoint_roundtrip(self, fake_redis: FakeRedis) -> None:
        """测试Checkpoint读写删往返（§6.2）。"""
        state = {"phase": "answering", "question_index": 3, "epoch": 2}
        isess.save_checkpoint_sync(fake_redis, 9, state)
        loaded = isess.load_checkpoint_sync(fake_redis, 9)
        assert loaded == state
        isess.delete_checkpoint_sync(fake_redis, 9)
        assert isess.load_checkpoint_sync(fake_redis, 9) is None
