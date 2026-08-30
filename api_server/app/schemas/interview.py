"""面试相关请求/响应模型（文档 §3.4 API 契约）。"""

from datetime import datetime

from pydantic import BaseModel, Field


class InterviewCreateRequest(BaseModel):
    """创建面试请求模型（§3.1）。"""

    resume_id: int = Field(..., ge=1, description="使用的简历ID")
    type: int = Field(1, ge=1, le=2, description="面试类型 1-完整面试 2-快速面试")
    tab_id: str = Field(..., min_length=1, max_length=64, description="创建面试的标签页唯一标识")


class QuestionOut(BaseModel):
    """当前题目输出模型（未完成面试仅返回当前题，§7.2）。"""

    question_index: int = Field(..., description="发问顺序题序（1起，含追问）")
    question_no: int = Field(..., description="基础题号（追问题与父题同号）")
    question_id: int = Field(..., description="题目ID")
    question_text: str = Field(..., description="题目内容")
    question_type: int = Field(..., description="题型 1-技术题 2-项目题 3-行为题")
    category: int | None = Field(None, description="维度 1-技术基础 2-项目经验 3-综合素质 4-架构设计")
    is_follow_up: bool = Field(False, description="是否追问题")


class InterviewCreateResponse(BaseModel):
    """创建面试响应模型（返回面试 id + epoch + 首题，§3.4）。"""

    interview_id: int = Field(..., description="面试会话ID（即 session_id）")
    epoch: int = Field(..., description="当前客户端持有的租约 epoch")
    status: int = Field(..., description="面试状态 0-进行中")
    type: int = Field(..., description="面试类型")
    total_questions: int = Field(..., description="基础题总数")
    current_question: QuestionOut | None = Field(None, description="首题")


class InterviewStateResponse(BaseModel):
    """面试当前状态响应模型（刷新恢复/超时兜底轮询，§3.4）。"""

    interview_id: int = Field(..., description="面试会话ID")
    status: int = Field(..., description="面试状态 0-进行中 1-已完成 2-已中断")
    type: int = Field(..., description="面试类型")
    phase: str = Field(..., description="阶段 not_started/answering/analyzing/summarizing/completed/aborted")
    question_index: int = Field(..., description="当前题序（状态版本token，§5.5）")
    epoch: int = Field(..., description="当前客户端租约 epoch（GET 携带 tab_id 时可能+1）")
    answered_count: int = Field(0, description="已答题数（含追问）")
    total_questions: int = Field(0, description="基础题总数")
    current_question: QuestionOut | None = Field(None, description="当前题目")


class AnswerSubmitRequest(BaseModel):
    """提交回答请求模型（§8.4）。"""

    question_index: int = Field(..., ge=1, description="所答题目题序（状态版本token）")
    answer: str = Field(..., min_length=1, max_length=10000, description="回答文本（语音转写或键盘输入）")
    tab_epoch: int = Field(..., ge=1, description="客户端租约 epoch（双开裁决）")
    answer_duration: int | None = Field(None, ge=0, le=3600, description="回答时长（秒）")


class AnswerAnalysisOut(BaseModel):
    """单题分析摘要输出模型（§9.2 合并输出的展示子集）。"""

    score: int = Field(..., description="综合评分 1-5")
    comment: str = Field(..., description="综合评价")
    correctness: str = Field("", description="正确性简述")
    technical_depth: int = Field(1, description="技术深度 1-5")
    completeness: int = Field(1, description="完整性 1-5")
    logic: int = Field(1, description="逻辑性 1-5")
    key_points: list[str] = Field(default_factory=list, description="回答要点")
    weaknesses: list[str] = Field(default_factory=list, description="薄弱点")


class AnswerSubmitResponse(BaseModel):
    """提交回答响应模型（分析摘要+评分+下一题或summarizing，§3.4）。"""

    interview_id: int = Field(..., description="面试会话ID")
    question_index: int = Field(..., description="本次已答题目题序")
    analysis: AnswerAnalysisOut = Field(..., description="本题主观分析摘要与评分")
    duplicated: bool = Field(False, description="是否命中幂等直接返回既有结果")
    phase: str = Field(..., description="下一阶段 answering/summarizing")
    next_question: QuestionOut | None = Field(None, description="下一题（追问或下一基础题）")


class AbortRequest(BaseModel):
    """主动放弃请求模型。"""

    tab_epoch: int = Field(..., ge=1, description="客户端租约 epoch")


class InterviewReportResponse(BaseModel):
    """面试报告响应模型（§13/§14.3）。"""

    interview_id: int = Field(..., description="面试会话ID")
    total_score: float = Field(..., description="总评分（百分制）")
    dimension_scores: dict[str, float] | None = Field(None, description="各维度得分")
    strengths: list[str] = Field(default_factory=list, description="回答优点")
    weaknesses: list[str] = Field(default_factory=list, description="知识薄弱点")
    capability_profile: dict[str, str] | None = Field(None, description="能力画像")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")
    summary: str = Field(..., description="总评")
    question_count: int = Field(0, description="题目数量")
    follow_up_count: int = Field(0, description="追问次数")
    total_duration: int | None = Field(None, description="面试总时长（秒）")
    created_at: datetime = Field(..., description="报告生成时间")

    model_config = {"from_attributes": True}


class ReportStatusResponse(BaseModel):
    """报告状态响应模型（未生成时返回generating，§13.1）。"""

    status: str = Field(..., description="generating/ready/failed/invalid")
    report: InterviewReportResponse | None = Field(None, description="报告内容（status=ready时返回）")


class InterviewListItem(BaseModel):
    """面试记录列表项模型（历史页展示）。"""

    interview_id: int = Field(..., description="面试会话ID")
    status: int = Field(..., description="面试状态 0-进行中 1-已完成 2-已中断")
    type: int = Field(..., description="面试类型 1-完整 2-快速")
    total_score: float | None = Field(None, description="面试总分（已完成）")
    follow_up_count: int = Field(0, description="追问次数")
    question_count: int = Field(0, description="基础题总数")
    answered_count: int = Field(0, description="已答题数（含追问）")
    report_ready: bool = Field(False, description="报告是否已生成")
    is_started: bool = Field(True, description="是否已正式启动（False=草稿，待设备检测）")
    created_at: datetime = Field(..., description="创建时间")
    interview_time: datetime | None = Field(None, description="完成时间")
    total_duration: int | None = Field(None, description="面试总时长（秒）")


class InterviewListResponse(BaseModel):
    """面试记录列表响应模型（分页）。"""

    items: list[InterviewListItem] = Field(..., description="面试记录列表")
    total: int = Field(..., description="记录总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="页大小")


class InterviewQuestionDetail(BaseModel):
    """逐题详情模型（仅已结束面试返回全量，§7.2约束）。"""

    question_index: int = Field(..., description="发问顺序题序（1起，含追问）")
    question_no: int = Field(..., description="基础题号（追问题与父题同号）")
    question_id: int = Field(..., description="题目ID")
    question_text: str = Field(..., description="题目内容")
    question_type: int = Field(..., description="题型 1-技术题 2-项目题 3-行为题")
    category: int | None = Field(None, description="维度 1-技术基础 2-项目经验 3-综合素质 4-架构设计")
    is_follow_up: bool = Field(False, description="是否追问题")
    user_answer: str | None = Field(None, description="用户回答")
    ai_score: int | None = Field(None, description="AI评分 1-5")
    ai_comment: str | None = Field(None, description="AI评价")
    answer_duration: int | None = Field(None, description="回答时长（秒）")


class InterviewQuestionListResponse(BaseModel):
    """逐题详情列表响应模型。"""

    items: list[InterviewQuestionDetail] = Field(..., description="题目列表（发问顺序）")
    total: int = Field(..., description="题目总数")
