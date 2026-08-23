"""LLM 输出 Schema 包，统一导出各业务结构化输出模型。"""

from app.llm.schemas.interview import (
    AnswerAnalysisResult,
    FastDecisionResult,
    InterviewReportResult,
    QuestionGenerationResult,
    SpeechCorrectionResult,
)

__all__ = [
    "AnswerAnalysisResult",
    "FastDecisionResult",
    "InterviewReportResult",
    "QuestionGenerationResult",
    "SpeechCorrectionResult",
]
