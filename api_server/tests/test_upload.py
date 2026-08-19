"""文件上传模块接口单元测试（覆盖文档10.1要求的4个端点全部场景）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.cos import format_upload_date
from app.models.upload_record import UploadRecord

# 测试用常量
_FILE_NAME = "我的简历.pdf"
_FILE_SIZE = 204800
_CONTENT_TYPE = "application/pdf"


def _insert_record(db: Session, **overrides: object) -> UploadRecord:
    """插入一条上传记录并刷新，字段可通过overrides覆盖。

    Args:
        db: 测试数据库会话。
        **overrides: 需要覆盖的字段。

    Returns:
        已落库并刷新的UploadRecord对象。
    """
    defaults: dict = {
        "user_id": 1,
        "file_type": "resume",
        "file_name": _FILE_NAME,
        "file_size": _FILE_SIZE,
        "content_type": _CONTENT_TYPE,
        "cos_key": "uploads/resumes/1/record-key.pdf",
        "cos_url": "https://bucket.cos.ap-guangzhou.myqcloud.com/uploads/resumes/1/record-key.pdf",
        "etag": "abc123def456",
        "status": "completed",
    }
    defaults.update(overrides)
    record = UploadRecord(**defaults)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _request_sts(client, file_name: str = _FILE_NAME, file_size: int = _FILE_SIZE, file_type: str = "resume"):
    """发起获取STS临时密钥的GET请求。"""
    return client.get(
        "/api/v1/cos/sts-token",
        params={
            "file_name": file_name,
            "file_type": file_type,
            "file_size": file_size,
            "content_type": _CONTENT_TYPE,
        },
    )


def _request_callback(client, cos_key: str, etag: str = '"abc123def456"', file_size: int = _FILE_SIZE):
    """发起上传完成回调的POST请求。"""
    return client.post(
        "/api/v1/cos/callback",
        json={
            "cos_key": cos_key,
            "file_name": _FILE_NAME,
            "file_size": file_size,
            "content_type": _CONTENT_TYPE,
            "etag": etag,
            "location": f"https://bucket.cos.ap-guangzhou.myqcloud.com/{cos_key}",
        },
    )


# ---------------------------------------------------------------------------
# GET /cos/sts-token
# ---------------------------------------------------------------------------

def test_get_sts_token_with_valid_request_returns_credentials(client, mock_sts, fake_redis):
    """测试合法请求返回STS凭证与COS Key，并在Redis登记pending状态。"""
    resp = _request_sts(client)
    assert resp.status_code == 200
    data = resp.json()
    # 响应结构完整
    assert data["credentials"]["tmp_secret_id"] == "AKIDTEST"
    assert data["credentials"]["session_token"] == "TESTTOKEN"
    assert data["bucket"] == settings.COS_BUCKET
    assert data["region"] == settings.COS_REGION
    assert data["upload_url"].startswith("https://")
    # cos_key格式：uploads/resumes/{user_id}/{uuid}.pdf
    cos_key = data["cos_key"]
    parts = cos_key.split("/")
    assert parts[0] == "uploads" and parts[1] == "resumes" and parts[2] == "1"
    assert parts[3].endswith(".pdf")
    # Redis登记pending状态且设置TTL
    status = fake_redis.hashes[f"upload:status:{cos_key}"]
    assert status["status"] == "pending"
    assert status["user_id"] == "1"
    assert fake_redis.ttls[f"upload:status:{cos_key}"] == 3600


def test_get_sts_token_with_invalid_extension_returns_400(client, mock_sts):
    """测试不支持的扩展名返回400。"""
    resp = _request_sts(client, file_name="virus.exe")
    assert resp.status_code == 400
    assert "仅支持" in resp.json()["detail"]


def test_get_sts_token_with_oversize_file_returns_400(client, mock_sts):
    """测试文件大小超过10MB上限返回400。"""
    resp = _request_sts(client, file_size=settings.COS_MAX_FILE_SIZE + 1)
    assert resp.status_code == 400
    assert "10MB" in resp.json()["detail"]


def test_get_sts_token_with_zero_file_size_returns_422(client, mock_sts):
    """测试file_size为0触发Pydantic参数校验422。"""
    resp = _request_sts(client, file_size=0)
    assert resp.status_code == 422


def test_get_sts_token_with_daily_limit_returns_429(client, mock_sts, fake_redis, auth_user_id):
    """测试当日上传次数达到上限返回429。"""
    daily_key = f"upload:daily:{auth_user_id}:{format_upload_date()}"
    fake_redis.strings[daily_key] = settings.COS_DAILY_UPLOAD_LIMIT
    resp = _request_sts(client)
    assert resp.status_code == 429
    assert "明天" in resp.json()["detail"]


def test_get_sts_token_without_auth_returns_401(client, mock_sts):
    """测试未认证（无Cookie）访问STS接口返回401。"""
    client.app.dependency_overrides.pop(get_current_user)
    resp = _request_sts(client)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /cos/callback
# ---------------------------------------------------------------------------

def test_upload_callback_success_persists_record(client, mock_sts, mock_head_object, db_session, fake_redis):
    """测试正常回调：三重校验通过后落库并更新Redis状态为completed。"""
    # 1. 先走真实STS流程获得cos_key（同时在Redis登记pending状态）
    sts_resp = _request_sts(client)
    assert sts_resp.status_code == 200
    cos_key = sts_resp.json()["cos_key"]

    # 2. HEAD元数据与回调参数一致（etag带引号，验证归一化比较）
    resp = _request_callback(client, cos_key=cos_key)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["upload_id"] > 0
    assert cos_key in data["file_url"]

    # 3. 数据库已落库一条记录
    records = db_session.execute(select(UploadRecord)).scalars().all()
    assert len(records) == 1
    assert records[0].user_id == 1
    assert records[0].file_type == "resume"
    assert records[0].cos_key == cos_key
    assert records[0].status == "completed"

    # 4. Redis状态已更新为completed
    assert fake_redis.hashes[f"upload:status:{cos_key}"]["status"] == "completed"


def test_upload_callback_with_other_users_cos_key_returns_400(client, mock_sts, mock_head_object):
    """测试回调他人目录的cos_key返回400（防越权伪造）。"""
    resp = _request_callback(client, cos_key="uploads/resumes/999/not-mine.pdf")
    assert resp.status_code == 400
    assert "不属于当前用户" in resp.json()["detail"]


def test_upload_callback_with_malformed_cos_key_returns_400(client, mock_sts, mock_head_object):
    """测试路径格式非法的cos_key返回400。"""
    resp = _request_callback(client, cos_key="evil/path.pdf")
    assert resp.status_code == 400


def test_upload_callback_with_missing_status_returns_400(client, mock_sts, mock_head_object):
    """测试Redis上传状态不存在（伪造/超时）返回400。"""
    # 未先调STS，Redis无pending状态
    resp = _request_callback(client, cos_key="uploads/resumes/1/forged.pdf")
    assert resp.status_code == 400
    assert "重新上传" in resp.json()["detail"]


def test_upload_callback_with_cos_file_missing_returns_404(client, mock_sts, mock_head_object):
    """测试COS上文件不存在（HEAD返回404）返回404。"""
    sts_resp = _request_sts(client)
    cos_key = sts_resp.json()["cos_key"]
    mock_head_object["meta"] = None  # 模拟HEAD 404
    resp = _request_callback(client, cos_key=cos_key)
    assert resp.status_code == 404


def test_upload_callback_with_size_mismatch_returns_400(client, mock_sts, mock_head_object):
    """测试回调file_size与COS实际大小不一致返回400。"""
    sts_resp = _request_sts(client)
    cos_key = sts_resp.json()["cos_key"]
    # COS实际大小改为409600，回调仍声称204800
    mock_head_object["meta"] = {"content_length": 409600, "content_type": _CONTENT_TYPE, "etag": "abc123def456"}
    resp = _request_callback(client, cos_key=cos_key)
    assert resp.status_code == 400
    assert "大小" in resp.json()["detail"]


def test_upload_callback_with_etag_mismatch_returns_400(client, mock_sts, mock_head_object):
    """测试回调ETag与COS实际ETag不一致返回400。"""
    sts_resp = _request_sts(client)
    cos_key = sts_resp.json()["cos_key"]
    mock_head_object["meta"] = {"content_length": _FILE_SIZE, "content_type": _CONTENT_TYPE, "etag": "different"}
    resp = _request_callback(client, cos_key=cos_key, etag='"abc123def456"')
    assert resp.status_code == 400
    assert "ETag" in resp.json()["detail"]


def test_upload_callback_without_auth_returns_401(client, mock_sts, mock_head_object):
    """测试未认证回调返回401。"""
    client.app.dependency_overrides.pop(get_current_user)
    resp = _request_callback(client, cos_key="uploads/resumes/1/any.pdf")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /cos/records
# ---------------------------------------------------------------------------

def test_list_records_returns_user_records_desc(client, db_session):
    """测试查询当前用户记录（按ID倒序）并返回分页信息。"""
    first = _insert_record(db_session, cos_key="uploads/resumes/1/a.pdf")
    second = _insert_record(db_session, cos_key="uploads/resumes/1/b.pdf")
    resp = client.get("/api/v1/cos/records")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["page"] == 1 and data["page_size"] == 20
    assert [item["upload_id"] for item in data["items"]] == [second.id, first.id]
    assert data["items"][0]["file_url"] == second.cos_url


def test_list_records_with_file_type_filter(client, db_session):
    """测试按file_type过滤记录。"""
    _insert_record(db_session, cos_key="uploads/resumes/1/a.pdf", file_type="resume")
    _insert_record(db_session, cos_key="uploads/avatars/1/a.png", file_type="avatar")
    resp = client.get("/api/v1/cos/records", params={"file_type": "avatar"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["file_type"] == "avatar"


def test_list_records_with_invalid_file_type_returns_400(client, db_session):
    """测试非法file_type参数返回400。"""
    resp = client.get("/api/v1/cos/records", params={"file_type": "video"})
    assert resp.status_code == 400


def test_list_records_excludes_other_users_records(client, db_session, auth_user_id):
    """测试列表不包含其他用户的记录（防越权）。"""
    _insert_record(db_session, user_id=auth_user_id + 100, cos_key="uploads/resumes/101/x.pdf")
    resp = client.get("/api/v1/cos/records")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_records_with_pagination(client, db_session):
    """测试分页参数（page/page_size）生效。"""
    for i in range(3):
        _insert_record(db_session, cos_key=f"uploads/resumes/1/{i}.pdf")
    resp = client.get("/api/v1/cos/records", params={"page": 2, "page_size": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["page"] == 2 and data["page_size"] == 2
    assert len(data["items"]) == 1


# ---------------------------------------------------------------------------
# DELETE /cos/records/{record_id}
# ---------------------------------------------------------------------------

def test_delete_record_success_returns_204(client, db_session, mock_delete_object):
    """测试删除成功返回204，同时删除COS文件与数据库记录。"""
    record = _insert_record(db_session)
    resp = client.delete(f"/api/v1/cos/records/{record.id}")
    assert resp.status_code == 204
    # 数据库记录已删除
    assert db_session.get(UploadRecord, record.id) is None
    # COS删除被调用且传入正确的key
    assert mock_delete_object == [record.cos_key]


def test_delete_record_not_found_returns_404(client, db_session, mock_delete_object):
    """测试删除不存在的记录返回404。"""
    resp = client.delete("/api/v1/cos/records/99999")
    assert resp.status_code == 404
    assert mock_delete_object == []


def test_delete_record_of_other_user_returns_404(client, db_session, mock_delete_object, auth_user_id):
    """测试删除他人记录返回404（防越权，不暴露存在性）。"""
    record = _insert_record(db_session, user_id=auth_user_id + 100, cos_key="uploads/resumes/101/x.pdf")
    resp = client.delete(f"/api/v1/cos/records/{record.id}")
    assert resp.status_code == 404
    # 他人的记录与COS文件均未被删除
    assert db_session.get(UploadRecord, record.id) is not None
    assert mock_delete_object == []
