"""简历模块单元测试：去重/份数上限/调度（锁+Outbox）/解析结果落库/锁语义。

覆盖《简历上传分析功能文档》M1 核心链路（LLM调用除外，Worker内已隔离）。
"""

import asyncio
import hashlib

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cos import cos_client
from app.llm.schemas.resume import ResumeExtraction
from app.models.outbox_event import OutboxEvent
from app.models.resume import RESUME_STATUS_READY, Resume
from app.models.resume_work_experience import ResumeWorkExperience
from app.redis import resume_lock
from app.repositories.resume_repository import resume_repository
from app.services.resume_service import (
    MAX_ACTIVE_RESUMES,
    ResumeLimitExceededError,
    ResumeNotFoundError,
    ResumeNotRetryableError,
    resume_service,
)

# SQLite兼容DDL（不含MySQL专有ON UPDATE子句）
_RESUME_DDL = """
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
"""

_WORK_EXPERIENCE_DDL = """
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
"""

_OUTBOX_DDL = """
CREATE TABLE outbox_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type VARCHAR(50) NOT NULL,
    aggregate_type VARCHAR(50) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    payload JSON NOT NULL,
    status INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    published_at DATETIME
)
"""

_UPLOAD_RECORD_DDL = """
CREATE TABLE upload_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    cos_key VARCHAR(500) NOT NULL,
    cos_url VARCHAR(1000) NOT NULL,
    etag VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    error_message VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

# 模拟的简历文件内容（两个不同文件）
_FILE_A = b"resume-content-A" * 10
_FILE_B = b"resume-content-B" * 10
_HASH_A = hashlib.sha256(_FILE_A).hexdigest()


class LockRedis:
    """支持简历分析锁语义的内存Redis桩（set NX EX / get / compare-and-del eval）。"""

    def __init__(self) -> None:
        """初始化字符串存储。"""
        self.strings: dict[str, str] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        """SET语义：nx=True时键已存在返回False。"""
        if nx and key in self.strings:
            return False
        self.strings[key] = value
        return True

    def get(self, key: str) -> str | None:
        """GET语义。"""
        return self.strings.get(key)

    def eval(self, script: str, numkeys: int, key: str, arg: str) -> int:
        """模拟compare-and-del Lua脚本：值匹配才删除。"""
        if self.strings.get(key) == arg:
            del self.strings[key]
            return 1
        return 0

    def delete(self, *keys: str) -> int:
        """DELETE语义（支持多键，无条件清除，幂等：不存在返回0）。"""
        count = 0
        for key in keys:
            if key in self.strings:
                del self.strings[key]
                count += 1
        return count


class AsyncLockRedis(LockRedis):
    """异步版锁Redis桩（await语义）。"""

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        """异步SET语义。"""
        return super().set(key, value, nx=nx, ex=ex)

    async def get(self, key: str) -> str | None:
        """异步GET语义。"""
        return super().get(key)

    async def eval(self, script: str, numkeys: int, key: str, arg: str) -> int:
        """异步compare-and-del语义。"""
        return super().eval(script, numkeys, key, arg)


@pytest.fixture()
def db_session() -> Session:
    """提供每个测试独立的内存SQLite会话（自动建resume相关三张表）。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text(_RESUME_DDL))
        conn.execute(text(_WORK_EXPERIENCE_DDL))
        conn.execute(text(_OUTBOX_DDL))
        conn.execute(text(_UPLOAD_RECORD_DDL))
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def lock_redis() -> LockRedis:
    """提供干净的锁Redis桩。"""
    return LockRedis()


@pytest.fixture()
def mock_cos_bytes(monkeypatch: pytest.MonkeyPatch) -> dict:
    """桩掉COS对象下载，按cos_key返回模拟文件内容。"""
    holder: dict = {"store": {}}

    def _fake_get(cos_key: str) -> bytes | None:
        """返回桩内容，未登记的key返回None（模拟404）。"""
        return holder["store"].get(cos_key)

    monkeypatch.setattr(cos_client, "get_object_bytes", _fake_get)
    return holder


def _upload(db: Session, cache: LockRedis, user_id: int, cos_key: str, content: bytes) -> dict:
    """便捷调用：模拟一次简历上传联动。"""
    return resume_service.on_resume_uploaded(
        db, cache, user_id, cos_key, f"{cos_key.rsplit('/', 1)[-1]}", len(content)
    )


# ---------------------------------------------------------------------------
# 简历联动：去重 / 创建 / 调度
# ---------------------------------------------------------------------------

def test_first_upload_creates_resume_and_schedules(db_session, lock_redis, mock_cos_bytes):
    """测试首次上传：创建简历（status=0）+ 抢锁 + 写Outbox事件。"""
    mock_cos_bytes["store"]["resumes/1/a.pdf"] = _FILE_A
    out = _upload(db_session, lock_redis, 1, "resumes/1/a.pdf", _FILE_A)

    assert out["created"] is True
    assert out["status"] == 0
    assert out["scheduled"] is True

    # 简历记录已落库，file_hash为SHA256
    resume = db_session.execute(select(Resume)).scalars().one()
    assert resume.user_id == 1
    assert resume.file_hash == _HASH_A
    assert resume.status == 0
    assert out["resume_id"] == resume.id

    # Outbox事件已写入且payload完整（Relay投递依据）
    event = db_session.execute(select(OutboxEvent)).scalars().one()
    assert event.event_type == "resume.parse"
    assert event.aggregate_type == "resume"
    assert event.payload["resume_id"] == resume.id
    assert event.payload["user_id"] == 1
    assert event.payload["task_uuid"]
    assert event.payload["cos_key"] == "resumes/1/a.pdf"

    # 分析锁已被调度侧持有（值=事件中的task_uuid）
    assert lock_redis.get(resume_lock.lock_key(resume.id)) == event.payload["task_uuid"]


def test_duplicate_upload_reuses_resume_without_new_record(db_session, lock_redis, mock_cos_bytes):
    """测试重复上传同一文件：命中去重复用，不新增记录、不重复投递（锁已持有）。"""
    mock_cos_bytes["store"]["resumes/1/a.pdf"] = _FILE_A
    first = _upload(db_session, lock_redis, 1, "resumes/1/a.pdf", _FILE_A)
    # 模拟Worker完成：释放锁 + 状态置就绪
    resume_id = first["resume_id"]
    lock_redis.strings.pop(resume_lock.lock_key(resume_id))
    db_session.execute(
        text("UPDATE resume SET status = 1 WHERE id = :rid"), {"rid": resume_id}
    )
    db_session.commit()

    second = _upload(db_session, lock_redis, 1, "resumes/1/a.pdf", _FILE_A)
    assert second["created"] is False
    assert second["resume_id"] == resume_id
    assert second["status"] == RESUME_STATUS_READY
    # 已就绪 → 不重新调度、不新增Outbox事件
    assert second["scheduled"] is False
    assert db_session.execute(select(OutboxEvent)).scalars().first() is not None
    events = db_session.execute(select(OutboxEvent)).scalars().all()
    assert len(events) == 1


def test_duplicate_upload_while_parsing_skips_reschedule(db_session, lock_redis, mock_cos_bytes):
    """测试解析中重复上传：复用记录，但锁被持有时跳过重复投递（自愈不叠加任务）。"""
    mock_cos_bytes["store"]["resumes/1/a.pdf"] = _FILE_A
    first = _upload(db_session, lock_redis, 1, "resumes/1/a.pdf", _FILE_A)

    second = _upload(db_session, lock_redis, 1, "resumes/1/a.pdf", _FILE_A)
    assert second["created"] is False
    assert second["resume_id"] == first["resume_id"]
    assert second["scheduled"] is False
    # 仍只有一条Outbox事件（首次调度写入）
    events = db_session.execute(select(OutboxEvent)).scalars().all()
    assert len(events) == 1


def test_failed_resume_reupload_refreshes_file_url_and_reschedules(db_session, lock_redis, mock_cos_bytes):
    """测试失败简历重新上传：刷新file_url指向新COS对象、重置状态并重新调度。

    回归场景：旧对象已随上传记录删除（解析404），用户重新上传同一文件内容
    到新cos_key，去重命中后必须改指新对象地址，否则Worker仍解析旧地址必404。
    """
    from app.cos import build_cos_url

    mock_cos_bytes["store"]["resumes/1/a.pdf"] = _FILE_A
    first = _upload(db_session, lock_redis, 1, "resumes/1/a.pdf", _FILE_A)
    resume_id = first["resume_id"]

    # 模拟首次解析失败：锁释放 + 状态置2 + 旧COS对象已删（store移除）
    lock_redis.strings.pop(resume_lock.lock_key(resume_id))
    db_session.execute(
        text("UPDATE resume SET status = 2, error_message = 'ValueError: 404' WHERE id = :rid"),
        {"rid": resume_id},
    )
    db_session.commit()
    mock_cos_bytes["store"].pop("resumes/1/a.pdf")

    # 同一文件内容重新上传到新cos_key
    mock_cos_bytes["store"]["resumes/1/new-key.pdf"] = _FILE_A
    second = _upload(db_session, lock_redis, 1, "resumes/1/new-key.pdf", _FILE_A)
    assert second["created"] is False
    assert second["resume_id"] == resume_id
    assert second["scheduled"] is True
    assert second["status"] == 0  # 重置回解析中

    # file_url 已刷新为新对象地址，错误信息已清空
    db_session.expire_all()
    resume = db_session.get(Resume, resume_id)
    assert resume.file_url == build_cos_url("resumes/1/new-key.pdf")
    assert resume.error_message is None
    assert resume.status == 0

    # 新调度事件携带新cos_key（Worker按它构建下载地址）
    events = db_session.execute(select(OutboxEvent)).scalars().all()
    assert len(events) == 2
    assert events[-1].payload["cos_key"] == "resumes/1/new-key.pdf"


def test_quota_exceeded_returns_conflict_error(db_session, lock_redis, mock_cos_bytes):
    """测试份数上限：已有6份未删除简历时第7份返回ResumeLimitExceededError(409)。"""
    # 直接造满6份active简历（不同hash）
    for i in range(MAX_ACTIVE_RESUMES):
        db_session.execute(
            text(
                "INSERT INTO resume (user_id, file_name, file_hash, status) "
                "VALUES (1, :name, :hash, 1)"
            ),
            {"name": f"r{i}.pdf", "hash": f"hash-{i}"},
        )
    db_session.commit()

    mock_cos_bytes["store"]["resumes/1/new.pdf"] = _FILE_B
    with pytest.raises(ResumeLimitExceededError) as exc_info:
        _upload(db_session, lock_redis, 1, "resumes/1/new.pdf", _FILE_B)
    assert "上限" in str(exc_info.value)


def test_soft_deleted_resume_not_counted_and_not_matched(db_session, lock_redis, mock_cos_bytes):
    """测试软删除联动：已删除简历不计份数、不参与去重（file_hash置空）。"""
    db_session.execute(
        text(
            "INSERT INTO resume (user_id, file_name, file_hash, status, is_deleted) "
            "VALUES (1, 'old.pdf', NULL, 1, 1)"
        )
    )
    db_session.commit()

    mock_cos_bytes["store"]["resumes/1/a.pdf"] = _FILE_A
    out = _upload(db_session, lock_redis, 1, "resumes/1/a.pdf", _FILE_A)
    # 软删除记录不命中去重，正常创建新简历
    assert out["created"] is True


# ---------------------------------------------------------------------------
# Worker侧落库：解析结果 / 失败标记
# ---------------------------------------------------------------------------

def _seed_resume(db: Session, status: int = 0) -> int:
    """插入一条测试简历并返回ID。"""
    result = db.execute(
        text(
            "INSERT INTO resume (user_id, file_name, file_hash, status) "
            "VALUES (1, 'a.pdf', :hash, :status)"
        ),
        {"hash": _HASH_A, "status": status},
    )
    db.commit()
    return int(result.lastrowid)


def test_save_parsed_result_replaces_work_experience(db_session):
    """测试解析结果落库：状态置就绪、字段写入、工作经历先清后插。"""
    resume_id = _seed_resume(db_session)
    db_session.execute(
        text(
            "INSERT INTO resume_work_experience (resume_id, company, role, duration) "
            "VALUES (:rid, '旧公司', '旧职位', '2018-2020')"
        ),
        {"rid": resume_id},
    )
    db_session.commit()

    extraction = ResumeExtraction(
        name="张三",
        skills=["Python", "FastAPI"],
        education=[{"school": "某某大学", "degree": "本科", "major": "计算机", "duration": "2016-2020"}],
        projects=[{"name": "AI面试系统", "description": "负责后端", "tech_stack": ["FastAPI", "MySQL"]}],
        work_experience=[
            {"company": "新公司", "role": "后端工程师", "duration": "2020-至今", "description": "开发"},
        ],
    )
    resume_repository.save_parsed_result(
        db_session,
        resume_id=resume_id,
        name=extraction.name,
        skills=list(extraction.skills),
        education=[item.model_dump() for item in extraction.education],
        projects=[item.model_dump() for item in extraction.projects],
        work_experiences=[item.model_dump() for item in extraction.work_experience],
    )

    resume = db_session.get(Resume, resume_id)
    assert resume.status == RESUME_STATUS_READY
    assert resume.parsed_name == "张三"
    assert resume.parsed_skills == ["Python", "FastAPI"]
    assert resume.parsed_projects[0]["name"] == "AI面试系统"
    assert resume.error_message is None

    works = (
        db_session.execute(
            select(ResumeWorkExperience).where(ResumeWorkExperience.resume_id == resume_id)
        )
        .scalars()
        .all()
    )
    # 旧工作经历被替换
    assert len(works) == 1
    assert works[0].company == "新公司"
    assert works[0].sort_order == 0


def test_save_parsed_result_normalizes_null_work_fields(db_session):
    """测试LLM返回显式null的工作经历字段落库时归一为空串（company/role/duration为NOT NULL）。"""
    resume_id = _seed_resume(db_session)
    extraction = ResumeExtraction(
        name="张三",
        skills=["Python"],
        education=[],
        projects=[],
        work_experience=[
            # LLM json_mode 显式输出 null，对应 resume_work_experience 表 NOT NULL 列
            {"company": None, "role": "后端工程师", "duration": None, "description": "开发"},
        ],
    )
    resume_repository.save_parsed_result(
        db_session,
        resume_id=resume_id,
        name=extraction.name,
        skills=list(extraction.skills),
        education=[item.model_dump() for item in extraction.education],
        projects=[item.model_dump() for item in extraction.projects],
        work_experiences=[item.model_dump() for item in extraction.work_experience],
    )
    # 不抛异常、状态就绪，且 company/duration 被落为空串而非 None/NULL
    assert db_session.get(Resume, resume_id).status == RESUME_STATUS_READY
    works = (
        db_session.execute(
            select(ResumeWorkExperience).where(ResumeWorkExperience.resume_id == resume_id)
        )
        .scalars()
        .all()
    )
    assert len(works) == 1
    assert works[0].company == ""
    assert works[0].role == "后端工程师"
    assert works[0].duration == ""
    assert works[0].description == "开发"


def test_mark_parse_failed_sets_status_and_message(db_session):
    """测试失败标记：status=2且error_message截断到512。"""
    resume_id = _seed_resume(db_session)
    resume_repository.mark_parse_failed(db_session, resume_id, "X" * 600)

    resume = db_session.get(Resume, resume_id)
    assert resume.status == 2
    assert len(resume.error_message) == 512


# ---------------------------------------------------------------------------
# 独立删除接口（M3）与失败一键重试（M4）
# ---------------------------------------------------------------------------

def test_delete_resume_soft_deletes_and_cleans_up(db_session, lock_redis, mock_cos_bytes, monkeypatch):
    """测试独立删除简历：软删resume + 物理删上传记录 + 删COS对象 + 清缓存/锁。"""
    from app.cos import build_cos_url, cos_client

    # 桩掉COS对象删除（避免真实网络调用）
    deleted_keys: list[str] = []
    monkeypatch.setattr(cos_client, "delete_object", lambda key: deleted_keys.append(key) or True)

    cos_key = "resumes/1/del.pdf"
    mock_cos_bytes["store"][cos_key] = _FILE_A
    created = _upload(db_session, lock_redis, 1, cos_key, _FILE_A)
    resume_id = created["resume_id"]

    # 造一条关联上传记录（cos_url 与 resume.file_url 一致），供删除联动清理
    file_url = build_cos_url(cos_key)
    db_session.execute(
        text(
            "INSERT INTO upload_records (user_id, file_type, file_name, file_size, content_type, "
            "cos_key, cos_url, etag, status) "
            "VALUES (1, 'resume', 'del.pdf', 100, 'application/pdf', :key, :url, 'etag1', 'completed')"
        ),
        {"key": cos_key, "url": file_url},
    )
    db_session.commit()

    # 模拟分析锁已被持有（删除时应无条件清除）
    lock_redis.strings[resume_lock.lock_key(resume_id)] = "stale-uuid"

    resume_service.delete_resume(db_session, lock_redis, 1, resume_id)

    # 软删除标记：is_deleted=1、file_hash 释放
    db_session.expire_all()
    resume = db_session.get(Resume, resume_id)
    assert resume.is_deleted == 1
    assert resume.file_hash is None
    assert resume.deleted_at is not None
    # 上传记录被物理删除
    records = db_session.execute(text("SELECT COUNT(*) FROM upload_records")).scalar_one()
    assert records == 0
    # COS 对象被删除
    assert "resumes/1/del.pdf" in deleted_keys
    # 分析锁被清除
    assert lock_redis.get(resume_lock.lock_key(resume_id)) is None


def test_delete_resume_wrong_user_raises_not_found(db_session, lock_redis):
    """测试删除越权：他人简历删除时抛 ResumeNotFoundError（路由层转404）。"""
    seed_id = db_session.execute(
        text(
            "INSERT INTO resume (user_id, file_name, file_hash, status) "
            "VALUES (2, 'a.pdf', 'hash-x', 1)"
        )
    ).lastrowid
    db_session.commit()

    with pytest.raises(ResumeNotFoundError):
        resume_service.delete_resume(db_session, lock_redis, 1, seed_id)


def test_delete_resume_idempotent(db_session, lock_redis):
    """测试删除幂等：重复删除同一简历返回 NotFound（第二次软删无匹配）。"""
    seed_id = db_session.execute(
        text(
            "INSERT INTO resume (user_id, file_name, file_hash, status, is_deleted) "
            "VALUES (1, 'a.pdf', 'hash-y', 1, 1)"
        )
    ).lastrowid
    db_session.commit()

    with pytest.raises(ResumeNotFoundError):
        resume_service.delete_resume(db_session, lock_redis, 1, seed_id)


def test_retry_analysis_only_failed_resumes(db_session, lock_redis):
    """测试一键重试：仅 status=2 可重试；就绪(1)记录抛 ResumeNotRetryableError。"""
    seed_id = db_session.execute(
        text(
            "INSERT INTO resume (user_id, file_name, file_hash, status) "
            "VALUES (1, 'a.pdf', 'hash-r', 1)"
        )
    ).lastrowid
    db_session.commit()

    with pytest.raises(ResumeNotRetryableError):
        resume_service.retry_analysis(db_session, lock_redis, 1, seed_id)


def test_retry_analysis_resets_and_reschedules(db_session, lock_redis, mock_cos_bytes):
    """测试失败简历一键重试：重置为解析中 + 清除残留锁 + 重新调度（Outbox事件+1）。"""
    from app.cos import build_cos_url

    cos_key = "resumes/1/retry.pdf"
    mock_cos_bytes["store"][cos_key] = _FILE_A
    created = _upload(db_session, lock_redis, 1, cos_key, _FILE_A)
    resume_id = created["resume_id"]

    # 模拟解析失败：释放首次锁 + 置 status=2
    lock_redis.strings.pop(resume_lock.lock_key(resume_id))
    db_session.execute(
        text("UPDATE resume SET status = 2, error_message = 'LLM timeout' WHERE id = :rid"),
        {"rid": resume_id},
    )
    db_session.commit()
    # 模拟残留锁（重试应无条件清除后再抢新锁）
    lock_redis.strings[resume_lock.lock_key(resume_id)] = "stale"

    out = resume_service.retry_analysis(db_session, lock_redis, 1, resume_id)

    assert out.status == 0  # 解析中
    assert out.error_message is None
    # 新锁已写入（值=最新 Outbox 事件的 task_uuid）
    events = db_session.execute(select(OutboxEvent)).scalars().all()
    assert len(events) == 2
    assert lock_redis.get(resume_lock.lock_key(resume_id)) == events[-1].payload["task_uuid"]
    assert events[-1].payload["cos_key"] == cos_key


# ---------------------------------------------------------------------------
# 锁语义（同步/异步）
# ---------------------------------------------------------------------------

def test_lock_acquire_verify_release_sync(lock_redis):
    """测试同步锁：抢锁→校验→compare-and-del释放。"""
    assert resume_lock.acquire_sync(lock_redis, 1, "uuid-1") is True
    assert resume_lock.verify_sync(lock_redis, 1, "uuid-1") is True
    assert resume_lock.release_sync(lock_redis, 1, "uuid-1") is True
    # 释放后可再次抢锁（自愈重试路径）
    assert resume_lock.acquire_sync(lock_redis, 1, "uuid-2") is True


def test_lock_acquire_fails_when_held_and_release_only_own_value(lock_redis):
    """测试锁互斥与误删保护：他人持有时抢锁失败，错误uuid释放不生效。"""
    resume_lock.acquire_sync(lock_redis, 1, "uuid-1")
    # 互斥：第二个任务抢锁失败
    assert resume_lock.acquire_sync(lock_redis, 1, "uuid-2") is False
    # 误删保护：uuid-2无法释放uuid-1的锁
    assert resume_lock.release_sync(lock_redis, 1, "uuid-2") is False
    assert resume_lock.verify_sync(lock_redis, 1, "uuid-1") is True


def test_lock_async_semantics():
    """测试异步锁：verify/释放与同步操作同一键值语义一致。"""
    async def _run() -> tuple[bool, bool, bool]:
        """异步执行锁校验与释放并返回三步结果。"""
        client = AsyncLockRedis()
        ok_acquire = await resume_lock.acquire_async(client, 2, "uuid-a")
        ok_verify = await resume_lock.verify_async(client, 2, "uuid-a")
        ok_release = await resume_lock.release_async(client, 2, "uuid-a")
        return ok_acquire, ok_verify, ok_release

    acquire_ok, verify_ok, release_ok = asyncio.run(_run())
    assert (acquire_ok, verify_ok, release_ok) == (True, True, True)


# ---------------------------------------------------------------------------
# 面试读取契约（M3）：详情读取 = status轮询 + 归属校验（蓝图§6.3 读取路径）
# ---------------------------------------------------------------------------

def test_read_contract_detail_with_ownership_check(db_session, lock_redis, mock_cos_bytes):
    """测试读取契约：本人可读详情与该简历status（供面试模块轮询）；他人读抛404。"""
    from app.cos import build_cos_url

    cos_key = "resumes/1/read.pdf"
    mock_cos_bytes["store"][cos_key] = _FILE_A
    created = _upload(db_session, lock_redis, 1, cos_key, _FILE_A)
    resume_id = created["resume_id"]

    # 本人可读（归属校验通过，status=0 供前端轮询）
    out = resume_service.get_resume(db_session, 1, resume_id)
    assert out.id == resume_id
    assert out.status == 0

    # 他人/不存在退回 404
    with pytest.raises(ResumeNotFoundError):
        resume_service.get_resume(db_session, 2, resume_id)
    with pytest.raises(ResumeNotFoundError):
        resume_service.get_resume(db_session, 1, 99999)


# ---------------------------------------------------------------------------
# LLM输出Schema校验（蓝图§5.5）
# ---------------------------------------------------------------------------

def test_resume_extraction_schema_accepts_partial_llm_output():
    """测试LLM部分输出：缺失字段以默认值兜底，不抛异常。"""
    extraction = ResumeExtraction.model_validate({"name": "李四"})
    assert extraction.name == "李四"
    assert extraction.skills == []
    assert extraction.education == []
    assert extraction.projects == []
    assert extraction.work_experience == []


def test_resume_extraction_schema_rejects_wrong_type():
    """测试LLM非法输出：字段类型错误时Pydantic校验拦截。"""
    with pytest.raises(Exception):
        ResumeExtraction.model_validate({"skills": "not-a-list"})
