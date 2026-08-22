"""简历API端点，提供简历列表查询、详情查询（AI分析状态轮询）、删除与失败重试。"""

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_redis
from app.cos import CosError
from app.schemas.resume import ResumeListResponse, ResumeOut
from app.services.resume_service import (
    ResumeNotFoundError,
    ResumeNotRetryableError,
    resume_service,
)

router = APIRouter(prefix="/resumes", tags=["简历"])


def _get_user_id(payload: dict) -> int:
    """从认证载荷中解析当前用户ID。

    Args:
        payload: get_current_user依赖返回的JWT载荷字典。

    Returns:
        当前用户唯一标识。
    """
    return int(payload["sub"])


@router.get("", response_model=ResumeListResponse, summary="查询我的简历列表")
def list_my_resumes(
    page: int = Query(1, ge=1, le=1000, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="页大小（1-100）"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeListResponse:
    """分页查询当前用户的简历列表（含AI解析状态，按上传时间倒序）。

    Args:
        page: 页码。
        page_size: 页大小。
        payload: JWT认证载荷。
        db: 数据库同步会话。

    Returns:
        ResumeListResponse: 简历列表 + 总数 + 分页信息。
    """
    return resume_service.list_resumes(db, _get_user_id(payload), page, page_size)


@router.get("/{resume_id}", response_model=ResumeOut, summary="查询简历详情")
def get_resume_detail(
    resume_id: int = Path(..., ge=1, description="简历ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeOut:
    """查询简历详情（强制归属校验，仅本人可读；供前端轮询AI分析状态）。

    Args:
        resume_id: 简历ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。

    Returns:
        ResumeOut: 简历详情（含解析结果与工作经历）。

    Raises:
        HTTPException: 简历不存在或无权访问404。
    """
    try:
        return resume_service.get_resume(db, _get_user_id(payload), resume_id)
    except ResumeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简历不存在")


@router.delete(
    "/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除简历",
)
def delete_resume(
    resume_id: int = Path(..., ge=1, description="简历ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> Response:
    """软删除简历并联动清理下游资源（归属校验，仅本人可删，幂等）。

    软删 resume（释放 file_hash 唯一约束）+ 物理删关联上传记录/COS对象 +
    清理分析缓存 + 释放分析锁。删除后可重新上传同一文件。

    Args:
        resume_id: 简历ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端（缓存与锁）。

    Returns:
        204 No Content。

    Raises:
        HTTPException: 简历不存在或无权访问404；COS删除失败502。
    """
    try:
        resume_service.delete_resume(db, cache_client, _get_user_id(payload), resume_id)
    except ResumeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简历不存在")
    except CosError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="COS服务异常，请稍后重试")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{resume_id}/retry",
    response_model=ResumeOut,
    summary="失败简历一键重试",
)
def retry_resume_analysis(
    resume_id: int = Path(..., ge=1, description="简历ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache_client: redis.Redis = Depends(get_redis),
) -> ResumeOut:
    """对解析失败（status=2）的简历重新调度AI分析（归属校验，仅本人可操作）。

    重置状态为解析中 → 释放残留锁 → 抢锁并重新投递分析任务。

    Args:
        resume_id: 简历ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache_client: 同步Redis客户端（锁）。

    Returns:
        ResumeOut: 重试触发后的简历详情（status=0 解析中）。

    Raises:
        HTTPException: 简历不存在或无权访问404；非失败态409；调度异常500。
    """
    try:
        return resume_service.retry_analysis(db, cache_client, _get_user_id(payload), resume_id)
    except ResumeNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简历不存在")
    except ResumeNotRetryableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="重试分析失败，请稍后重试")
