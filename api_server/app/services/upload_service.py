"""文件上传服务层（同步）。

编排"前置校验 → STS临时密钥发放 → Redis状态登记"与
"回调防伪造校验 → COS HEAD校验 → 记录落库"两条链路。

安全设计:
    - STS 策略限定到用户目录，前端临时密钥无法越权写他人目录。
    - 回调时校验 cos_key 路径前缀归属 + Redis 上传状态 + COS HEAD 元数据三重防伪造。
    - Redis 每日计数器限制单用户上传频率，防刷量。
"""

import logging
import os
import uuid
from datetime import datetime

import redis
from sqlalchemy.orm import Session

from app.cos import CosError, build_cos_url, cos_client, format_upload_date
from app.core.config import settings
from app.repositories.upload_repository import upload_repository
from app.schemas.upload import (
    StsTokenRequest,
    StsTokenResponse,
    UploadCallbackRequest,
    UploadCallbackResponse,
    UploadRecordListResponse,
    UploadRecordResponse,
)

logger = logging.getLogger(__name__)

# Redis 键模板
_UPLOAD_STATUS_KEY = "upload:status:{cos_key}"  # 上传中间状态（防伪造回调）
_UPLOAD_DAILY_KEY = "upload:daily:{user_id}:{date}"  # 每日上传计数

# 上传状态Redis TTL（秒）：超时未回调自动过期，回调时视为伪造
UPLOAD_STATUS_TTL = 3600
# 每日计数TTL（秒）
DAILY_COUNT_TTL = 86400


class FileTypeInvalidError(Exception):
    """文件类型不支持（路由层转400）。"""


class FileSizeExceedError(Exception):
    """文件大小超限（路由层转400）。"""


class DailyLimitExceededError(Exception):
    """当日上传次数达上限（路由层转429）。"""


class CallbackInvalidError(Exception):
    """回调参数无效/校验不通过（路由层转400）。"""


class CosFileNotFoundError(Exception):
    """COS文件不存在（HEAD校验失败，路由层转404）。"""


class UploadNotFoundError(Exception):
    """上传记录不存在（路由层转404）。"""


class UploadService:
    """文件上传业务编排层（同步）：STS发放 + 回调校验 + 记录管理。"""

    # 文件用途 → 目录名映射（所有图片类型统一走 images 目录）
    _FILE_TYPE_DIR_MAP: dict[str, str] = {
        "resume": "resumes",
        "avatar": "images",
        "post_image": "images",
    }

    # 目录名 → 文件用途反向映射（回调校验用）
    _DIR_FILE_TYPE_MAP: dict[str, str] = {
        "resumes": "resume",
        "images": "image",
    }

    # ------------------------------------------------------------------
    # STS 临时密钥发放
    # ------------------------------------------------------------------

    def get_sts_token(
        self, cache_client: redis.Redis, user_id: int, req: StsTokenRequest
    ) -> StsTokenResponse:
        """校验上传请求并发放限定目录的 STS 临时密钥。

        校验顺序: 文件类型白名单 → 文件大小上限 → 每日上传次数限制 →
        生成COS Key → 调用STS → Redis登记pending状态。

        Args:
            cache_client: 同步Redis客户端（每日计数 + 上传状态）。
            user_id: 当前用户ID。
            req: STS申请请求（file_name/file_type/file_size/content_type）。

        Returns:
            StsTokenResponse: 临时密钥 + COS Key + Bucket/Region + 上传URL。

        Raises:
            FileTypeInvalidError: 扩展名不在白名单。
            FileSizeExceedError: 文件大小超过上限。
            DailyLimitExceededError: 当日上传次数已达上限。
            CosError: STS调用失败。
        """
        # 1. 扩展名白名单校验
        ext = os.path.splitext(req.file_name)[1].lower()
        allowed_exts = [e.strip().lower() for e in settings.COS_ALLOWED_EXTENSIONS.split(",") if e.strip()]
        if ext not in allowed_exts:
            raise FileTypeInvalidError(f"不支持的文件类型: {ext or '(无扩展名)'}")

        # 2. 文件大小校验
        if req.file_size > settings.COS_MAX_FILE_SIZE:
            raise FileSizeExceedError("文件大小不能超过 10MB")

        # 3. 每日上传次数限制（Redis计数器，防刷量）
        daily_key = _UPLOAD_DAILY_KEY.format(user_id=user_id, date=format_upload_date())
        count = cache_client.incr(daily_key)
        if count == 1:
            cache_client.expire(daily_key, DAILY_COUNT_TTL)
        if count > settings.COS_DAILY_UPLOAD_LIMIT:
            raise DailyLimitExceededError("今日上传次数已用完，请明天再试")

        # 4. 生成COS Key：{type_dir}/{user_id}/{uuid}.{ext}
        # 图片类型（avatar/post_image）统一走 images/ 目录
        type_dir = self._FILE_TYPE_DIR_MAP.get(req.file_type, f"{req.file_type}s")
        cos_key = f"{type_dir}/{user_id}/{uuid.uuid4().hex}{ext}"

        # 5. 调用STS生成限定目录的临时密钥
        resource_prefix = f"{type_dir}/{user_id}"
        credentials = cos_client.get_sts_credentials(resource_prefix)

        # 6. Redis登记上传pending状态（回调校验依据，TTL 1小时）
        status_key = _UPLOAD_STATUS_KEY.format(cos_key=cos_key)
        cache_client.hset(
            status_key,
            mapping={
                "status": "pending",
                "user_id": user_id,
                "file_name": req.file_name,
                "file_size": req.file_size,
            },
        )
        cache_client.expire(status_key, UPLOAD_STATUS_TTL)

        logger.info(
            "发放STS临时密钥: user_id=%s file_type=%s cos_key=%s daily_count=%s",
            user_id, req.file_type, cos_key, count,
        )

        return StsTokenResponse(
            credentials=credentials,  # type: ignore[arg-type]
            cos_key=cos_key,
            bucket=settings.COS_BUCKET,
            region=settings.COS_REGION,
            upload_url=f"https://{cos_client.get_bucket_domain()}",
            expire_time=settings.COS_STS_DURATION,
        )

    # ------------------------------------------------------------------
    # 上传完成回调校验
    # ------------------------------------------------------------------

    def upload_callback(
        self, db: Session, cache_client: redis.Redis, user_id: int, req: UploadCallbackRequest
    ) -> UploadCallbackResponse:
        """校验前端直传结果并落库上传记录（三重防伪造）。

        校验链路: cos_key路径前缀归属 → Redis上传状态存在且归属一致 →
        COS HEAD Object元数据（大小/ETag）一致性。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            user_id: 当前用户ID。
            req: 回调请求（cos_key/file_name/file_size/content_type/etag/location）。

        Returns:
            UploadCallbackResponse: 上传记录ID + 文件URL + 状态。

        Raises:
            CallbackInvalidError: cos_key不匹配当前用户、Redis状态缺失或元数据校验失败。
            CosFileNotFoundError: COS上文件不存在。
            CosError: COS服务异常。
        """
        # 1. 校验cos_key路径前缀归属（{type_dir}/{user_id}/...）
        file_type = self._parse_and_check_cos_key(req.cos_key, user_id)

        # 2. Redis上传状态校验（防伪造回调/超时）
        status_key = _UPLOAD_STATUS_KEY.format(cos_key=req.cos_key)
        status_data = cache_client.hgetall(status_key)
        if not status_data:
            raise CallbackInvalidError("上传状态不存在或已过期，请重新上传")
        if int(status_data.get("user_id", "0")) != user_id:
            raise CallbackInvalidError("无权操作该文件")

        # 3. COS HEAD Object校验文件完整性
        head = cos_client.head_object(req.cos_key)
        if head is None:
            raise CosFileNotFoundError("COS上文件不存在")
        if head["content_length"] != req.file_size:
            raise CallbackInvalidError("文件大小与COS实际大小不一致")
        # ETag归一化（COS与前端SDK返回值都可能带引号）
        req_etag = req.etag.strip('"')
        if req_etag and head["etag"] and req_etag != head["etag"]:
            raise CallbackInvalidError("文件ETag校验失败")

        # 4. 校验通过：写入上传记录
        record = upload_repository.create(
            db,
            user_id=user_id,
            file_type=file_type,
            file_name=req.file_name,
            file_size=req.file_size,
            content_type=req.content_type,
            cos_key=req.cos_key,
            cos_url=build_cos_url(req.cos_key),
            etag=head["etag"],
            status="completed",
        )

        # 5. 更新Redis状态为completed并清理
        cache_client.hset(status_key, "status", "completed")
        cache_client.expire(status_key, 600)

        logger.info(
            "上传回调校验通过: user_id=%s upload_id=%s cos_key=%s size=%s",
            user_id, record.id, req.cos_key, req.file_size,
        )

        return UploadCallbackResponse(
            upload_id=record.id,
            cos_key=record.cos_key,
            file_url=record.cos_url,
            status=record.status,
            created_at=record.created_at or datetime.now(),
        )

    # ------------------------------------------------------------------
    # 上传记录查询与删除
    # ------------------------------------------------------------------

    def list_records(
        self,
        db: Session,
        user_id: int,
        file_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> UploadRecordListResponse:
        """分页查询当前用户的上传记录。

        Args:
            db: 数据库同步会话。
            user_id: 当前用户ID。
            file_type: 按用途过滤（resume/image），None表示全部。
            page: 页码（从1开始）。
            page_size: 页大小。

        Returns:
            UploadRecordListResponse: 记录列表 + 总数 + 分页信息。
        """
        offset = (page - 1) * page_size
        records = upload_repository.list_by_user(db, user_id, file_type, offset, page_size)
        total = upload_repository.count_by_user(db, user_id, file_type)
        items = [
            UploadRecordResponse(
                upload_id=r.id,
                file_type=r.file_type,
                file_name=r.file_name,
                file_size=r.file_size,
                content_type=r.content_type,
                file_url=r.cos_url,
                status=r.status,
                created_at=r.created_at or datetime.now(),
            )
            for r in records
        ]
        return UploadRecordListResponse(items=items, total=total, page=page, page_size=page_size)

    def delete_record(self, db: Session, user_id: int, record_id: int) -> None:
        """删除上传记录并同步删除COS文件。

        Args:
            db: 数据库同步会话。
            user_id: 当前用户ID（防越权）。
            record_id: 上传记录ID。

        Raises:
            UploadNotFoundError: 记录不存在或不属于当前用户。
            CosError: COS删除失败。
        """
        record = upload_repository.get_by_id(db, record_id)
        if record is None or record.user_id != user_id:
            raise UploadNotFoundError("上传记录不存在")

        # 先删COS文件（幂等：文件不存在也视为成功）
        cos_client.delete_object(record.cos_key)

        # 再删数据库记录
        upload_repository.delete_by_id(db, record_id)
        logger.info("删除上传记录: user_id=%s record_id=%s cos_key=%s", user_id, record_id, record.cos_key)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_and_check_cos_key(cos_key: str, user_id: int) -> str:
        """解析并校验cos_key路径前缀归属（防伪造回调的关键防线）。

        期望格式: {type_dir}/{user_id}/{filename}，
        其中 type_dir 为 resumes / images，{user_id} 必须与当前登录用户一致。

        Args:
            cos_key: COS对象Key。
            user_id: 当前用户ID。

        Returns:
            文件用途（resume/avatar）。

        Raises:
            CallbackInvalidError: 路径格式非法或归属不匹配。
        """
        parts = cos_key.strip("/").split("/")
        if len(parts) != 3:
            raise CallbackInvalidError("cos_key路径格式非法")
        type_dir = parts[0]
        file_type = UploadService._DIR_FILE_TYPE_MAP.get(type_dir)
        if file_type is None:
            raise CallbackInvalidError("cos_key文件用途非法")
        try:
            path_user_id = int(parts[1])
        except ValueError as exc:
            raise CallbackInvalidError("cos_key路径用户ID非法") from exc
        if path_user_id != user_id:
            raise CallbackInvalidError("cos_key不属于当前用户")
        return file_type


upload_service = UploadService()