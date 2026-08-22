"""端到端测试：简历上传 → 回调去重 → Outbox → MQ → LangGraph LLM 解析 → 落库 → 校验。

覆盖《简历上传分析功能文档》M1 全链路（真实 COS + LLM）：
    1. 生成一份真实 PDF 简历（pypdf，Helvetica 标准字体，英文文本可提取）
    2. 按 COS XML API 签名（含 body SHA1）PUT 上传到 COS
    3. 调用 POST /cos/callback 触发回调联动（SHA256 去重 + 简历创建 + Outbox 调度）
    4. 等待 MQ runner 消费 → InterviewResumeParseConsumer → LLM 结构化提取 → 落库
    5. 轮询 GET /resumes/{id} 校验 status=1 及解析结果字段
    6. 重复上传同一文件验证去重复用（不新增记录）
    7. 失败自愈：模拟 status=2 + 旧 COS 对象删除后重新上传同一内容，
       验证去重命中刷新 file_url 指向新对象并重新调度解析成功
    8. SSE 实时推送：保持 /messages/stream 长连接，验证解析完成通知实时到达
    9. 删除联动：删除简历类上传记录联动软删除简历行，重新上传同文件创建新记录

用法: 在 api_server 目录下用 interview 环境运行
    python tests/e2e_resume_parse_test.py

前提: uvicorn + mq.runner 运行中，MySQL/Redis/RabbitMQ/LLM 正常。
"""

import hashlib
import hmac
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import jwt
import requests
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import text

# 允许直接 python 运行时从项目根导入 app 包（脚本位于 tests/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.cos import cos_client
from app.db.sync_session import SyncSessionLocal

# ---- 配置 ----
BASE = "http://127.0.0.1:8000/api/v1"
SECRET_KEY = "change-me-in-production"  # 与 api_server/.env 保持一致
USER_ID = 1  # E2E测试用户A

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
    return jwt.encode({"sub": str(user_id), "login": "test_a"}, SECRET_KEY, algorithm="HS256")


def session_for(user_id: int) -> requests.Session:
    """创建携带 access_token Cookie 的会话。"""
    s = requests.Session()
    s.cookies.set("access_token", make_token(user_id))
    return s


# ---------------------------------------------------------------------------
# 测试 PDF 生成（pypdf 构造，Helvetica 标准字体，内容为可提取文本）
# ---------------------------------------------------------------------------

_RESUME_LINES = [
    "Resume",
    "",
    "Name: Zhang San",
    "Email: zhangsan@example.com",
    "Phone: 138-0000-0000",
    "",
    "Skills: Python, FastAPI, MySQL, Redis, Docker, LangChain",
    "",
    "Education:",
    "Tsinghua University, Bachelor, Computer Science, 2016-2020",
    "",
    "Projects:",
    "AI Interview System: Built an AI-powered interview coaching backend with FastAPI and LangChain.",
    "Tech stack: FastAPI, MySQL, Redis, LangChain, RabbitMQ",
    "",
    "Work Experience:",
    "ByteDance, Backend Engineer, 2020-2023",
    "Developed high-concurrency services and optimized MySQL queries.",
]


def make_resume_pdf(path: str) -> None:
    """生成单页 PDF 简历（内容为纯文本，供 LLM 结构化提取）。"""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    content_stream = DecodedStreamObject()
    cmds = ["BT", "/F1 12 Tf", "72 720 Td"]
    for line in _RESUME_LINES:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        cmds.append(f"({safe}) Tj")
        cmds.append("0 -18 Td")
    cmds.append("ET")
    content_stream.set_data("\n".join(cmds).encode("latin-1"))
    page[NameObject("/Contents")] = content_stream

    res = DictionaryObject()
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    res[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = res
    with open(path, "wb") as f:
        writer.write(f)


# ---------------------------------------------------------------------------
# COS PUT 上传（复用服务端 CosClient.put_object，COS XML API 签名含 body SHA1）
# ---------------------------------------------------------------------------

def wait_resume_ready(sa: requests.Session, resume_id: int, timeout: int = 300) -> tuple[int, dict | None]:
    """轮询等待简历解析到达终态（1就绪/2失败）。

    Args:
        sa: 携带认证Cookie的会话。
        resume_id: 简历ID。
        timeout: 最长等待秒数。

    Returns:
        (最终状态, 详情字典)；超时返回 (None, None)。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        rr = sa.get(f"{BASE}/resumes/{resume_id}", timeout=10)
        if rr.status_code != 200:
            continue
        item = rr.json()
        if item.get("status") in (1, 2):
            return item["status"], item
    return None, None


class SseCollector:
    """后台线程读取 SSE 流并收集事件（用于验证实时推送链路）。"""

    def __init__(self, sa: requests.Session) -> None:
        """初始化并立即建立 SSE 长连接（携带认证Cookie）。"""
        self.events: list[str] = []
        self._stop = threading.Event()
        self._resp = sa.get(f"{BASE}/messages/stream", stream=True, timeout=(5, 120))
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        """循环读取 SSE 行，收集 event:/data: 行直到停止。"""
        try:
            for line in self._resp.iter_lines(decode_unicode=True):
                if self._stop.is_set():
                    break
                if line and (line.startswith("event:") or line.startswith("data:")):
                    self.events.append(line)
        except Exception:  # noqa: BLE001
            pass

    def has_message_containing(self, keyword: str, after_index: int = 0) -> bool:
        """检查是否收到包含指定关键词的 message 事件数据行。"""
        for line in self.events[after_index:]:
            if line.startswith("data:") and keyword in line:
                return True
        return False

    def close(self) -> None:
        """停止读取并关闭连接。"""
        self._stop.set()
        self._resp.close()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    """执行简历上传分析全链路端到端测试。"""
    print("=" * 60)
    print("阶段0: 健康检查")
    r = requests.get("http://127.0.0.1:8000/health", timeout=5)
    check("健康检查 200", r.status_code == 200, f"status={r.status_code}")

    sa = session_for(USER_ID)

    # ------------------------------------------------------------
    print("=" * 60)
    print("阶段1: 生成测试 PDF 简历，获取 STS 临时密钥并上传 COS")
    pdf_path = f"_e2e_resume_{uuid.uuid4().hex[:8]}.pdf"
    make_resume_pdf(pdf_path)
    with open(pdf_path, "rb") as f:
        content = f.read()
    print(f"    生成的简历 PDF: {pdf_path} ({len(content)} bytes)")

    # 1.1 先申请 STS（后端在 Redis 登记 pending 状态，回调据此校验）
    r_sts = sa.get(
        f"{BASE}/cos/sts-token",
        params={
            "file_name": "ZhangSan_Resume.pdf",
            "file_type": "resume",
            "file_size": len(content),
            "content_type": "application/pdf",
        },
        timeout=15,
    )
    check("STS 临时密钥 200", r_sts.status_code == 200, f"status={r_sts.status_code} body={r_sts.text[:300]}")
    if r_sts.status_code != 200:
        print("    获取 STS 失败，终止测试")
        sys.exit(1)
    sts_data = r_sts.json()
    cos_key = sts_data.get("cos_key")
    check("STS 返回 cos_key", bool(cos_key), f"cos_key={cos_key}")

    # 1.2 用管理端密钥 PUT 上传到该 cos_key
    try:
        etag = cos_client.put_object(cos_key, content, content_type="application/pdf")
    except Exception as e:  # noqa: BLE001
        check("PUT 上传 COS 成功", False, f"error={e}")
        print("    上传失败，终止测试")
        sys.exit(1)
    check("PUT 上传 COS 成功", bool(etag), f"etag={etag}")
    print(f"    COS 对象: {cos_key}  ETag: {etag}")

    # ------------------------------------------------------------
    print("=" * 60)
    print("阶段2: 上传回调（触发 SHA256 去重 + 简历创建 + Outbox 调度）")
    r = sa.post(
        f"{BASE}/cos/callback",
        json={
            "cos_key": cos_key,
            "file_name": "ZhangSan_Resume.pdf",
            "file_size": len(content),
            "content_type": "application/pdf",
            "etag": etag,
            "location": f"https://{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com/{cos_key}",
        },
        timeout=30,
    )
    check("回调返回 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code != 200:
        print("    回调失败，终止测试")
        sys.exit(1)
    data = r.json()
    resume_id = data.get("resume_id")
    resume_status = data.get("resume_status")
    check("回调返回 resume_id", resume_id is not None, f"resume_id={resume_id}")
    check("简历初始状态为解析中(0)", resume_status == 0, f"resume_status={resume_status}")
    print(f"    resume_id={resume_id} resume_status={resume_status}")

    # ------------------------------------------------------------
    print("=" * 60)
    print("阶段3: 等待 MQ 消费 + LLM 解析（轮询状态，最长 5 分钟）")
    final_status, detail = None, None
    deadline = time.time() + 300
    while time.time() < deadline:
        time.sleep(3)
        rr = sa.get(f"{BASE}/resumes/{resume_id}", timeout=10)
        if rr.status_code != 200:
            continue
        item = rr.json()
        final_status = item.get("status")
        if final_status in (1, 2):
            detail = item
            break
    check(f"简历解析完成（status=1 就绪 / 2 失败）", final_status == 1,
          f"status={final_status} error_message={(detail or {}).get('error_message')}")
    if final_status != 1:
        print("    解析失败或超时，终止测试")
        print(f"    详情: {detail}")
        sys.exit(1)

    # ------------------------------------------------------------
    print("=" * 60)
    print("阶段4: 校验 LLM 结构化解析结果")
    item = detail
    check("解析出姓名 Zhang San", (item.get("parsed_name") or "").lower() == "zhang san",
          f"parsed_name={item.get('parsed_name')}")
    skills = [s.lower() for s in (item.get("parsed_skills") or [])]
    check("技能含 Python", "python" in skills, f"skills={item.get('parsed_skills')}")
    check("技能含 FastAPI", "fastapi" in skills, f"skills={item.get('parsed_skills')}")
    projects = item.get("parsed_projects") or []
    check("项目经历非空", len(projects) > 0, f"projects={projects}")
    if projects:
        check("项目含名称", bool(projects[0].get("name")), f"project={projects[0]}")
    education = item.get("parsed_education") or []
    check("教育经历非空", len(education) > 0, f"education={education}")
    works = item.get("work_experiences") or []
    check("工作经历非空", len(works) > 0, f"works={works}")
    if works:
        check("工作经历含公司", bool(works[0].get("company")), f"work={works[0]}")
    check("status=1 就绪", item.get("status") == 1, f"status={item.get('status')}")

    # ------------------------------------------------------------
    print("=" * 60)
    print("阶段5: 重复上传同一文件 → 去重复用（不新增记录）")
    r2 = sa.post(
        f"{BASE}/cos/callback",
        json={
            "cos_key": cos_key,
            "file_name": "ZhangSan_Resume.pdf",
            "file_size": len(content),
            "content_type": "application/pdf",
            "etag": etag,
            "location": f"https://{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com/{cos_key}",
        },
        timeout=30,
    )
    check("重复上传回调 200", r2.status_code == 200, f"status={r2.status_code}")
    if r2.status_code == 200:
        d2 = r2.json()
        check("去重复用同一 resume_id", d2.get("resume_id") == resume_id,
              f"resume_id={d2.get('resume_id')} expected={resume_id}")
        check("已就绪不重复调度", d2.get("resume_status") == 1, f"resume_status={d2.get('resume_status')}")
    else:
        check("重复上传回调 200", False, f"body={r2.text[:200]}")

    # 列表校验
    rl = sa.get(f"{BASE}/resumes/", params={"page": 1, "page_size": 20}, timeout=10)
    check("简历列表 200", rl.status_code == 200, f"status={rl.status_code}")
    if rl.status_code == 200:
        items = rl.json().get("items", [])
        check("列表中仅 1 份简历（去重生效）", len(items) == 1, f"items={len(items)}")

    # ------------------------------------------------------------
    print("=" * 60)
    print("阶段6: 失败自愈 — 模拟解析失败+旧COS对象删除，重新上传同一内容")
    # 6.1 先建立 SSE 长连接（验证阶段7的实时推送）
    sse = None
    try:
        sse = SseCollector(sa)
        time.sleep(2)  # 等待连接注册
        check("SSE 长连接建立（无认证异常）", True, "")
    except Exception as e:  # noqa: BLE001
        check("SSE 长连接建立（无认证异常）", False, f"error={e}")

    # 6.2 模拟故障：简历置为失败态 + 删除旧 COS 对象（复现线上404场景）
    with SyncSessionLocal() as db:
        db.execute(
            text("UPDATE resume SET status = 2, error_message = 'simulated: object deleted' WHERE id = :rid"),
            {"rid": resume_id},
        )
        db.commit()
    cos_client.delete_object(cos_key)
    print(f"    已模拟: resume_id={resume_id} status=2, 旧对象已删 {cos_key}")

    # 6.3 同一文件内容重新上传（STS 分配新 cos_key）；先记录重传前 Outbox 事件数
    with SyncSessionLocal() as db:
        outbox_before = db.execute(
            text("SELECT COUNT(*) FROM outbox_event WHERE payload -> '$.resume_id' = :rid"),
            {"rid": resume_id},
        ).scalar_one()
    r_sts2 = sa.get(
        f"{BASE}/cos/sts-token",
        params={"file_name": "ZhangSan_Resume.pdf", "file_type": "resume",
                "file_size": len(content), "content_type": "application/pdf"},
        timeout=15,
    )
    new_cos_key = r_sts2.json().get("cos_key") if r_sts2.status_code == 200 else None
    check("重新上传获取新 STS 200", r_sts2.status_code == 200 and bool(new_cos_key),
          f"status={r_sts2.status_code}")
    etag2 = cos_client.put_object(new_cos_key, content, content_type="application/pdf")
    check("重新上传 PUT 新对象成功", bool(etag2), f"etag={etag2}")

    r3 = sa.post(
        f"{BASE}/cos/callback",
        json={
            "cos_key": new_cos_key,
            "file_name": "ZhangSan_Resume.pdf",
            "file_size": len(content),
            "content_type": "application/pdf",
            "etag": etag2,
            "location": f"https://{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com/{new_cos_key}",
        },
        timeout=30,
    )
    check("失败后重传回调 200", r3.status_code == 200, f"status={r3.status_code} body={r3.text[:300]}")
    if r3.status_code == 200:
        d3 = r3.json()
        check("失败简历重传复用同一 resume_id", d3.get("resume_id") == resume_id,
              f"resume_id={d3.get('resume_id')} expected={resume_id}")
        check("重传后状态重置为解析中(0)", d3.get("resume_status") == 0, f"resume_status={d3.get('resume_status')}")
        # 重新调度验证：该简历的 Outbox 事件数应 +1（最新事件携带新 cos_key）
        with SyncSessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT COUNT(*), COALESCE((SELECT payload ->> '$.cos_key' FROM outbox_event "
                    "WHERE payload -> '$.resume_id' = :rid ORDER BY id DESC LIMIT 1), '') "
                    "FROM outbox_event WHERE payload -> '$.resume_id' = :rid"
                ),
                {"rid": resume_id},
            ).fetchone()
        check("重传触发重新调度（Outbox事件+1）", row[0] == outbox_before + 1,
              f"before={outbox_before} after={row[0]}")
        check("新调度事件携带新 cos_key", row[1] == new_cos_key, f"last_cos_key={row[1]}")

    # 6.4 校验 file_url 已刷新指向新对象
    with SyncSessionLocal() as db:
        row = db.execute(
            text("SELECT file_url, error_message FROM resume WHERE id = :rid"),
            {"rid": resume_id},
        ).fetchone()
    expected_url = f"https://{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com/{new_cos_key}"
    check("file_url 已刷新指向新 COS 对象", row and row[0] == expected_url,
          f"file_url={row[0] if row else None}")
    check("error_message 已清空", row and not row[1], f"error_message={row[1] if row else None}")

    # 6.5 等待重新解析完成（旧对象已删，若 file_url 未刷新必然404失败）
    st2, _ = wait_resume_ready(sa, resume_id)
    check("失败简历重传后重新解析成功（status=1）", st2 == 1, f"status={st2}")

    # ------------------------------------------------------------
    print("=" * 60)
    print("阶段7: SSE 实时推送 — 解析完成通知到达长连接")
    if sse is not None:
        time.sleep(5)  # 等待事件送达
        got = sse.has_message_containing("简历 AI 分析已完成")
        check("SSE 收到「简历 AI 分析已完成」实时推送", got,
              f"events={sse.events[:6]}")
        sse.close()
    else:
        check("SSE 收到「简历 AI 分析已完成」实时推送", False, "SSE 连接未建立")

    # ------------------------------------------------------------
    print("=" * 60)
    print("阶段8: 删除联动 — 删除简历类上传记录联动软删除简历")
    # 8.1 找到该简历对应的上传记录（列表项以 file_url 标识对象，upload_id 为主键）
    rl2 = sa.get(f"{BASE}/cos/records", params={"file_type": "resume", "page": 1, "page_size": 20}, timeout=10)
    record_id = None
    if rl2.status_code == 200:
        for rec in rl2.json().get("items", []):
            if new_cos_key in (rec.get("file_url") or ""):
                record_id = rec.get("upload_id")
                break
    check("找到简历对应的上传记录", record_id is not None, f"records={rl2.text[:300]}")

    # 8.2 删除上传记录（联动软删除简历 + 删COS对象）
    if record_id is not None:
        rd = sa.delete(f"{BASE}/cos/records/{record_id}", timeout=30)
        check("删除上传记录返回 204", rd.status_code == 204, f"status={rd.status_code}")

        # 8.3 简历详情应 404（软删除后不可见）
        rg = sa.get(f"{BASE}/resumes/{resume_id}", timeout=10)
        check("软删除简历详情返回 404", rg.status_code == 404, f"status={rg.status_code}")

        # 8.4 数据库层校验：is_deleted=1 且 file_hash 已释放
        with SyncSessionLocal() as db:
            row = db.execute(
                text("SELECT is_deleted, file_hash, deleted_at FROM resume WHERE id = :rid"),
                {"rid": resume_id},
            ).fetchone()
        check("简历行 is_deleted=1", row and row[0] == 1, f"row={row}")
        check("file_hash 已释放（允许重传同文件）", row and not row[1], f"file_hash={row[1] if row else None}")

        # 8.5 重新上传同一内容 → 创建全新简历记录（唯一约束已释放）
        r_sts3 = sa.get(
            f"{BASE}/cos/sts-token",
            params={"file_name": "ZhangSan_Resume.pdf", "file_type": "resume",
                    "file_size": len(content), "content_type": "application/pdf"},
            timeout=15,
        )
        cos_key3 = r_sts3.json().get("cos_key")
        etag3 = cos_client.put_object(cos_key3, content, content_type="application/pdf")
        r4 = sa.post(
            f"{BASE}/cos/callback",
            json={
                "cos_key": cos_key3,
                "file_name": "ZhangSan_Resume.pdf",
                "file_size": len(content),
                "content_type": "application/pdf",
                "etag": etag3,
                "location": f"https://{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com/{cos_key3}",
            },
            timeout=30,
        )
        check("删除后重传回调 200", r4.status_code == 200, f"status={r4.status_code}")
        if r4.status_code == 200:
            d4 = r4.json()
            new_resume_id = d4.get("resume_id")
            check("删除后重传创建新 resume_id", new_resume_id is not None and new_resume_id != resume_id,
                  f"resume_id={new_resume_id} old={resume_id}")
            st3, _ = wait_resume_ready(sa, new_resume_id)
            check("新简历解析成功（status=1）", st3 == 1, f"status={st3}")

    # 清理本地 PDF
    import os
    os.unlink(pdf_path)

    # ------------------------------------------------------------
    print("=" * 60)
    print(f"汇总: PASS={len(PASS)} FAIL={len(FAIL)}")
    for name, detail in FAIL:
        print(f"  FAIL: {name} -> {detail}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
