"""文件上传API端点，提供STS临时密钥发放、上传回调校验、上传记录管理。"""

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_redis
from app.cos import CosError
from app.schemas.upload import (
    StsTokenRequest,
    StsTokenResponse,
    UploadCallbackRequest,
    UploadCallbackResponse,
    UploadRecordListResponse,
)
from app.services.upload_service import (
    CallbackInvalidError,
    CosFileNotFoundError,
    DailyLimitExceededError,
    FileTypeInvalidError,
    FileSizeExceedError,
    UploadNotFoundError,
    upload_service,
)

router = APIRouter(prefix="/cos", tags=["文件上传"])


def _get_user_id(payload: dict) -> int:
    """从认证载荷中解析当前用户ID。

    Args:
        payload: get_current_user依赖返回的JWT载荷字典。

    Returns:
        当前用户唯一标识。
    """
    return int(payload["sub"])


@router.get("/sts-token", response_model=StsTokenResponse, summary="获取STS临时密钥")
def get_sts_token(
    file_name: str = Query(..., min_length=1, max_length=255, description="原始文件名"),
    file_type: str = Query(..., description="文件用途：resume（简历）/ image（图片）"),
    file_size: int = Query(..., gt=0, description="文件大小（字节）"),
    content_type: str = Query(..., max_length=100, description="文件MIME类型"),
    payload: dict = Depends(get_current_user),
    cache_client: redis.Redis = Depends(get_redis),
) -> StsTokenResponse:
    """获取STS临时密钥与COS上传路径（前端直传前置接口）。

    校验文件类型/大小/每日次数后，发放限定到用户目录的临时密钥，
    并在Redis登记pending状态供回调校验。

    Args:
        file_name: 原始文件名（用于提取扩展名）。
        file_type: 文件用途（resume/image）。
        file_size: 文件大小（字节）。
        content_type: 文件MIME类型。
        payload: JWT认证载荷。
        cache_client: 同步Redis客户端。

    Returns:
        StsTokenResponse: 临时密钥 + cos_key + bucket/region + 上传URL。

    Raises:
        HTTPException: 类型不支持400；大小超限400；次数超限429；STS失败500。
    """
    try:
        req = StsTokenRequest(
            file_name=file_name, file_type=file_type, file_size=file_size, content_type=content_type
        )
    except ValidationError as exc:
        errors = exc.errors()
        msgs = [e.get("msg", "参数错误") for e in errors]
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="; ".join(msgs))
    try:
        return upload_service.get_sts_token(cache_client, _get_user_id(payload), req)
    except FileTypeInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"仅支持 PDF、Word、图片格式（{exc}）")
    except FileSizeExceedError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件大小不能超过 10MB")
    except DailyLimitExceededError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="今日上传次数已用完，请明天再试"
        )
    except CosError:
        raise HTTPException(status_code=500, detail="上传服务异常，请稍后重试")


@router.post("/callback", response_model=UploadCallbackResponse, summary="上传完成回调校验")
def upload_callback(
    request_body: UploadCallbackRequest,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> UploadCallbackResponse:
    """前端直传COS成功后的回调校验（三重防伪造）。

    校验cos_key路径归属 → Redis上传状态 → COS HEAD元数据一致性，
    全部通过后写入upload_records表。

    Args:
        request_body: 回调请求体（cos_key/文件元信息/etag/location）。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端。

    Returns:
        UploadCallbackResponse: 上传记录ID + 文件URL + 状态。

    Raises:
        HTTPException: 回调参数无效400；COS文件不存在404；COS服务异常502。
    """
    try:
        return upload_service.upload_callback(db, cache_client, _get_user_id(payload), request_body)
    except CallbackInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except CosFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="COS上文件不存在，请重新上传")
    except CosError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="COS服务异常，请稍后重试")
    except Exception:
        raise HTTPException(status_code=500, detail="上传记录保存失败")


@router.get("/records", response_model=UploadRecordListResponse, summary="查询上传记录列表")
def list_upload_records(
    file_type: str | None = Query(None, description="按用途过滤：resume/image，不传查全部"),
    page: int = Query(1, ge=1, le=1000, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="页大小（1-100）"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadRecordListResponse:
    """分页查询当前用户的上传记录（按时间倒序）。

    Args:
        file_type: 按用途过滤，None查全部。
        page: 页码。
        page_size: 页大小。
        payload: JWT认证载荷。
        db: 数据库同步会话。

    Returns:
        UploadRecordListResponse: 记录列表 + 总数 + 分页信息。
    """
    if file_type is not None and file_type not in ("resume", "image"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_type 仅支持 resume / image")
    return upload_service.list_records(db, _get_user_id(payload), file_type, page, page_size)


@router.delete(
    "/records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除上传记录",
)
def delete_upload_record(
    record_id: int = Path(..., ge=1, description="上传记录ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """删除上传记录并同步删除COS文件（幂等：COS文件不存在也视为删除成功）。

    Args:
        record_id: 上传记录ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。

    Returns:
        204 No Content。

    Raises:
        HTTPException: 记录不存在404；COS删除失败502。
    """
    try:
        upload_service.delete_record(db, _get_user_id(payload), record_id)
    except UploadNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传记录不存在")
    except CosError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="COS服务异常，请稍后重试")
    except Exception:
        raise HTTPException(status_code=500, detail="删除上传记录失败")
    return Response(status_code=status.HTTP_204_NO_CONTENT)