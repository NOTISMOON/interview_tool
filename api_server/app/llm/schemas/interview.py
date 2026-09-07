"""面试模块 LLM 输出模型（LangGraph 结构化提取结果）。

主要结构化输出（对应文档 §7/§9/§13）：
    - QuestionGenerationResult: 创建面试时批量预生成基础题
    - AnswerAnalysisResult:     4路并行分支（内容/技术深度/完整逻辑/综合评分）聚合后的
                                分析+评分结果（不含追问，追问由判题链流式生成）
    - InterviewReportResult:    Summary Agent 最终报告
其余为并行分支与判题链的辅助输出模型（FastDecisionResult/SpeechCorrectionResult 等）。

字段全部带默认值：DeepSeek json_mode 输出不稳定，缺失/显式 null 均可能
出现（同 resume.py WorkItem 经验），强制非空会导致偶发整体解析失败。
"""

from pydantic import BaseModel, Field


class GeneratedQuestion(BaseModel):
    """预生成的单道基础题。"""

    question_text: str = Field(default="", description="题目内容")
    question_type: int = Field(default=1, description="题型 1-技术题 2-项目题 3-行为题")
    category: int = Field(default=1, description="维度 1-技术基础 2-项目经验 3-综合素质 4-架构设计")


class QuestionGenerationResult(BaseModel):
    """基础题批量生成结果（创建面试时一次性预生成，§7.2）。"""

    questions: list[GeneratedQuestion] = Field(default_factory=list, description="基础题列表")


class AnswerAnalysisResult(BaseModel):
    """回答分析合并结果（并行分析图聚合，§9.2）。

    score 落库 ai_score，comment 落库 ai_comment；corrected_answer 为模型顺带
    纠错后的回答（语音/输入识别错误已修正，口语词保留），落库 user_answer 用
    （P2：纠错并入分析/追问提示词，不再单独起一次 LLM）。
    追问生成由判题链流式生成（generate_follow_up_stream）负责，分析图不产出 follow_up_question。
    """

    correctness: str = Field(default="", description="是否切题、回答正确性简述")
    technical_depth: int = Field(default=1, description="技术深度 1-5")
    completeness: int = Field(default=1, description="完整性 1-5")
    logic: int = Field(default=1, description="逻辑性 1-5")
    key_points: list[str] = Field(default_factory=list, description="回答要点")
    weaknesses: list[str] = Field(default_factory=list, description="薄弱点/缺失")
    score: int = Field(default=1, description="综合评分 1-5（落库 ai_score）")
    comment: str = Field(default="", description="综合评价（落库 ai_comment）")
    # 必填：json_mode 下模型表缺失省字段（有默认值时常被省略）→ 空串导致 service
    # 回退原文、纠正失效。强制 min_length>=1 堵死空回退，无错误时也须逐字原样返回。
    corrected_answer: str = Field(..., min_length=1, description="顺带纠错后的回答全文（无改动时等于原文）")


class ContentAnalysisResult(BaseModel):
    """并行分支·内容分析（切题性 + 要点 + 薄弱点）。"""

    correctness: str = Field(default="", description="是否切题、内容是否正确（简述，一两句话）")
    key_points: list[str] = Field(default_factory=list, description="回答覆盖到的要点列表")
    weaknesses: list[str] = Field(default_factory=list, description="薄弱点或缺失列表（没有则空列表）")


class TechnicalDepthResult(BaseModel):
    """并行分支·技术深度评分。"""

    technical_depth: int = Field(default=1, description="技术深度 1-5")


class CompletenessLogicResult(BaseModel):
    """并行分支·完整性与逻辑性评分。"""

    completeness: int = Field(default=1, description="完整性 1-5")
    logic: int = Field(default=1, description="逻辑性 1-5")


class ScoringResult(BaseModel):
    """并行分支·综合评分与评价（v3·顺带产出纠错后回答）。

    corrected_answer 由评分分支顺带纠错生成（P2 起不再单独调语音纠错 LLM）：
    仅修正确认的识别错误，无错误时等于原文；聚合进 AnswerAnalysisResult 落库 user_answer。
    """

    score: int = Field(default=1, description="综合评分 1-5 分整数，综合各维度给出")
    comment: str = Field(default="", description="面试官视角的综合评价（两三句话，可直接展示给候选人）")
    # 必填：堵死 json_mode 省略有默认值字段导致 corrected 为空、落库回退原文的问题
    corrected_answer: str = Field(..., min_length=1, description="顺带纠错后的回答全文（无改动时等于原文）")


class FastDecisionResult(BaseModel):
    """Fast Decision 轻量 LLM 输出（v2·即时判定追问，§四决策1=B）。

    next_action 取值：
        - "follow_up"  需要追问，follow_up_question 为判定的追问文本
        - "next_base"  直接进入下一道基础题
        - "end"        面试结束（全部题目答完）

    判定基于当前题目 + 回答 + 简历上下文，SYNC 亚秒级完成（低 temp 短 prompt），
    即使用户选 B（fast LLM）也能保证回答后立即给下一题。
    """

    next_action: str = Field(default="next_base", description="追问/下一基础题/结束")
    follow_up_question: str | None = Field(
        None, description="判定的追问（next_action=follow_up 时必填）"
    )
    technical_depth_hint: int = Field(
        default=3, description="回答深度轻度预判 1-5（1-2 倾向追问，供规则叠加判定）"
    )


class InterviewReportResult(BaseModel):
    """最终面试报告结构（Summary Agent，§13；维度大众化）。"""

    total_score: float = Field(default=0.0, description="总体评分（百分制）")
    dimension_scores: dict[str, float] = Field(
        default_factory=dict, description="各维度得分（专业能力/项目实践/问题解决/沟通表达/综合素质/岗位匹配）"
    )
    strengths: list[str] = Field(default_factory=list, description="回答优点")
    weaknesses: list[str] = Field(default_factory=list, description="知识薄弱点")
    capability_profile: dict[str, str] = Field(default_factory=dict, description="能力画像（等级/评价）")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")
    summary: str = Field(default="", description="总评")
