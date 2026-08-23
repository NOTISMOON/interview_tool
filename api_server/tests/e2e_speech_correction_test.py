"""端到端纠错效果测试：语音识别文本纠错节点（真实 LLM）。

用包含乱码（同音/近音字）与口头禅的 ASR 文本验证 _speech_correct 节点的
纠错效果：技术术语被纠正、语义保留、不被润色/评价、空文本原样返回。

覆盖《语音识别纠错》设计约定：
    - 同音/近音字纠错（如 拍审测士 -> pytest）
    - 技术术语/框架/库/产品名纠错（依赖简历技术栈上下文）
    - 口头禅是否保留按当前 prompt 规则（禁止删减用户内容）如实报告，不做硬断言
    - 空文本 / 纯语气词原样返回
    - 输出不含评价性、不回答面试问题

用法: 在 api_server 目录下用 interview 环境运行
    python tests/e2e_speech_correction_test.py

前提: DeepSeek 或本地 Ollama（interview_model 可调用）正常。
"""

import sys
from pathlib import Path

# 允许直接 python 运行时从项目根导入 app 包（脚本位于 tests/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.workflow.interview import _speech_correct  # noqa: E402

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    """记录单个断言结果。"""
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        FAIL.append((name, detail))
        print(f"  [FAIL] {name} -> {detail}")


# 简历技术栈上下文（提示纠错节点识别项目术语）
RESUME_CONTEXT = {
    "name": "测试候选人",
    "skills": ["Python", "FastAPI", "MySQL", "Redis", "RabbitMQ", "Docker", "Kubernetes", "pytest", "watchdog"],
    "projects": [],
    "work_experience": [],
    "education": [],
}

# 每个用例：name 名称 / question 当前面试题 / transcript 原始 ASR 文本
#   must_contain: 纠正后必须包含的关键词（乱码被纠正为正确术语）
#   keep_terms:   纠正后不得丢失的技术词（防止误删语义）
#   forbidden:    纠正后不得出现的内容（评价/脑补等）
CASES = [
    {
        "name": "同音术语乱码",
        "question": "请介绍你日常开发中常用的工具与框架",
        "transcript": "我主要负责后端的拍审测士测试，呃，还用了坏门狗监听文件变化",
        "must_contain": ["pytest", "watchdog"],
        "keep_terms": [],
        "forbidden": [],
    },
    {
        "name": "技术术语中英混杂",
        "question": "你的后端服务是怎么提供接口的？",
        "transcript": "后端是用方撕它比起的服务，然后呢，数据库用的买色扣，消息队列用的是热比特MQ",
        "must_contain": ["FastAPI", "MySQL", "RabbitMQ"],
        "keep_terms": [],
        "forbidden": [],
    },
    {
        "name": "部署编排术语",
        "question": "你们是怎么部署和发布服务的？",
        "transcript": "部署用的是道客，呃，容器编排用库伯内茨",
        "must_contain": ["Docker", "Kubernetes"],
        "keep_terms": [],
        "forbidden": [],
    },
    {
        "name": "口头禅密集(语义保留)",
        "question": "你项目中缓存是怎么设计的？",
        "transcript": "嗯，那个，我的项目呢，呃，就是，那个，用瑞迪斯做缓存，然后呢，就是，这个，那个，用买色扣存数据",
        "must_contain": ["redis", "Redis", "mysql", "MySQL"],
        "keep_terms": ["缓存"],
        "forbidden": [],
    },
    {
        "name": "无明显乱码(最小改动)",
        "question": "你们团队用什么做版本管理？",
        "transcript": "我们团队用了git做版本管理，代码托管在gitee上",
        "must_contain": ["git", "gitee"],
        "keep_terms": [],
        "forbidden": [],
    },
    {
        "name": "空文本原样返回",
        "question": "请开始回答",
        "transcript": "",
        "must_contain": [],
        "keep_terms": [],
        "forbidden": [],
        "expect_empty": True,
    },
    {
        "name": "纯语气词",
        "question": "请开始回答",
        "transcript": "嗯，呃，那个",
        "must_contain": [],
        "keep_terms": [],
        "forbidden": [],
        "no_add": True,  # 不得脑补出实际内容
    },
]

# 禁止出现的评价性/越界内容（任何用例都不允许）
GLOBAL_FORBIDDEN = ["回答得不错", "回答得很好", "很好", "优秀", "正确", "你的问题是", "请回答"]


def run_case(case: dict) -> None:
    """执行单个纠错用例并断言。"""
    name = case["name"]
    state = {
        "interview_id": 1,
        "question_text": case["question"],
        "resume_context": RESUME_CONTEXT,
        "answer": case["transcript"],
    }
    print(f"\n== {name} ==")
    print(f"  原始  : {case['transcript']!r}")
    corrected = _speech_correct(state)["answer"]
    print(f"  纠正后: {corrected!r}")

    # 空文本：原样返回空
    if case.get("expect_empty"):
        check(f"{name} 空文本返回空", corrected == "", f"实际={corrected!r}")
        return

    # 非空
    check(f"{name} 结果非空", bool(corrected.strip()), f"实际={corrected!r}")

    # 必须包含纠正后的术语（大小写不敏感）
    lowered = corrected.lower()
    for term in case["must_contain"]:
        check(f"{name} 含术语 {term}", term.lower() in lowered, f"纠正后={corrected!r}")

    # 不得丢失的语义关键词
    for term in case["keep_terms"]:
        check(f"{name} 保留 {term}", term in corrected, f"纠正后={corrected!r}")

    # 不得脑补内容（如纯语气词被补成完整答案）
    if case.get("no_add"):
        # 语气词文本纠错后不应凭空多出实际语义内容（允许仅加标点/语气词原样）
        added = corrected.replace("嗯", "").replace("呃", "").replace("那个", "").replace("，", "").replace("。", "")
        check(f"{name} 未脑补内容", len(added.strip()) <= 1, f"纠正后={corrected!r}")

    # 全局禁止：评价性语言 / 回答面试问题
    for word in GLOBAL_FORBIDDEN:
        check(f"{name} 不含 {word}", word not in corrected, f"纠正后={corrected!r}")


def main() -> None:
    """执行全部纠错用例并输出汇总。"""
    print("语音识别纠错效果测试（真实 LLM）")
    for case in CASES:
        run_case(case)

    print(f"\n结果: {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("失败明细:")
        for name, detail in FAIL:
            print(f"  - {name}: {detail}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
