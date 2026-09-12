"""面试模块 LangGraph 工作流（v4·真实循环图 + interrupt 挂起/恢复）。

对齐《面试模块单LangGraph架构方案.md》v3 迭代：
    - interview_graph 为【真实循环图】：init → ask（interrupt 出题挂起）→
      fast_decision →（follow_up 时）follow_up_stream → route →（end 时 END，
      否则回边 ask）。整场面试 = 一次连续图执行（thread_id = interview_id），
      RedisSaver checkpointer 跨 interrupt 持久化全局状态（基础题快照、当前题
      指针等），每轮提交回答以 Command(resume={answer, ...}) 从挂起点恢复，
      不再每轮把整份全局状态合并进图。
    - 创建面试【不进入图】：基础题仍由 service 直接调 generate_questions() 批量
      预生成落库（runtime 图只做问答推进，不做出题）。
    - 图只做「给定当前题回答，判定下一动作并产出追问/下一题」的单步推进：
      不写库、不碰锁/epoch；题目与回答的落库、幂等、三层并发控制仍由
      interview_service 编排（落库失败时 service 重建图线程回退，图状态可从
      MySQL 业务数据重建）。
    - 追问【不入问题队列】：fast_decision 判 follow_up 后，追问文本写入全局
      状态 pending_follow_up，经 SSE 直推前端；用户回答追问后才在落库阶段建
      DB 行。Redis 问题队列镜像（T3.8/T3.9）已整体删除，基础题按 question_no
      顺序推进。
    - 语音纠错不再单独成节点/调用：纠错指令融入分析/追问提示词，以纠错后回答更新
      user_answer（P2）。
    - answer_analysis（内容/技术深度/完整逻辑/综合评分 4 路并行聚合）仍由
      AnswerAnalysisGraph 承担，转入主链判题后同步执行（由 service 调 analyze_answer_parallel）。

LLM 失败防御（节点内兜底，图自治不中断）：
    - fast_decision / follow_up_stream 抛错 → 节点内回退 next_base（§21 语义
      简化为单次兜底，service 不再统计 analysis_fail_count 重试）。

同步路径 LLM 调用：
    1. question_generation（创建时一次，service 直接调用，不进图）
    2. fast_decision（每次回答后，LLM 判定下一动作：follow_up/next_base/end）
    3. follow_up_stream（fast_decision 判 follow_up 后，LLM 流式产出追问文本，
       边生成边经 SSE judge_stream 累积快照推前端，收集全文判 NONE）
异步路径另用 AnswerAnalysisGraph（service 判题后调用，4 路并行分析后聚合落库）。
"""

import asyncio
import json
import logging
from typing import Iterator, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.redis import RedisSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.config import settings
from app.llm.models import interview_model, judge_fast_model
from app.llm.prompt import (
    COMPLETENESS_LOGIC_PROMPT,
    CONTENT_ANALYSIS_PROMPT,
    FAST_DECISION_PROMPT,
    FOLLOW_UP_STREAM_PROMPT,
    QUESTION_GENERATION_PROMPT,
    REPORT_SUMMARY_PROMPT,
    SCORING_PROMPT,
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
    TechnicalDepthResult,
)
from app.redis.sync_client import SyncRedisClient

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
# 图状态（单状态：checkpointer 持久化全局，interrupt 跨轮保留）
# --------------------------------------------------------------------------

class InterviewState(TypedDict, total=False):
    """面试图全局状态（RedisSaver checkpointer 持久化，thread_id=interview_id）。

    全局状态是节奏事实源，跨 interrupt 自动保留，恢复时【只传增量】（answer 与
    每轮动态规则入参），不再每轮整份合并：
        - 持久字段：base_questions/base_count/resume_context/当前题指针/当前题文本，
          首启（或 service 落库失败重建）时由 service 从 DB 装载种入。
        - 每轮动态字段：answer/elapsed_over/interrupted/follow_up_total/
          per_base_follow_up_count，随 Command(resume=...) 由 service 从 DB/租约计算传入。
        - 本轮节点瞬时字段：next_action/pending_follow_up/next_base_text。
    注意：interrupt 挂起发生在 ask 节点，未落库的追问文本（pending_follow_up）
    与下一题文本（next_base_text）在挂起状态中保留，供 service 落库编排。
    """

    # —— 持久（首启种入，checkpointer 跨 interrupt 保留）——
    user_id: int  # SSE 发布目标用户
    interview_id: int  # thread_id（== interview 主键）
    resume_context: dict  # 简历结构化上下文
    base_questions: list[dict]  # [{question_no, question_id, question_type, category, question_text}]
    base_count: int  # 基础题总数
    # 当前题（route 推进，ask 读取）
    current_question_id: int | None  # 基础题ID；追问未落库时为 None（service 落库后回填）
    question_no: int  # 当前基础题号（追问与父题同号）
    question_text: str  # 当前题目文本（追问时为追问文本，答基础题为基础题文本）

    # —— 每轮动态（随 resume 由 service 传入，单一数据源=DB）——
    answer: str  # 用户回答文本
    elapsed_over: bool  # 是否超过最长面试时长（90分钟）
    interrupted: bool  # Redis 中断标记（主动放弃/无活动超时）
    follow_up_total: int  # 全场当前追问总数（用于追问上限防御）
    per_base_follow_up_count: int  # 当前基础题已追问次数（每题最多1次）

    # —— 本轮节点瞬时 ——
    next_action: str  # follow_up / next_base / end
    pending_follow_up: str | None  # 未落库追问文本（follow_up_stream 写入）
    next_base_text: str | None  # 下一基础题文本（next_base 时由 route 写入）


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

def _first_base(base_questions: list[dict]) -> dict | None:
    """取第一道基础题（按 question_no 升序第一）。

    Args:
        base_questions: 基础题快照列表。

    Returns:
        第一道基础题字典；无则 None。
    """
    if not base_questions:
        return None
    return min(base_questions, key=lambda x: int(x.get("question_no", 0)))


def _base_id_by_no(base_questions: list[dict], q_no: int) -> int | None:
    """按基础题号取基础题ID。

    Args:
        base_questions: 基础题快照列表。
        q_no: 基础题号。

    Returns:
        对应基础题ID；未找到返回 None。
    """
    for q in base_questions:
        if int(q.get("question_no", 0)) == q_no:
            return int(q["question_id"])
    return None


def _next_base_obj(state: InterviewState) -> dict | None:
    """取当前基础题之后的第一道基础题（question_no 大于当前题号）。

    Args:
        state: 全局状态（含 base_questions 快照与当前 question_no）。

    Returns:
        下一基础题字典；无则 None。
    """
    base = state.get("base_questions") or []
    q_no = int(state.get("question_no", 0))
    for q in sorted(base, key=lambda x: int(x.get("question_no", 0))):
        if int(q.get("question_no", 0)) > q_no:
            return q
    return None


def _init(state: InterviewState) -> InterviewState:
    """节点 init：装载基础题快照并定位当前题（仅首启/重建执行一次）。

    后续轮次由 checkpointer 保留全局状态，不经过本节点。若调用方已指定当前题
    （question_no/question_text，供 service 落库失败重建线程）直接采用；否则定位
    第一道基础题作为首题。

    Returns:
        初始化后的全局状态。
    """
    base = state.get("base_questions") or []
    q_no = int(state.get("question_no") or 0)
    q_text = str(state.get("question_text") or "")
    if q_no <= 0 or not q_text:
        first = _first_base(base)
        if first is not None:
            q_no = int(first["question_no"])
            q_text = str(first["question_text"])
    return {
        "base_questions": base,
        "base_count": len(base),
        "current_question_id": state.get("current_question_id")
        or _base_id_by_no(base, q_no),
        "question_no": q_no,
        "question_text": q_text,
        "next_action": ACTION_NEXT_BASE,
        "pending_follow_up": None,
        "next_base_text": None,
        "answer": "",
        "elapsed_over": bool(state.get("elapsed_over", False)),
        "interrupted": bool(state.get("interrupted", False)),
        "follow_up_total": int(state.get("follow_up_total", 0)),
        "per_base_follow_up_count": int(state.get("per_base_follow_up_count", 0)),
    }


def _ask(state: InterviewState) -> InterviewState:
    """节点 ask：interrupt 出题挂起（human-in-the-loop），恢复时写入答案。

    首次进入（首启/重建）以当前题 interrupt 返回给调用方并挂起；用户提交回答后
    以 Command(resume={answer, ...}) 恢复，此处把答案与每轮动态规则入参写入状态，
    随后经回边进入 fast_decision 判题。挂起即等待用户回答，图不消耗任何资源。

    Returns:
        写入 answer 与每轮动态入参的状态。
    """
    payload = {
        "kind": "interview:ask",
        "session_id": state.get("interview_id"),
        "question_no": state.get("question_no"),
        "question_id": state.get("current_question_id"),
        "question_text": state.get("question_text"),
        "is_follow_up": state.get("next_action") == ACTION_FOLLOW_UP,
    }
    resumed = interrupt(payload)
    if not isinstance(resumed, dict):
        return {"answer": str(resumed or "")}
    return {
        "answer": str(resumed.get("answer") or ""),
        # 每轮动态规则入参（由 service 从 DB/租约计算后随 resume 传入，单一数据源=DB）
        "elapsed_over": bool(resumed.get("elapsed_over", state.get("elapsed_over", False))),
        "interrupted": bool(resumed.get("interrupted", state.get("interrupted", False))),
        "follow_up_total": int(resumed.get("follow_up_total", state.get("follow_up_total", 0))),
        "per_base_follow_up_count": int(
            resumed.get("per_base_follow_up_count", state.get("per_base_follow_up_count", 0))
        ),
    }


def _fast_decision(state: InterviewState) -> InterviewState:
    """节点 fast_decision：LLM 即时判定下一动作（追问/下一基础/结束）。

    保留 LLM 意图判定（LLM 判定全部动作）：以 judge_fast_model（关闭思考模式，
    低延迟短 prompt）输出 next_action ∈ {follow_up, next_base, end}；仅判动作，
    追问文本生成由 follow_up_stream 节点流式完成。非法动作回退 next_base。

    LLM 调用失败在【节点内】兜底回退 next_base（图自治不中断，§21 语义简化）。

    Returns:
        写入 next_action 的 state。
    """
    try:
        model: BaseChatModel = judge_fast_model
        prompt = FAST_DECISION_PROMPT.format(
            question=state.get("question_text", ""),
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
        logger.info(
            "Fast Decision: interview_id=%s question_no=%s action=%s depth_hint=%s",
            state.get("interview_id"), state.get("question_no"), action, result.technical_depth_hint,
        )
        return {"next_action": action, "pending_follow_up": None}
    except Exception:
        logger.exception(
            "Fast Decision LLM 失败，节点内回退 next_base: interview_id=%s",
            state.get("interview_id"),
        )
        return {"next_action": ACTION_NEXT_BASE, "pending_follow_up": None}


def _follow_up_stream(state: InterviewState) -> InterviewState:
    """节点 follow_up_stream：流式生成追问并直推前端（仅 fast_decision 判 follow_up 后）。

    以 judge_fast_model 流式产出追问文本，边生成边经 SSE judge_stream 累积
    快照推前端打字机（追问【不入问题队列】，生成即输出）；收集全文后
    is_follow_up_none 判定：NONE（回答已到位无需追问）回落 next_base，否则追问
    文本写入全局状态 pending_follow_up 供 service 记录为当前题（用户回答后才落库）。

    LLM 调用失败在【节点内】兜底回退 next_base（图自治不中断）。

    Returns:
        next_action（follow_up / next_base）+ pending_follow_up。
    """
    try:
        user_id = int(state.get("user_id") or 0)
        question = state.get("question_text", "")
        answer = state.get("answer") or ""
        resume_context = state.get("resume_context") or {}

        def _publish(snapshot: str, done: bool = False, is_none: bool = False, final_text: str | None = None) -> None:
            """发布一条 judge_stream 事件（正文累积快照或 done 终帧）。

            采用"累积快照"而非增量 delta：每帧携带当前已生成的全部文本，前端整段
            替换而非追加拼接，即使中途丢帧也能在下帧自愈为一致文本（无缺字缺口）。
            """
            _publish_sse_event(
                user_id,
                {
                    "kind": "interview:judge_stream",
                    "session_id": state.get("interview_id"),
                    "question_index": state.get("question_no"),
                    "text": snapshot,
                    "done": done,
                    "is_none": is_none,
                    "final_text": final_text,
                },
            )

        buf: list[str] = []
        for chunk in generate_follow_up_stream(question, answer, resume_context):
            if not chunk:
                continue
            buf.append(chunk)
            if chunk.strip():
                # 累积快照：逐 chunk 累积后，每帧推送当前已生成全文（langchain stream
                # 本身只产增量 token，没有"带全文"的内置模式，全文需在此手动累积）
                _publish("".join(buf))
        text = "".join(buf).strip()
        if is_follow_up_none(text):
            # LLM 判定无需追问 → 告诉前端清空回退，由 route 分派下一基础题
            _publish("", done=True, is_none=True)
            return {"next_action": ACTION_NEXT_BASE, "pending_follow_up": None}
        _publish("", done=True, final_text=text[:300])
        logger.info(
            "追问流式生成完成: interview_id=%s question_no=%s len=%s",
            state.get("interview_id"), state.get("question_no"), len(text),
        )
        return {"next_action": ACTION_FOLLOW_UP, "pending_follow_up": text[:300]}
    except Exception:
        logger.exception(
            "追问流式生成失败，节点内回退 next_base: interview_id=%s",
            state.get("interview_id"),
        )
        return {"next_action": ACTION_NEXT_BASE, "pending_follow_up": None}


def _route(state: InterviewState) -> InterviewState:
    """节点 route：动作标准化 + 推进当前题 + 防御（end→END，否则回边 ask 再出题）。

    防御（LLM 意图判定之后的兜底）：
        - Redis 中断标记（主动放弃/无活动超时）→ 强制 end；
        - follow_up 触发条件不满足（超时/追问达上限/本基础题已追问/回答空）→ 回退 next_base。
    推进当前题：follow_up 时当前题=追问文本；next_base 时当前题=下一基础题（按
    question_no 顺序推进，不依赖 Redis 问题队列镜像）。end 时不推进（由业务状态收敛）。

    Returns:
        标准化后的 next_action（+ 推进后的当前题字段与 next_base_text）。
    """
    action = state.get("next_action", ACTION_NEXT_BASE)
    if state.get("interrupted"):
        # Redis 中断/超时：无论 LLM 判定如何均结束（结束由业务状态收敛，不重复发题）
        action = ACTION_END
    elif action == ACTION_FOLLOW_UP and (
        state.get("elapsed_over")
        or int(state.get("follow_up_total", 0)) >= int(state.get("base_count", 0))
        or int(state.get("per_base_follow_up_count", 0)) >= 1
        or not str(state.get("answer", "")).strip()
    ):
        # 追问触发条件不满足 → 回退下一基础题
        action = ACTION_NEXT_BASE

    out: dict = {"next_action": action}
    if action == ACTION_FOLLOW_UP:
        text = str(state.get("pending_follow_up") or "")
        if text:
            # 推进当前题为追问（不入问题队列；追问行由 service 落库后回填真实ID）
            out["question_text"] = text
            out["current_question_id"] = None
            return out
        # 追问文本为空（异常兜底）→ 回退下一基础题
        action = ACTION_NEXT_BASE
        out["next_action"] = ACTION_NEXT_BASE

    # next_base / end：取下一道未答基础题文本（基础题按 question_no 顺序）
    out["pending_follow_up"] = None
    if action == ACTION_NEXT_BASE:
        nxt = _next_base_obj(state)
        if nxt is not None:
            out["next_base_text"] = str(nxt.get("question_text", ""))
            out["question_no"] = int(nxt["question_no"])
            out["question_text"] = str(nxt["question_text"])
            out["current_question_id"] = int(nxt["question_id"])
            return out
        # 基础题已问尽 → 结束
        out["next_action"] = ACTION_END
    return out


# --------------------------------------------------------------------------
# SSE 直推（图节点内发布，供追问流式推送；与 service._publish_sse 同一通道）
# --------------------------------------------------------------------------

def _publish_sse_event(user_id: int, event: dict) -> None:
    """经用户频道推送 SSE 事件（同步 Redis，失败不阻断判题）。

    Args:
        user_id: 目标用户ID。
        event: 事件数据（含 kind 等字段）。
    """
    try:
        SyncRedisClient.get_client().publish(
            f"{settings.NOTIFY_PUSH_CHANNEL_PREFIX}:{user_id}",
            json.dumps(event, ensure_ascii=False, default=str),
        )
    except Exception:
        logger.exception("面试图SSE推送失败: user_id=%s kind=%s", user_id, event.get("kind"))


def build_interview_graph():
    """构建并编译面试节奏控制图（真实循环图，绑定 Redis checkpointer）。

    节点链与循环边：init → ask（interrupt 出题挂起）→ fast_decision
    →（follow_up 时）follow_up_stream → route →（end 时 END，否则【回边】ask）。
    整场面试 = 一次连续图执行（thread_id=interview_id），中间多次 interrupt 挂起/
    Command(resume=answer) 恢复；全局状态由 checkpointer 跨 interrupt 保留，
    每轮恢复只传增量（answer + 动态规则入参），不再整份合并。
    创建面试不经本图。

    Returns:
        编译后的 StateGraph（绑定 checkpointer）。
    """
    builder = StateGraph(InterviewState)
    builder.add_node("init", _init)
    builder.add_node("ask", _ask)
    builder.add_node("fast_decision", _fast_decision)
    builder.add_node("follow_up_stream", _follow_up_stream)
    builder.add_node("route", _route)
    builder.add_edge(START, "init")
    builder.add_edge("init", "ask")
    # 循环核心回边：ask 恢复写入答案后 → fast_decision 判下一动作
    builder.add_edge("ask", "fast_decision")
    # fast_decision 判 follow_up → 流式生成追问；其余动作直接进 route
    builder.add_conditional_edges(
        "fast_decision",
        lambda s: "follow_up_stream" if s.get("next_action") == ACTION_FOLLOW_UP else "route",
        {"follow_up_stream": "follow_up_stream", "route": "route"},
    )
    builder.add_edge("follow_up_stream", "route")
    # route 判 end → END（整场结束）；否则回边 ask 出下一题并挂起
    builder.add_conditional_edges(
        "route",
        lambda s: END if s.get("next_action") == ACTION_END else "ask",
        {"ask": "ask", END: END},
    )
    graph = builder.compile(checkpointer=interview_graph_checkpointer)
    logger.info(
        "面试节奏控制图已编译（循环图+interrupt） checkpointer=%s",
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


def _read_turn_result(result: dict) -> dict:
    """从图 invoke 返回值提取本轮结果（判题动作/追问/下一基础题/是否出题挂起）。

    Args:
        result: 图 invoke 返回的状态字典（含 __interrupt__ 键表示 ask 挂起）。

    Returns:
        本轮结果字典：next_action/pending_follow_up/next_base_text/interrupted
        （True=已出题挂起，等待用户回答；False=整场结束 END）。
    """
    return {
        "interrupted": "__interrupt__" in result,
        "next_action": result.get("next_action"),
        "pending_follow_up": result.get("pending_follow_up"),
        "next_base_text": result.get("next_base_text"),
        "question_no": result.get("question_no"),
        "question_text": result.get("question_text"),
    }


def start_interview_graph(
    interview_id: int,
    user_id: int,
    resume_context: dict,
    base_questions: list[dict],
    question_no: int = 0,
    question_text: str = "",
    current_question_id: int | None = None,
    follow_up_total: int = 0,
    per_base_follow_up_count: int = 0,
) -> dict:
    """启动/重建面试图：init → ask(interrupt 首题/当前题)，图挂起等首次回答。

    整场面试一次连续执行（thread_id=interview_id），此后每轮以
    resume_interview_graph 恢复。图状态（基础题快照/简历上下文/当前题指针）由
    checkpointer 跨 interrupt 持久化；本函数仅在首启或重建线程时调用。

    重建场景（service 落库失败回退 / Redis checkpointer 丢失）：以业务
    checkpoint 的当前题（question_no/question_text/current_question_id）重建，
    保证恢复点与前端展示题一致。

    Args:
        interview_id: 面试会话ID（thread_id）。
        user_id: 目标用户ID（追问流式 SSE 发布用）。
        resume_context: 简历结构化上下文。
        base_questions: 基础题列表（question_no/question_id/question_type/category/question_text）。
        question_no: 当前题基础题号（0 则取第一道基础题）。
        question_text: 当前题文本（空则取第一道基础题文本）。
        current_question_id: 当前基础题ID（未知时按 question_no 回填）。
        follow_up_total: 当前追问总数（重建场景从 DB 装载，用于追问上限防御）。
        per_base_follow_up_count: 当前基础题已追问次数（重建场景从 DB 装载）。

    Returns:
        本轮结果（interrupted=True，出题挂起）。
    """
    input_state: InterviewState = {
        "user_id": user_id,
        "interview_id": interview_id,
        "resume_context": resume_context or {},
        "base_questions": base_questions,
        "base_count": len(base_questions),
        "question_no": question_no,
        "question_text": question_text,
        "current_question_id": current_question_id,
        "follow_up_total": follow_up_total,
        "per_base_follow_up_count": per_base_follow_up_count,
        "elapsed_over": False,
        "interrupted": False,
        "answer": "",
        "next_action": ACTION_NEXT_BASE,
        "pending_follow_up": None,
        "next_base_text": None,
    }
    result = interview_graph.invoke(input_state, config=_thread_config(interview_id))
    return _read_turn_result(result)


def resume_interview_graph(interview_id: int, resume_value: dict) -> dict:
    """恢复面试图（提交回答）：从挂起 ask 恢复，判题/出题后再次 interrupt 或 END。

    Args:
        interview_id: 面试会话ID（thread_id）。
        resume_value: 恢复载荷 {"answer", "elapsed_over", "interrupted",
                       "follow_up_total", "per_base_follow_up_count"}。

    Returns:
        本轮结果（next_action/pending_follow_up/next_base_text/interrupted=
        True=已出题挂起等待下一答；False=整场结束）。
    """
    result = interview_graph.invoke(
        Command(resume=resume_value), config=_thread_config(interview_id)
    )
    return _read_turn_result(result)


def get_graph_current_question(interview_id: int) -> str | None:
    """读取图当前挂起问题的文本（用于与业务 checkpoint 对齐校验）。

    图线程不存在或读取失败返回 None，调用方据此重建线程。

    Args:
        interview_id: 面试会话ID（thread_id）。

    Returns:
        图当前题文本；无则 None。
    """
    try:
        snapshot = interview_graph.get_state(_thread_config(interview_id))
        values = snapshot.values if snapshot is not None else {}
        text = values.get("question_text")
        return str(text) if text else None
    except Exception:
        logger.warning("读取面试图当前题失败: interview_id=%s", interview_id, exc_info=True)
        return None


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
# 流式追问生成（v2·判题链，经 SSE judge_stream 累积快照直推前端）
# --------------------------------------------------------------------------

# 追问 NONE 判定标记（模型回答到位时的输出）
FOLLOW_UP_NONE_MARKERS = {"NONE", "none", "None", "无", "无需", "无需追问", "不需要追问"}


def resume_follow_up_subset(resume_context: dict) -> dict:
    """裁剪简历上下文为追问用子集（P0：减少 prompt 输入 token）。

    只保留追问判题实际需要的部分：技能列表（前 12）、项目经历（前 3，
    description 截断 120 字）、工作经历（前 2）——丢弃 education 等无关大字段。

    Args:
        resume_context: 简历结构化上下文字典。

    Returns:
        精简后的上下文字典。
    """
    projects = []
    for p in (resume_context.get("projects") or [])[:3]:
        item = dict(p or {})
        desc = str(item.get("description") or "")
        if len(desc) > 120:
            item["description"] = f"{desc[:120]}…"
        projects.append(item)
    return {
        "skills": (resume_context.get("skills") or [])[:12],
        "projects": projects,
        "work_experience": (resume_context.get("work_experience") or [])[:2],
    }


def generate_follow_up_stream(
    question: str,
    answer: str,
    resume_context: dict,
) -> Iterator[str]:
    """流式生成追问文本（单次 LLM，输出为纯文本追问问题或 NONE）。

    由 service 在判题阶段逐 token 收集，同时经 SSE（judge_stream 增量
    事件）推给前端打字机展示；收集完成后由服务层判定 NONE/追问。抛 LLM 异常时
    由服务层按 analysis_fail_count 兜底。

    Args:
        question: 当前题目文本。
        answer: 用户回答（纠错后或原文）。
        resume_context: 简历结构化上下文（内部裁剪为追问子集）。

    Yields:
        LLM 输出的文本增量（逐 chunk）。
    """
    subset = resume_follow_up_subset(resume_context)
    prompt = FOLLOW_UP_STREAM_PROMPT.format(
        question=question,
        answer=answer[:2000],  # 防超长回答撑爆上下文
        resume_context=json.dumps(subset, ensure_ascii=False, default=str),
    )
    # 判题专用快速模型（judge_fast_model）：关闭思考模式，简单任务免思维链开销
    for chunk in judge_fast_model.stream(prompt):
        content = getattr(chunk, "content", None)
        if content:
            yield content


def is_follow_up_none(text: str) -> bool:
    """判断流式收集结果是否表示"无需追问"（NONE）。

    Args:
        text: 流式收集的完整输出（已 strip）。

    Returns:
        True=无需追问，应走下一基础题。
    """
    if not text:
        return True
    return text.upper() in FOLLOW_UP_NONE_MARKERS or text.upper().startswith("NONE")


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
    """分析图节点·汇聚节点（等所有分支完成后执行），合并为 AnswerAnalysisResult。

    corrected_answer 取评分分支顺带纠错的结果（无改动时为空串由调用方回退原文），
    供 service 落库时以纠错后回答更新 user_answer（P2）。

    Returns:
        合并后的 result 字段。
    """
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
        corrected_answer=scoring.corrected_answer,
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