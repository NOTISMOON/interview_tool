"""面试API端点（文档 §3.4 契约）。

同步 HTTP 为主（单次 LLM 调用 5~15 秒），不经过 MQ；
SSE 只做通知不承载数据。冲突响应（409）携带最新状态供前端强制同步。
"""

import redis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_redis
from app.db.sync_session import SyncSessionLocal
from app.models.message import MESSAGE_TYPE_INTERVIEW
from app.schemas.interview import (
    AbortRequest,
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    InterviewCreateRequest,
    InterviewCreateResponse,
    InterviewListItem,
    InterviewListResponse,
    InterviewQuestionDetail,
    InterviewQuestionListResponse,
    InterviewReportResponse,
    InterviewStateResponse,
    ReportStatusResponse,
)
from app.services.interview_service import (
    InterviewConflictError,
    InterviewNotFoundError,
    ResumeNotReadyError,
    interview_service,
)
from app.services.notification_service import notification_service

router = APIRouter(prefix="/interviews", tags=["面试"])


def _get_user_id(payload: dict) -> int:
    """从认证载荷中解析当前用户ID。

    Args:
        payload: get_current_user依赖返回的JWT载荷字典。

    Returns:
        当前用户唯一标识。
    """
    return int(payload["sub"])


def _raise_conflict(exc: InterviewConflictError) -> None:
    """将并发冲突异常转为409响应（携带最新状态强制同步，§5.5）。

    Args:
        exc: 服务层抛出的冲突异常。

    Raises:
        HTTPException: 409 + 冲突原因与最新状态。
    """
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"reason": exc.reason, "latest_state": exc.state},
    )


@router.post(
    "",
    response_model=InterviewCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建面试会话",
)
def create_interview(
    req: InterviewCreateRequest,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> InterviewCreateResponse:
    """创建面试：校验简历归属与状态，预生成基础题并返回首题（§3/§7）。

    Args:
        req: 创建请求（resume_id/type/tab_id）。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端。

    Returns:
        InterviewCreateResponse: 面试id + epoch + 首题。

    Raises:
        HTTPException: 简历不存在404；分析中/失败409；LLM出题失败503。
    """
    try:
        result = interview_service.create_interview(
            db, cache, _get_user_id(payload), req.resume_id, req.type, req.tab_id
        )
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="简历不存在")
    except ResumeNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="面试创建失败（题目生成异常），请稍后重试",
        )
    # 题目生成完成：投递面试就绪通知（独立session，失败不阻断主流程）。
    # 用户切走页面后可从消息中心/历史记录进入对应设备检测路由（§3 方案：草稿互不影响）。
    user_id = _get_user_id(payload)
    interview_type = "完整面试" if req.type == 1 else "快速面试"
    notif_db = SyncSessionLocal()
    try:
        notification_service.create_notification(
            notif_db,
            recipient_id=user_id,
            msg_type=MESSAGE_TYPE_INTERVIEW,
            title="面试题已生成，待设备检测",
            content=f"你的{interview_type}题目已生成完毕，点击进入设备检测后即可开始作答。",
            from_user_id=None,
            related_id=result["interview_id"],
            related_type=4,  # 关联实体类型：4-interview（面试），前端据此跳设备检测
        )
        notif_db.commit()
    except Exception:
        import logging

        logging.getLogger(__name__).exception("面试就绪通知投递失败: interview_id=%s", result.get("interview_id"))
    finally:
        notif_db.close()
    return InterviewCreateResponse(**result)


@router.get(
    "",
    response_model=InterviewListResponse,
    summary="查询我的面试记录列表",
)
def list_interviews(
    page: int = Query(1, ge=1, le=1000, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="页大小（1-100）"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> InterviewListResponse:
    """分页查询当前用户面试记录（含进行中/已完成/已中断，报告就绪标志）。

    Args:
        page: 页码。
        page_size: 页大小。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端（草稿态判定）。

    Returns:
        InterviewListResponse: 记录列表 + 总数 + 分页信息。
    """
    result = interview_service.list_interviews(db, cache, _get_user_id(payload), page, page_size)
    return InterviewListResponse(
        items=[InterviewListItem(**item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get(
    "/stats",
    summary="查询面试统计（次数与平均分）",
)
def get_interview_stats(
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """查询控制台面试统计：总次数/完成数/平均分（§统计口径）。

    统计包含软删除记录——删除面试不影响平均分与完成数；总次数为未删除
    可见记录数（历史页分页口径）。

    Args:
        payload: JWT认证载荷。
        db: 数据库同步会话。

    Returns:
        {"total": 可见记录总数, "completed_count": 已完成次数, "avg_score": 平均分}。
    """
    return interview_service.get_stats(db, _get_user_id(payload))


@router.get(
    "/{interview_id}/questions",
    response_model=InterviewQuestionListResponse,
    summary="查询已结束面试的逐题详情",
)
def list_interview_questions(
    interview_id: int = Path(..., ge=1, description="面试会话ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewQuestionListResponse:
    """查询逐题详情（仅已结束面试返回全量题目，§7.2约束）。

    Args:
        interview_id: 面试会话ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。

    Returns:
        InterviewQuestionListResponse: 题目/回答/评分列表（发问顺序）。

    Raises:
        HTTPException: 面试不存在404；进行中409。
    """
    try:
        result = interview_service.list_questions(db, _get_user_id(payload), interview_id)
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    except InterviewConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="面试进行中，暂不可查看题目"
        )
    return InterviewQuestionListResponse(
        items=[InterviewQuestionDetail(**item) for item in result["items"]],
        total=result["total"],
    )


@router.get(
    "/{interview_id}",
    response_model=InterviewStateResponse,
    summary="查询面试当前状态",
)
def get_interview_state(
    interview_id: int = Path(..., ge=1, description="面试会话ID"),
    tab_id: str | None = Query(None, max_length=64, description="标签页标识（进入/刷新面试页时传，触发租约激活）"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> InterviewStateResponse:
    """查询面试状态（刷新恢复/超时兜底轮询，§3.4/§15）。

    Args:
        interview_id: 面试会话ID。
        tab_id: 标签页标识（同页幂等返回当前epoch，新页接管epoch+1）。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端。

    Returns:
        InterviewStateResponse: phase/question_index/epoch/当前题。

    Raises:
        HTTPException: 面试不存在404。
    """
    try:
        state = interview_service.get_state(
            db, cache, _get_user_id(payload), interview_id, tab_id
        )
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    return InterviewStateResponse(**state)


@router.post(
    "/{interview_id}/start",
    response_model=InterviewStateResponse,
    summary="设备检测通过后正式启动面试",
)
def start_interview(
    interview_id: int = Path(..., ge=1, description="面试会话ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> InterviewStateResponse:
    """设备检测通过后启动面试：草稿态 not_started → answering（§3，幂等）。

    Args:
        interview_id: 面试会话ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端。

    Returns:
        InterviewStateResponse: 最新状态（phase=answering）。

    Raises:
        HTTPException: 面试不存在404；已完成/中断409。
    """
    try:
        state = interview_service.start_interview(
            db, cache, _get_user_id(payload), interview_id
        )
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    except InterviewConflictError as exc:
        _raise_conflict(exc)
    return InterviewStateResponse(**state)


@router.post(
    "/{interview_id}/answers",
    response_model=AnswerSubmitResponse,
    summary="提交回答",
)
def submit_answer(
    req: AnswerSubmitRequest,
    background_tasks: BackgroundTasks,
    interview_id: int = Path(..., ge=1, description="面试会话ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> AnswerSubmitResponse:
    """提交回答：同步返回分析摘要+评分+下一题（或summarizing，§8.4/§9）。

    幂等键 (interview_id, question_index)：已分析的题直接返回既有结果；
    全部题目完成后经后台任务生成最终报告（§13.1）。

    Args:
        interview_id: 面试会话ID。
        req: 提交请求（question_index/answer/tab_epoch）。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端。
        background_tasks: FastAPI后台任务（报告异步生成）。

    Returns:
        AnswerSubmitResponse: 分析摘要+评分+下一题。

    Raises:
        HTTPException: 面试不存在404；冲突409（含最新状态）；分析失败502。
    """
    try:
        result = interview_service.submit_answer(
            db, cache, _get_user_id(payload), interview_id,
            req.question_index, req.answer, req.tab_epoch, req.answer_duration,
        )
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    except InterviewConflictError as exc:
        _raise_conflict(exc)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="回答分析服务异常，请稍后重试",
        )
    # 最后一题分析完 → 后台生成报告（BackgroundTasks，操作锁保护，§13.1）
    if result["phase"] == "summarizing":
        background_tasks.add_task(interview_service.generate_report_background, cache, interview_id)
    return AnswerSubmitResponse(**result)


@router.get(
    "/{interview_id}/report",
    response_model=ReportStatusResponse,
    summary="获取面试报告",
)
def get_interview_report(
    interview_id: int = Path(..., ge=1, description="面试会话ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> ReportStatusResponse:
    """获取面试报告（未生成时返回generating并惰性兜底触发，§13.1）。

    Args:
        interview_id: 面试会话ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端。

    Returns:
        ReportStatusResponse: generating/ready/failed/invalid + 报告内容。

    Raises:
        HTTPException: 面试不存在404。
    """
    try:
        result = interview_service.get_report(db, cache, _get_user_id(payload), interview_id)
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    report = result.get("report")
    return ReportStatusResponse(
        status=result["status"],
        report=InterviewReportResponse.model_validate(report) if report is not None else None,
    )


@router.post(
    "/{interview_id}/report/regenerate",
    response_model=ReportStatusResponse,
    summary="报告生成失败手动重试",
)
def regenerate_report(
    interview_id: int = Path(..., ge=1, description="面试会话ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> ReportStatusResponse:
    """报告手动重试（LLM失败后暴露，重置失败计数重新生成，§13.1）。

    Args:
        interview_id: 面试会话ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端。

    Returns:
        ReportStatusResponse: generating。

    Raises:
        HTTPException: 面试不存在404；未完成409。
    """
    try:
        result = interview_service.regenerate_report(db, cache, _get_user_id(payload), interview_id)
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    except InterviewConflictError as exc:
        _raise_conflict(exc)
    return ReportStatusResponse(status=result, report=None)


@router.post(
    "/{interview_id}/abort",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="主动放弃面试",
)
def abort_interview(
    req: AbortRequest,
    interview_id: int = Path(..., ge=1, description="面试会话ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> Response:
    """主动放弃：status=2（已中断），已答题目与评分保留（§21）。

    Args:
        req: 放弃请求（tab_epoch）。
        interview_id: 面试会话ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端。

    Returns:
        204 No Content。

    Raises:
        HTTPException: 面试不存在404；epoch不符/已结束409。
    """
    try:
        interview_service.abort(db, cache, _get_user_id(payload), interview_id, req.tab_epoch)
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    except InterviewConflictError as exc:
        _raise_conflict(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{interview_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除面试记录（软删除）",
)
def delete_interview(
    interview_id: int = Path(..., ge=1, description="面试会话ID"),
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
) -> Response:
    """软删除面试记录（草稿/进行中/已中断/已完成均可删除）。

    仅标记 is_deleted=1：历史列表移除，但题目/报告/总分保留，控制台
    平均分统计不受影响；同时清理 Redis Checkpoint 与关联就绪通知。

    Args:
        interview_id: 面试会话ID。
        payload: JWT认证载荷。
        db: 数据库同步会话。
        cache: 同步Redis客户端。

    Returns:
        204 No Content。

    Raises:
        HTTPException: 面试不存在404；并发冲突409。
    """
    try:
        interview_service.delete_record(db, cache, _get_user_id(payload), interview_id)
    except InterviewNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试不存在")
    except InterviewConflictError as exc:
        _raise_conflict(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
