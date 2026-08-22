"""简历解析 LangGraph 工作流。

两节点线性图（蓝图§3.4）：
    1. load_document: 按文件扩展名选择 LangChain 文档加载器，直接解析线上文件链接
       （不手写下载与解析逻辑）。
    2. extract: 面试基座模型 with_structured_output 做 LLM 结构化提取，
       Pydantic schema 约束输出（蓝图§5.5），失败向上抛由消费者置 status=2。

加载策略（数据源统一为公开 file_url，需 COS 桶对 resumes/* 开通公有读）：
    - .pdf:  PyPDFLoader(file_url).load()，加载器支持 URL 直连，免下载。
    - .docx: Docx2txtLoader 不支持 URL（0.4.2 把URL当本地路径报PermissionError），
             故从 file_url 拉取字节写入临时文件后再本地解析。
    预签名URL带 "?q-signature=..." 会触发加载器文件名 bug，一律用干净的公开 file_url。
    旧版 .doc 不再支持，仅允许 .pdf/.docx 两种（见上传扩展名白名单）。

状态流转: RawFile(cos_key + file_url) → text → ResumeExtraction。
"""

import logging
import os
import tempfile
from typing import TypedDict

import requests
from langchain_community.document_loaders import Docx2txtLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.llm.models import interview_model
from app.llm.prompt import RESUME_PARSE_PROMPT
from app.llm.schemas.resume import ResumeExtraction

logger = logging.getLogger(__name__)

# 提取文本截断长度（与 num_ctx 配套，防止超长简历撑爆上下文）
MAX_TEXT_LENGTH = 12000


class ResumeParseState(TypedDict, total=False):
    """简历解析工作流状态。"""

    cos_key: str  # COS对象Key（用于扩展名判断与日志）
    file_url: str  # 公开访问线上链接（须可匿名GET，.pdf/.docx 均直连解析）
    text: str  # 提取出的纯文本
    extraction: ResumeExtraction  # LLM结构化提取结果


def load_document(state: ResumeParseState) -> ResumeParseState:
    """节点1：文件加载与文本提取（.pdf/.docx 均直连线上链接）。

    Args:
        state: 工作流状态（含 cos_key / file_url）。

    Returns:
        更新后的状态（补充 text）。

    Raises:
        ValueError: 缺少线上链接、文件类型不支持或文本提取为空。
    """
    file_url = state.get("file_url")
    if not file_url:
        raise ValueError("简历缺少线上链接 file_url")
    ext = os.path.splitext(state["cos_key"])[1].lower()
    if ext == ".pdf":
        docs = PyPDFLoader(file_url).load()
    elif ext == ".docx":
        # Docx2txtLoader 不支持 URL 直连（0.4.2 报 PermissionError），从 file_url 拉取后临时文件解析。
        resp = requests.get(file_url, timeout=60)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name
        try:
            docs = Docx2txtLoader(tmp_path).load()
        finally:
            os.unlink(tmp_path)
    else:
        raise ValueError(f"不支持的简历文件类型: {ext or '(无扩展名)'}（仅支持 .pdf/.docx）")

    text = "\n".join(d.page_content for d in docs).strip()
    if not text:
        raise ValueError("简历文本提取结果为空（可能是扫描件或损坏文件）")
    if len(text) > MAX_TEXT_LENGTH:
        logger.warning("简历文本超长截断: cos_key=%s len=%s", state["cos_key"], len(text))
        text = text[:MAX_TEXT_LENGTH]
    logger.info(
        "简历文本提取完成: cos_key=%s ext=%s text_len=%s",
        state["cos_key"], ext or "?", len(text),
    )
    return {**state, "text": text}


def extract(state: ResumeParseState) -> ResumeParseState:
    """节点2：LLM 结构化提取（Pydantic schema 约束输出）。

    Args:
        state: 工作流状态（含 text）。

    Returns:
        更新后的状态（补充 extraction）。

    Raises:
        Exception: LLM 调用或结构化解析失败时向上抛出。
    """
    model: BaseChatModel = interview_model
    # DeepSeek 线上模型不支持 function_calling/json_schema（thinking 模式限制），
    # 统一使用 json_mode（requires prompt 含 "json" 字样，已在 RESUME_PARSE_PROMPT 补充）。
    structured = model.with_structured_output(ResumeExtraction, method="json_mode")
    result = structured.invoke(RESUME_PARSE_PROMPT + state["text"])
    if not isinstance(result, ResumeExtraction):
        raise ValueError(f"LLM结构化输出类型异常: {type(result)}")
    logger.info(
        "简历LLM结构化提取完成: name=%s skills=%s education=%s projects=%s works=%s",
        result.name, len(result.skills), len(result.education),
        len(result.projects), len(result.work_experience),
    )
    return {**state, "extraction": result}


def build_resume_parse_graph():
    """构建并编译简历解析工作流图。

    Returns:
        编译后的 LangGraph 可执行图（ainvoke 入参含 cos_key/file_url）。
    """
    graph = StateGraph(ResumeParseState)
    graph.add_node("load_document", load_document)
    graph.add_node("extract", extract)
    graph.add_edge(START, "load_document")
    graph.add_edge("load_document", "extract")
    graph.add_edge("extract", END)
    return graph.compile()


# 模块级编译单例（Worker进程内复用）
resume_parse_graph = build_resume_parse_graph()


def parse_resume(cos_key: str, file_url: str) -> ResumeExtraction:
    """同步执行简历解析工作流（Worker内经 asyncio.to_thread 调用）。

    PDF/DOCX 均传公开 file_url 直连各自加载器。

    Args:
        cos_key: COS对象Key（决定文件类型与加载策略）。
        file_url: 简历公开访问的线上链接。

    Returns:
        ResumeExtraction 结构化提取结果。

    Raises:
        ValueError: 文件类型不支持或文本为空。
        Exception: LLM 调用失败。
    """
    result = resume_parse_graph.invoke({"cos_key": cos_key, "file_url": file_url})
    return result["extraction"]