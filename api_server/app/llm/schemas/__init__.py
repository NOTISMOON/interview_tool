"""LLM 输出 Schema 包，统一导出面试业务结构化输出模型（简历解析模型见 schemas/resume.py）。"""

from app.llm.schemas.interview import (
    AnswerAnalysisResult,
    FastDecisionResult,
    InterviewReportResult,
    QuestionGenerationResult,
)

__all__ = [
    "AnswerAnalysisResult",
    "FastDecisionResult",
    "InterviewReportResult",
    "QuestionGenerationResult",
]
