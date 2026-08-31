"""面试模块 LangGraph 工作流（v2·单图承载面试节奏 + Fast Decision 即时判定）。

按《面试模块单LangGraph架构方案.md》重构：
    - 单个 InterviewGraph 承载整场面试节奏控制（thread_id = interview_id），
      用 LangGraph checkpointer（Redis，跨进程共享持久化）保存题目队列、
      当前题序等图内状态，重启/刷新后可恢复。
    - 图中含 question_generation / speech_correct / fast_decision / routing 节点：
        创建面试:  init -> question_agent(批量预生成基础题) -> routing(出首题)
        提交回答:  speech_correct(LLM 纠错语音识别文本)
                   -> fast_decision(即时判定下一题: 追问/下一基础/结束)
                   -> routing(出下一题 / 结束)。
    - 全量分析评分（Answer Analysis / Score）不走同步路径，由异步 Worker
      消费 outbox 事件完成（见 app/mq/consumers/interview_analysis_consumer.py）。

安全设计（对齐项目记忆中的关键工程约束）：
    - 幂等 MUST 留在 service 层：图只做「给定当前题回答，产出下一题」的单步推进，
      不引入 interrupt/resume 双推进；重复 POST 由 _advance_with_lock 幂等预检拦截。
    - persist / 并发控制留在 API 层：图不写库、不碰锁/epoch；只负责 LLM 决策与
      状态轻量推进，题目与回答的落库、三层并发控制仍由 interview_service 编排。
    - answer_analysis 仍是「单次合并 LLM 节点」（不拆分 Score），只是移到异步路径。

同步路径 LLM 调用仅三款：
    1. question_generation（创建时一次，批量出题）
    2. speech_correct（每次回答后，纠错语音识别文本，最小改动）
    3. fast_decision（每次回答后亚秒级，判定追问/下一题）
异步路径另用 AnswerAnalysisGraph（Worker 内 4 路并行分析后聚合），追问由主图生成。
"""

import asyncio
import json
import logging
from typing import TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.redis import RedisSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.llm.models import interview_model
from app.llm.prompt import (
    COMPLETENESS_LOGIC_PROMPT,
    CONTENT_ANALYSIS_PROMPT,
    FAST_DECISION_PROMPT,
    QUESTION_GENERATION_PROMPT,
    REPORT_SUMMARY_PROMPT,
    SCORING_PROMPT,
    SPEECH_CORRECTION_PROMPT,
    TECHNICAL_DEPTH_PROMPT,
)
from app.llm.schemas.interview import (
    AnswerAnalysisResult,
    CompletenessLogicResult,
    ContentAnalysisResult,
    FastDecisionResult,
    InterviewReportResult,
    QuestionGenerationResult,
    ScoringResult,
    SpeechCorrectionResult,
    TechnicalDepthResult,
)

logger = logging.getLogger(__name__)

# 面试类型 -> 出题量要求（§7.2：type=1 完整 15 题 / type=2 快速 9 题）
# 四维度：1-技术八股 2-项目与社会实践 4-架构设计 3-综合素养（两类型均覆盖四维度，综合素养固定最后）
TYPE_REQUIREMENTS = {
    1: "完整面试，共生成 15 道基础题（技术八股3题、项目与社会实践7题、架构设计2题、综合素养3题）",
    2: "快速面试，共生成 9 道基础题（技术八股2题、项目与社会实践4题、架构设计1题、综合素养2题）",
}

# 决策动作常量（FastDecisionResult.next_action）
ACTION_FOLLOW_UP = "follow_up"
ACTION_NEXT_BASE = "next_base"
ACTION_END = "end"


# --------------------------------------------------------------------------
# 单图状态
# --------------------------------------------------------------------------

class InterviewState(TypedDict, total=False):
    """面试节奏控制图状态（thread 级）。"""

    interview_id: int  # thread_id（== interview 主键）
    interview_type: int  # 1-完整 2-快速
    resume_context: dict  # 简历结构化上下文

    # 基础题（创建时预生成，已落库；此处为主要供 Fast Decision 判定是否问尽）
    base_questions: list[dict]  # [{question_no, question_id, question_type, category, question_text}]
    base_count: int  # 基础题总数

    # 本轮输入（service 提交回答时写入）
    question_no: int  # 当前回答的基础题号
    question_text: str  # 当前题目文本（Fast Decision 判定追问贴合回答）
    answer: str  # 用户回答文本

    # 图输出（下一题判定结果）
    next_action: str  # follow_up / next_base / end
    follow_up_question: str | None  # 判定的追问（若 follow_up）

    # 计数值（service 落库后回写，供终止判断）
    follow_up_total: int  # 全场追问总数（service 从 DB 统计回写）
    unanswered_base_after: int  # 当前基础题之后未答的基础题数（service 回写）


# --------------------------------------------------------------------------
# checkpointer
# --------------------------------------------------------------------------

def build_checkpointer() -> RedisSaver:
    """构建面试图 Redis checkpointer（跨进程共享图状态）。

    使用项目 Redis（Redis Stack，内置 RedisJSON/RediSearch 模块）存储
    LangGraph 检查点，多进程/多 worker 共享同一份图状态，不落本地磁盘文件。
    图状态可从 MySQL/Redis 业务数据重建，Redis 中仅作运行态冗余缓存。

    Returns:
        RedisSaver 实例（已 setup 建索引）。
    """
    saver = RedisSaver(redis_url=settings.REDIS_URL)
    saver.setup()
    return saver


# 模块级 checkpointer（图编译时绑定；invoke 时按 thread_id 读写持久化状态）
interview_graph_checkpointer = build_checkpointer()


# --------------------------------------------------------------------------
# 节点
# --------------------------------------------------------------------------

def _init(state: InterviewState) -> InterviewState:
    """节点 init：初始化基础题列表与计数值。"""
    base = state.get("base_questions") or []
    return {
        "interview_id": state.get("interview_id"),
        "interview_type": state.get("interview_type", 1),
        "base_questions": base,
        "base_count": len(base),
    }


def _question_agent(state: InterviewState) -> InterviewState:
    """节点 question_agent：LLM 批量预生成基础题（创建时一次，§7.2）。

    由 service 在创建时调用 generate_questions() 预生成并落库，此处仅在
    state 未携带基础题时兜底生成（正常流程 service 已预置，跳过 LLM）。

    Returns:
        填入基础题列表的 state。
    """
    if state.get("base_questions"):
        return {"base_questions": state["base_questions"], "base_count": len(state["base_questions"])}
    resume_context = state.get("resume_context") or {}
    interview_type = state.get("interview_type", 1)
    result = _generate_questions_impl(resume_context, interview_type)
    base = [
        {
            "question_text": q.question_text,
            "question_type": q.question_type,
            "category": q.category,
        }
        for q in result.questions
    ]
    return {"base_questions": base, "base_count": len(base)}


def _fast_decision(state: InterviewState) -> InterviewState:
    """节点 fast_decision：即时判定下一题（追问/下一基础/结束）。

    轻量 Fast LLM（低 temp 短 prompt），亚秒级返回 {next_action, follow_up_question,
    technical_depth_hint}。题目是否问尽由 service 依据 DB 题目推进判定传入。

    Returns:
        next_action 与 follow_up_question。
    """
    model: BaseChatModel = interview_model
    prompt = FAST_DECISION_PROMPT.format(
        question=state.get("question_text", state.get("question_no", "")),
        answer=state.get("answer", ""),
        resume_context=json.dumps(state.get("resume_context") or {}, ensure_ascii=False, default=str),
    )
    structured = model.with_structured_output(FastDecisionResult, method="json_mode")
    result = structured.invoke(prompt)
    if not isinstance(result, FastDecisionResult):
        raise ValueError(f"Fast Decision 结果类型异常: {type(result)}")

    action = result.next_action
    if action not in (ACTION_FOLLOW_UP, ACTION_NEXT_BASE, ACTION_END):
        action = ACTION_NEXT_BASE
    # follow_up 必须附带追问文本；缺省回退下一基础题
    if action == ACTION_FOLLOW_UP and not result.follow_up_question:
        action = ACTION_NEXT_BASE
    logger.info(
        "Fast Decision: interview_id=%s question_no=%s action=%s depth_hint=%s",
        state.get("interview_id"), state.get("question_no"), action, result.technical_depth_hint,
    )
    return {
        "next_action": action,
        "follow_up_question": result.follow_up_question if action == ACTION_FOLLOW_UP else None,
    }


def _speech_correct(state: InterviewState) -> InterviewState:
    """节点 speech_correct：LLM 纠错语音识别文本（最小改动，仅修正识别错误）。

    在 fast_decision 前对原始 ASR 文本做同音/近音/技术术语纠错，结果覆写
    state.answer，供 fast_decision 路由与 service 落库、异步分析复用。
    纠错失败（LLM 异常或空输出）回退原文，绝不阻塞提交链路。

    Returns:
        覆写 answer 为纠错后文本的 state。
    """
    raw = (state.get("answer") or "").strip()
    if not raw:
        # 无回答（创建时兜底等场景）不纠错，原样返回
        return {"answer": state.get("answer") or ""}
    prompt = SPEECH_CORRECTION_PROMPT.format(
        question=state.get("question_text", ""),
        resume_context=json.dumps(state.get("resume_context") or {}, ensure_ascii=False, default=str),
        transcript=raw,
    )
    model: BaseChatModel = interview_model
    structured = model.with_structured_output(SpeechCorrectionResult, method="json_mode")
    try:
        result = structured.invoke(prompt)
        corrected = result.corrected_text.strip() if isinstance(result, SpeechCorrectionResult) else ""
    except Exception:
        # 纠错 LLM 失败不阻塞提交：回退原文，由 service 原样落库/分析
        logger.exception("语音纠错失败，回退原文: interview_id=%s", state.get("interview_id"))
        corrected = ""
    if not corrected:
        corrected = raw
    if corrected != raw:
        logger.info(
            "语音纠错: interview_id=%s len=%s->%s",
            state.get("interview_id"), len(raw), len(corrected),
        )
    return {"answer": corrected}


def _route(state: InterviewState) -> InterviewState:
    """节点 routing：按 next_action 分派（服务层据以返回下一题/结束）。

    图内仅做动作标准化：end 且题目未问尽时回退下一基础题（防御）。
    """
    action = state.get("next_action", ACTION_NEXT_BASE)
    unanswered_after = int(state.get("unanswered_base_after", 0))
    if action == ACTION_END and unanswered_after > 0:
        # 防御：Fast LLM 误判"无下一题"，但 DB 还有未答基础题 → 回退下一基础题
        logger.warning(
            "Fast Decision 误判 end 但仍有未答基础题: interview_id=%s unanswered_after=%s",
            state.get("interview_id"), unanswered_after,
        )
        action = ACTION_NEXT_BASE
    return {"next_action": action}


def build_interview_graph():
    """构建并编译面试节奏控制图（绑定 SQLite checkpointer）。"""
    builder = StateGraph(InterviewState)
    builder.add_node("init", _init)
    builder.add_node("question_agent", _question_agent)
    builder.add_node("speech_correct", _speech_correct)
    builder.add_node("fast_decision", _fast_decision)
    builder.add_node("route", _route)
    builder.add_edge(START, "init")
    builder.add_edge("init", "question_agent")
    builder.add_edge("question_agent", "speech_correct")
    builder.add_edge("speech_correct", "fast_decision")
    builder.add_edge("fast_decision", "route")
    builder.add_edge("route", END)
    graph = builder.compile(checkpointer=interview_graph_checkpointer)
    logger.info(
        "面试节奏控制图已编译 checkpointer=%s",
        settings.REDIS_URL.split("@")[-1],
    )
    return graph


interview_graph = build_interview_graph()


def _thread_config(interview_id: int) -> dict:
    """构造 graph invoke 的 thread 配置（thread_id = interview_id）。

    Args:
        interview_id: 面试会话主键。

    Returns:
        langgraph config 字典。
    """
    return {"configurable": {"thread_id": str(interview_id)}}


def run_fast_decision(
    interview_id: int,
    interview_type: int,
    resume_context: dict,
    base_questions: list[dict],
    question_no: int,
    question_text: str,
    answer: str,
    follow_up_total: int,
    unanswered_base_after: int,
) -> dict:
    """执行单轮 Fast Decision，即时返回下一题判定结果。

    以 (question_no, question_text, answer) 推进图状态并调用 fast_decision + route，
    完整结果供 service 落库与响应组装。

    Args:
        interview_id: 面试会话ID（thread_id）。
        interview_type: 面试类型 1-完整 2-快速。
        resume_context: 简历结构化上下文。
        base_questions: 基础题列表（question_no/question_id/question_type/category/question_text）。
        question_no: 当前回答的基础题号。
        question_text: 当前题目文本。
        answer: 用户回答文本。
        follow_up_total: 全场当前追问总数（用于终止判断，由图状态保留）。
        unanswered_base_after: 当前基础题之后未答的基础题数。

    Returns:
        {"next_action", "follow_up_question", "corrected_text"}。
    """
    # RedisSaver 基于 redis-py 连接池，天然线程安全，无需额外互斥锁
    result = interview_graph.invoke(
        {
            "interview_id": interview_id,
            "interview_type": interview_type,
            "resume_context": resume_context,
            "base_questions": base_questions,
            "question_no": question_no,
            "question_text": question_text,
            "answer": answer,
            "follow_up_total": follow_up_total,
            "unanswered_base_after": unanswered_base_after,
        },
        config=_thread_config(interview_id),
    )
    # speech_correct 节点已把 state.answer 覆写为纠错后文本（未纠错时等于原文）
    return {
        "next_action": result["next_action"],
        "follow_up_question": result.get("follow_up_question"),
        "corrected_text": result.get("answer") or "",
    }


def invalidate_checkpoint(interview_id: int) -> None:
    """清除面试图检查点（面试完成/中断后的清理，释放 Redis 空间）。

    调用方需保证 interview_id 不再需要图状态恢复。

    Args:
        interview_id: 面试会话ID。
    """
    try:
        interview_graph_checkpointer.delete_thread(str(interview_id))
    except Exception:
        logger.exception("清除面试图检查点失败: interview_id=%s", interview_id)


# --------------------------------------------------------------------------
# 基础题预生成（§7；创建时一次，由 service 调用）
# --------------------------------------------------------------------------

def _generate_questions_impl(resume_context: dict, interview_type: int) -> QuestionGenerationResult:
    """执行 LLM 批量出题（内部实现，供图外调用与图内兜底复用）。

    Args:
        resume_context: 简历结构化上下文。
        interview_type: 面试类型 1-完整 2-快速。

    Returns:
        QuestionGenerationResult 基础题列表。

    Raises:
        ValueError: LLM 输出为空或类型异常。
        Exception: LLM 调用失败（由上层按 §21 转 503）。
    """
    prompt = QUESTION_GENERATION_PROMPT.format(
        type_requirement=TYPE_REQUIREMENTS.get(interview_type, TYPE_REQUIREMENTS[1]),
        resume_context=json.dumps(resume_context, ensure_ascii=False, default=str),
    )
    model: BaseChatModel = interview_model
    structured = model.with_structured_output(QuestionGenerationResult, method="json_mode")
    result = structured.invoke(prompt)
    if not isinstance(result, QuestionGenerationResult) or not result.questions:
        raise ValueError(f"LLM出题结果异常: {type(result)}")
    logger.info("基础题预生成完成: type=%s count=%s", interview_type, len(result.questions))
    return result


def generate_questions(resume_context: dict, interview_type: int) -> QuestionGenerationResult:
    """执行基础题预生成工作流（§7.2，service 创建面试时调用，兼容旧调用方）。

    Args:
        resume_context: 简历结构化上下文（技能/项目/工作经历/教育经历）。
        interview_type: 面试类型 1-完整 2-快速。

    Returns:
        QuestionGenerationResult 基础题列表。

    Raises:
        ValueError: LLM 输出为空或类型异常。
        Exception: LLM 调用失败（由上层按 §21 转 503）。
    """
    return _generate_questions_impl(resume_context, interview_type)


# --------------------------------------------------------------------------
# 异步回答分析图（§9，Worker 内执行；4 路并行分支后聚合，降低单题分析时延）
# --------------------------------------------------------------------------


class AnswerAnalysisState(TypedDict, total=False):
    """回答分析图状态（每题一次，聚合节点产出最终结果）。

    - 输入：question / answer / resume_context。
    - 各并行分支各写一个字段：content / technical / completeness / scoring。
    - aggregate 汇聚四个分支为 result。
    """

    question: str  # 当前题目文本
    answer: str  # 用户回答文本
    resume_context: dict  # 简历结构化上下文
    content: ContentAnalysisResult  # 分支·内容分析
    technical: TechnicalDepthResult  # 分支·技术深度
    completeness: CompletenessLogicResult  # 分支·完整性与逻辑性
    scoring: ScoringResult  # 分支·综合评分与评价
    result: AnswerAnalysisResult  # 聚合结果


def _structured_invoke(model: BaseChatModel, result_cls: type, prompt_str: str) -> object:
    """以 json_mode 让模型输出指定结构，并校验返回类型。

    Args:
        model: 底层聊天模型实例。
        result_cls: 期望的结构化输出 Pydantic 类。
        prompt_str: 提示词文本。

    Returns:
        result_cls 的实例。

    Raises:
        ValueError: LLM 输出类型异常。
    """
    structured = model.with_structured_output(result_cls, method="json_mode")
    result = structured.invoke(prompt_str)
    if not isinstance(result, result_cls):
        raise ValueError(f"LLM结构化输出类型异常: expected={result_cls.__name__} got={type(result)}")
    return result


def _content_analysis(state: AnswerAnalysisState) -> dict:
    """分析图节点·内容分析：切题性 + 要点 + 薄弱点。"""
    prompt = CONTENT_ANALYSIS_PROMPT.format(
        question=state.get("question", ""),
        answer=state.get("answer", ""),
    )
    return {"content": _structured_invoke(interview_model, ContentAnalysisResult, prompt)}


def _technical_depth(state: AnswerAnalysisState) -> dict:
    """分析图节点·技术深度评分。"""
    prompt = TECHNICAL_DEPTH_PROMPT.format(
        question=state.get("question", ""),
        answer=state.get("answer", ""),
    )
    return {"technical": _structured_invoke(interview_model, TechnicalDepthResult, prompt)}


def _completeness_logic(state: AnswerAnalysisState) -> dict:
    """分析图节点·完整性与逻辑性评分。"""
    prompt = COMPLETENESS_LOGIC_PROMPT.format(
        question=state.get("question", ""),
        answer=state.get("answer", ""),
    )
    return {"completeness": _structured_invoke(interview_model, CompletenessLogicResult, prompt)}


def _scoring(state: AnswerAnalysisState) -> dict:
    """分析图节点·综合评分与评价。"""
    prompt = SCORING_PROMPT.format(
        question=state.get("question", ""),
        answer=state.get("answer", ""),
        resume_context=json.dumps(state.get("resume_context") or {}, ensure_ascii=False, default=str),
    )
    return {"scoring": _structured_invoke(interview_model, ScoringResult, prompt)}


def _aggregate(state: AnswerAnalysisState) -> dict:
    """分析图节点·汇聚节点（等所有分支完成后执行），合并为 AnswerAnalysisResult。"""
    content = state["content"]
    technical = state["technical"]
    completeness = state["completeness"]
    scoring = state["scoring"]
    result = AnswerAnalysisResult(
        correctness=content.correctness,
        technical_depth=technical.technical_depth,
        completeness=completeness.completeness,
        logic=completeness.logic,
        key_points=content.key_points,
        weaknesses=content.weaknesses,
        score=scoring.score,
        comment=scoring.comment,
    )
    return {"result": result}


def build_answer_analysis_graph():
    """构建并编译回答分析图（4 路并行扇出 + 汇聚）。

    START 同时指向 4 个并行分支（扇出），4 个分支再汇聚到 aggregate（扇入，
    汇聚节点会等待所有前驱完成）。同步 invoke 下并行分支在线程池并发执行。
    """
    builder = StateGraph(AnswerAnalysisState)
    builder.add_node("content_analysis", _content_analysis)
    builder.add_node("technical_depth", _technical_depth)
    builder.add_node("completeness_logic", _completeness_logic)
    builder.add_node("scoring", _scoring)
    builder.add_node("aggregate", _aggregate)
    # 扇出：四路并行分支
    builder.add_edge(START, "content_analysis")
    builder.add_edge(START, "technical_depth")
    builder.add_edge(START, "completeness_logic")
    builder.add_edge(START, "scoring")
    # 扇入：四路均完成后进入聚合节点
    builder.add_edge("content_analysis", "aggregate")
    builder.add_edge("technical_depth", "aggregate")
    builder.add_edge("completeness_logic", "aggregate")
    builder.add_edge("scoring", "aggregate")
    builder.add_edge("aggregate", END)
    graph = builder.compile()
    logger.info("回答分析图已编译（4 路并行分支）")
    return graph


answer_analysis_graph = build_answer_analysis_graph()


def analyze_answer(question: str, answer: str, resume_context: dict) -> AnswerAnalysisResult:
    """执行回答并行分析工作流图（同步入口）。

    运行 AnswerAnalysisGraph：4 路并行 LLM 分支（内容/技术深度/完整逻辑/综合评分）
    后聚合为 AnswerAnalysisResult。同步 invoke 下并行分支在线程池并发执行，
    单题分析时延从"单次全量"降为"最慢分支"。

    Args:
        question: 当前题目文本。
        answer: 用户回答文本。
        resume_context: 简历结构化上下文。

    Returns:
        AnswerAnalysisResult 分析+评分结果（不含追问）。

    Raises:
        Exception: 任一并行分支 LLM 调用失败时抛出（由 Worker 重试/标记失败）。
    """
    state = answer_analysis_graph.invoke(
        {
            "question": question,
            "answer": answer,
            "resume_context": resume_context or {},
        }
    )
    result = state["result"]
    logger.info(
        "回答并行分析完成: score=%s depth=%s comments=%s",
        result.score, result.technical_depth, len(result.comment),
    )
    return result


async def analyze_answer_parallel(
    question: str, answer: str, resume_context: dict
) -> AnswerAnalysisResult:
    """异步执行回答并行分析工作流图（供异步 Worker 使用）。

    Args:
        question: 当前题目文本。
        answer: 用户回答文本。
        resume_context: 简历结构化上下文。

    Returns:
        AnswerAnalysisResult 分析+评分结果。

    Raises:
        Exception: 任一并行分支 LLM 调用失败时抛出。
    """
    return await asyncio.to_thread(analyze_answer, question, answer, resume_context)


# --------------------------------------------------------------------------
# 报告生成（§13，Summary Agent；不变）
# --------------------------------------------------------------------------

def _generate_report_impl(resume_context: dict, records: list[dict]) -> InterviewReportResult:
    """执行报告生成 LLM 调用（内部实现）。

    Args:
        resume_context: 简历结构化上下文。
        records: 整场面试记录（题目/回答/评分/评价）。

    Returns:
        InterviewReportResult 最终报告结构。

    Raises:
        ValueError: LLM 输出类型异常。
        Exception: LLM 调用失败。
    """
    prompt = REPORT_SUMMARY_PROMPT.format(
        resume_context=json.dumps(resume_context, ensure_ascii=False, default=str),
        interview_records=json.dumps(records, ensure_ascii=False, default=str),
    )
    model: BaseChatModel = interview_model
    structured = model.with_structured_output(InterviewReportResult, method="json_mode")
    result = structured.invoke(prompt)
    if not isinstance(result, InterviewReportResult):
        raise ValueError(f"LLM报告结果类型异常: {type(result)}")
    logger.info("面试报告生成完成: total_score=%s", result.total_score)
    return result


def generate_report(resume_context: dict, records: list[dict]) -> InterviewReportResult:
    """执行报告生成工作流（§13 Summary Agent，兼容旧调用方）。

    Args:
        resume_context: 简历结构化上下文。
        records: 整场面试记录列表（题目/回答/评分/评价）。

    Returns:
        InterviewReportResult 最终报告结构。

    Raises:
        Exception: LLM 调用失败（由上层按 §21 重试/手动 regenerate）。
    """
    return _generate_report_impl(resume_context, records)