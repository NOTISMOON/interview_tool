"""LLM 模型工厂：基于 LangChain 初始化聊天模型，供应商/模型/超时均可配置化切换。

对应简历上传分析蓝图 §5.11：LLM 抽象层经 LangChain 统一封装，
Worker 内不直接绑定单一供应商，供应商差异不影响下游数据契约。
"""

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings


def _init_model(model: str, temperature: float) -> BaseChatModel:
    """按配置创建聊天模型实例。

    Args:
        model: 模型名称（如 qwen3.5:4b / qwen2.5vl:3b）。
        temperature: 采样温度，越低输出越稳定。

    Returns:
        配置化后的 BaseChatModel 实例。

    Raises:
        ImportError: 缺少对应供应商的集成包时抛出（如 langchain-ollama）。
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "timeout": settings.LLM_TIMEOUT,
    }
    if settings.LLM_PROVIDER == "ollama":
        # Ollama 特有参数：base_url 指定本地服务地址，num_ctx 控制上下文窗口，
        # num_predict 控制单次输出 Token 上限（对应通用 max_tokens 概念）。
        kwargs.update(
            {
                "base_url": settings.LLM_BASE_URL,
                "num_ctx": settings.LLM_NUM_CTX,
                "num_predict": settings.LLM_MAX_TOKENS,
            }
        )
    return init_chat_model(model_provider=settings.LLM_PROVIDER, **kwargs)


def _build_interview_model() -> BaseChatModel:
    """构建面试/简历解析基座模型。

    优先使用 DeepSeek 线上模型（OpenAI 兼容），未配置 API Key 时回退本地 Ollama。
    返回的深层模型支持 with_structured_output 做 Pydantic 结构化提取。
    """
    if settings.DEEPSEEK_API_KEY:
        return init_chat_model(
            model_provider="openai",
            model=settings.DEEPSEEK_MODEL,
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            temperature=settings.LLM_TEMPERATURE_INTERVIEW,
            timeout=settings.LLM_TIMEOUT,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
    # 本地回退：Ollama
    return _init_model(settings.LLM_MODEL_INTERVIEW, settings.LLM_TEMPERATURE_INTERVIEW)


# 面试/简历解析基座模型（DeepSeek 线上优先，LOWER温度保证解析稳定）
interview_model = _build_interview_model()
