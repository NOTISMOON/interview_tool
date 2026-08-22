"""上传模块测试夹具：内存SQLite + FakeRedis + COS桩 + 依赖注入覆盖。

说明:
    - ORM模型的updated_at含MySQL专有"ON UPDATE CURRENT_TIMESTAMP"子句，无法直接
      在SQLite上create_all，故手动执行SQLite兼容DDL建表。
    - FakeRedis仅实现上传服务用到的方法（incr/expire/hset/hgetall）。
    - COS客户端为模块级单例，通过monkeypatch替换其方法属性实现桩化。
"""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db, get_redis
from app.api.v1.controllers.upload import router as upload_router
from app.cos import cos_client

# SQLite兼容的upload_records建表语句（不含MySQL专有ON UPDATE子句）
_UPLOAD_RECORDS_DDL = """
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
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

# SQLite兼容的resume建表语句（删除上传记录联动软删除简历时查询用）
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


class FakeRedis:
    """内存版Redis桩，实现上传服务用到的最小接口。"""

    def __init__(self) -> None:
        """初始化内存存储结构。"""
        self.strings: dict[str, int] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        """自增计数器并返回新值。"""
        self.strings[key] = self.strings.get(key, 0) + 1
        return self.strings[key]

    def expire(self, key: str, seconds: int) -> bool:
        """记录键的TTL（仅记录不实现过期）。"""
        self.ttls[key] = seconds
        return True

    def hset(self, key: str, *args: object, mapping: dict | None = None) -> int:
        """写入Hash字段，兼容(field, value)与mapping两种签名。"""
        if mapping is not None:
            self.hashes.setdefault(key, {}).update({str(k): str(v) for k, v in mapping.items()})
            return len(mapping)
        if len(args) == 2:
            field, value = args
            self.hashes.setdefault(key, {})[str(field)] = str(value)
            return 1
        raise ValueError("FakeRedis.hset参数非法")

    def hgetall(self, key: str) -> dict[str, str]:
        """读取整个Hash，不存在返回空字典。"""
        return dict(self.hashes.get(key, {}))


@pytest.fixture()
def db_session() -> Session:
    """提供每个测试独立的内存SQLite会话（自动建upload_records表）。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text(_UPLOAD_RECORDS_DDL))
        conn.execute(text(_RESUME_DDL))
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
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
    """当前认证用户ID（依赖注入覆盖返回的JWT载荷sub）。"""
    return 1


@pytest.fixture()
def client(db_session: Session, fake_redis: FakeRedis, auth_user_id: int) -> TestClient:
    """构建挂载上传路由的测试客户端（覆盖DB/Redis/认证三项依赖）。"""

    def _override_get_db():
        """复用测试会话的get_db覆盖（会话生命周期由fixture管理）。"""
        yield db_session

    def _override_get_redis() -> FakeRedis:
        """返回FakeRedis。"""
        return fake_redis

    def _override_get_current_user() -> dict:
        """返回固定测试用户的JWT载荷。"""
        return {"sub": str(auth_user_id)}

    test_app = FastAPI()
    api = APIRouter(prefix="/api/v1")
    api.include_router(upload_router)
    test_app.include_router(api)
    test_app.dependency_overrides[get_db] = _override_get_db
    test_app.dependency_overrides[get_redis] = _override_get_redis
    test_app.dependency_overrides[get_current_user] = _override_get_current_user
    return TestClient(test_app)


@pytest.fixture()
def mock_sts(monkeypatch: pytest.MonkeyPatch) -> None:
    """桩掉COS客户端的STS临时密钥生成，返回固定凭证。"""

    def _fake_get_sts(resource_prefix: str) -> dict:
        """返回固定测试凭证。"""
        return {
            "tmp_secret_id": "AKIDTEST",
            "tmp_secret_key": "TESTKEY",
            "session_token": "TESTTOKEN",
            "expired_time": 1893456000,
        }

    monkeypatch.setattr(cos_client, "get_sts_credentials", _fake_get_sts)


@pytest.fixture()
def mock_head_object(monkeypatch: pytest.MonkeyPatch) -> dict:
    """桩掉COS HEAD Object校验，返回可修改的元数据holder。"""
    holder: dict = {
        "meta": {"content_length": 204800, "content_type": "application/pdf", "etag": "abc123def456"}
    }

    def _fake_head(cos_key: str) -> dict | None:
        """返回holder中设定的元数据。"""
        return holder["meta"]

    monkeypatch.setattr(cos_client, "head_object", _fake_head)
    return holder


@pytest.fixture()
def mock_delete_object(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """桩掉COS删除对象，记录调用参数供断言。"""
    calls: list[str] = []

    def _fake_delete(cos_key: str) -> bool:
        """记录删除调用并返回成功。"""
        calls.append(cos_key)
        return True

    monkeypatch.setattr(cos_client, "delete_object", _fake_delete)
    return calls


@pytest.fixture()
def stub_resume_link(monkeypatch: pytest.MonkeyPatch) -> dict:
    """桩掉上传回调内的简历联动（去重+调度），隔离上传模块自身测试。

    返回holder记录联动调用参数，返回值模拟"新建简历并已调度"。
    """
    from app.services.resume_service import resume_service

    holder: dict = {"calls": []}

    def _fake_on_uploaded(db, cache_client, user_id, cos_key, file_name, file_size):
        """记录调用并返回固定的简历联动结果。"""
        holder["calls"].append({"user_id": user_id, "cos_key": cos_key, "file_name": file_name})
        return {"resume_id": 101, "created": True, "status": 0, "scheduled": True}

    monkeypatch.setattr(resume_service, "on_resume_uploaded", _fake_on_uploaded)
    return holder
