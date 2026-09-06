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


def _build_judge_model() -> BaseChatModel:
    """构建判题快速模型（语音纠错 + 追问生成专用）。

    判题链路对"快而短"的任务（改错别字 / 生成一句追问）仍需全局 interview_model
    默认开启的思考模式（thinking=high）时，简单任务也会先产出长思维链，实测单次
    纠错全量调用可达 40s+。此处显式关闭思考模式（{"thinking": {"type": "disabled"}}），
    将判题两段调用与"质量优先"的 4 路分析 / 报告生成（保留 interview_model）解耦。

    注意：Ollama 回退分支不传 thinking 参数（其 API 不识别该字段）；DeepSeek 走
    OpenAI 兼容接口，规范要求将思考开关放在 extra_body（LangChain 的 ChatOpenAI
    支持显式传入）注入请求体。

    Returns:
        关闭思考模式的聊天模型实例。
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
            # DeepSeek 思考开关是 OpenAI 兼容的非标准字段：经 extra_body 注入请求体
            # （直接放顶层会被 LangChain 拼进 create() 参数导致 SDK TypeError）
            extra_body={"thinking": {"type": "disabled"}},
        )
    # 本地回退：Ollama（无 thinking 开关，照常使用基座模型）
    return _init_model(settings.LLM_MODEL_INTERVIEW, settings.LLM_TEMPERATURE_INTERVIEW)


# 判题快速模型（语音纠错 + 追问生成，关闭思考模式）
judge_fast_model = _build_judge_model()
