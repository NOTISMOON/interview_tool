# interview_graph 运行时节奏控制重构

## Context（背景与为什么改）

上一轮 P1 优化把面试判题链从 `interview_graph`（LangGraph 单图）抽成了 service 层散落函数（`_judge_no_lock` + `_stream_next_question`），导致 `interview_graph` 变成空壳：图构建了、checkpointer 绑定了，但入口 `run_fast_decision` **从未被调用**（[interview_service.py](file:///D:/Projects/interview_tool/api_server/app/services/interview_service.py) 只 import 不 invoke）。

这背离了《面试模块单LangGraph架构方案.md》"一张图承载整场面试节奏控制"的架构约定。**本次重构目标：interview_graph 重新掌控面试运行时节奏**（判定下一动作、流式追问、路由循环、Redis 中断、结束通知生成报告），service 只保留事务/锁/checkpoint/幂等编排。

用户已确认的设计决策：
1. **创建面试不进图**：创建时仍直接 `generate_questions()` 批量出题落库（改动面小）
2. **保留 LLM 意图判定**：`fast_decision` 由 LLM 判定全部动作（follow_up / next_base / end），恢复原图设计
3. **追问不入"图全局状态"的问题队列**：`InterviewState.question_queue`（发问顺序镜像）只装基础题；追问生成后**不进入该队列**，直接 SSE 流式推前端 + 记录为图全局状态/Redis checkpoint 的"当前题"，用户回答追问后才落库
4. **落库时机**：用户回答追问后，MQ 事件处理时：先出题落库 → 调用分析图 → 分析完成后分析落库（消除"问题未落库但分析先入库"的不一致）
5. **去掉独立语音纠错**：纠错指令融入分析/追问提示词，分析完落库时以纠错后回答更新 `user_answer`
6. **路由节点循环 + Redis 中断 + 结束时通知异步生成报告**

## 图的三态设计（interview_graph 重构核心）

LangGraph `compile(checkpointer, input=..., output=...)` 标准三态，取代现在"一个 `InterviewState` 全量透传、checkpointer 空转"的做法：

| 状态 | 类型 | 内容 | 生命周期 |
|------|------|------|----------|
| **输入状态** `InterviewInput` | input schema | 本轮调用数据：question_no / question_text / answer / resume_context / user_id（SSE发布） | 每次 invoke 由 service 填 |
| **全局状态** `InterviewState` | checkpointer 持久化（thread_id=interview_id） | base_questions、question_queue（仅基础题）、当前题指针 current_question_no、追问记录 pending_follow_up、follow_up_total、中断标记 | 跨轮保留，中断/恢复从该状态重建节奏 |
| **输出状态** `InterviewOutput` | output schema | next_action（follow_up/next_base/end）、follow_up_question、corrected_answer、next_base_text | invoke 返回给 service |

关键点：
- **追问不进 question_queue**：fast_decision 判 follow_up 后，追问文本先写入全局状态 `pending_follow_up`（并 SSE 直推前端、Redis checkpoint 记为当前题），**不 push 到 question_queue**；等用户回答追问后，在落库阶段才建 DB 行并出队推进
- **全局状态成为唯一节奏事实源**：Node 写全局状态 → checkpointer 保存；service 读输出状态执行落库/SSE；下次 invoke 时图直接从 checkpointer 恢复全局状态（不再全量透传）

## 目标流程（提交回答后单轮节奏）

```
用户提交回答（前端）
  → POST /answers（同步受理：epoch/幂等/版本校验 → checkpoint置analyzing + 记录当前题）
  → 投递 interview.answer.submitted 事件（MQ）→ 返回"已受理"

MQ Answer Consumer 处理事件（to_thread 同步链路）
  ① 执行 interview_graph.invoke（thread_id=interview_id，从 checkpointer 恢复全局状态）：
     init（校验/补全全局状态）
     → fast_decision（单次 LLM structured：next_action=follow_up|next_base|end）
     → follow_up_stream（仅 follow_up 时：LLM 流式生成追问，边生成边 SSE 推送，收集全文判 NONE；
       追问文本写入全局状态 pending_follow_up，不入 question_queue）
     → route（防御：end 但还有未答基础题→next_base；Redis 中断标记→end）
     → 输出 InterviewOutput {next_action, follow_up_question, corrected_answer, next_base_text}
  ② 短锁推进（_persist_and_advance_locked 改造）：
     - follow_up：全局状态 current_question=追问文本；SSE done 帧 → 前端展示追问
     - next_base：取 question_queue 下一道基础题文本 → SSE 分片流推送（DB 文本打字机）
     - end：finish → checkpoint=summarizing → 投递 report pending 事件（最后一个节点通知异步生成报告）
  ③ 异步并行分析：调 answer_analysis_graph（4 路并行）
     → 先出题落库（若是回答"未落库追问"，先建追问行：question_text 取自全局状态 pending_follow_up）
     → 分析完成后落库（ai_score/ai_comment，user_answer 更新为纠错后文本）

用户回答追问后（再次进入 ①，同理循环）——route 实现"循环"
```

## 关键代码变更

### 1. `app/llm/workflow/interview.py` — interview_graph 节点重构（核心）

- **保留**：`InterviewState` 结构、`_init`、`build_interview_graph`、checkpointer、`_thread_config`、`invalidate_checkpoint`
- **改造 `_fast_decision` 节点**：用 `judge_fast_model`（关闭 thinking，见 [models.py](file:///D:/Projects/interview_tool/api_server/app/llm/models.py) 的 `_build_judge_model`）structured 输出 `next_action ∈ {follow_up, next_base, end}` + `follow_up_question`，恢复原图语义
- **移除 speech_correct 节点**：不再有独立纠错 LLM 调用（纠错融入提示词）；`correct_speech_text` 函数删除或仅保留纯文本规整内部逻辑
- **调整 `run_fast_decision`**（作为 MQ 消费端 invoke 图的唯一入口）：
  - 参数：`interview_id, base_questions(含id/text), question_no, question_text, answer, resume_context, follow_up_total, unanswered_base_after, interrupted(Redis标记), user_id`（SSE 发布需）
  - 返回：`{next_action, follow_up_question(None/文本), corrected_answer}`
  - 流式 SSE 在节点内完成或由 service 在 invoke 后执行（见下述决策点）
- **路由循环**：图保持"单步推进、由 service 循环 invoke"（每次提交回答 = 一次 invoke，thread_id 固定）；route 防御逻辑保留

### 2. `app/services/interview_service.py` — 判题链收编

- `_judge_no_lock` 整体替换为 `run_fast_decision`（图）调用；删掉 service 内散落的"规则判定 can_follow_up + generate_follow_up_stream 收集"逻辑
- `_stream_next_question` 拆为两部分：
  - 追问流：图节点产出或节点内 SSE 推送（累积快照 judge_stream + done 帧）
  - 基础题分片流：保留在 service（DB 文本 3 字/55ms 分片推送），`_next_base_question` 复用
- `_persist_and_advance_locked` 调整落库顺序（对应"先出题落库 → 分析 → 分析落库"）：
  - follow_up 场景：**不再立即 create_follow_up**，只推进 checkpoint（current_question=追问文本）
  - 用户回答追问后：此刻创建追问题行（question_text 取 checkpoint.current_question）→ 作答分析完成后再落库 ai_score/ai_comment，user_answer=纠错后文本
- 移除：`correct_speech_text` 同步调用、问题队列 `enqueue_head` 追问插队（T3.8/T3.9 视觉镜像简化；追问不再入队，基础题按 question_no 顺序推进即可）
- SSE：`_publish_sse` 保留；新增/调整事件 `interview:judge_stream`（追问/基础题正文累积快照 text + done 终帧）、`interview:judged`（判题完成，携带纠正后回答可选）

### 3. `app/mq/consumers/interview_answer_consumer.py` — 编排顺序

- `handle_message` 内顺序调整：判题图 → 短锁推进 → 异步并行分析 → 分析落库（保持断言）
- **分析并入判题链**：`analyze_answer_parallel` 在 answer.submitted 处理内调用（to_thread），完成后同链落库；`InterviewAnalysisConsumer`（独立 analysis 队列）停用或移除，报告生成不再依赖 REport_ANALYSIS_WAIT_SECONDS 轮询补齐

### 4. 提示词与纠错融合（`app/prompt.py` / `app/llm/schemas/interview.py`）

- `CONTENT_ANALYSIS_PROMPT` / `TECHNICAL_DEPTH_PROMPT` / `COMPLETENESS_LOGIC_PROMPT` / `SCORING_PROMPT` / `FOLLOW_UP_STREAM_PROMPT`: 增加"若识别到语音/输入错误先纠正，在纠正后的语义上分析；输出 corrected_answer"
- 分析结果 schema 增加 `corrected_answer` 字段（必填，min_length=1，避免模型 json_mode 省略导致空串回退原文），落库时用纠错后回答更新 `user_answer`

### 5. 前端（承接正文流改造，已在进行）

- 消费 `interview:judge_stream`：累积快照 text 整段替换直印题目卡片（无独立预览框）；done 终帧携带完整文本与元数据
- `judged` 事件补全分析元数据；移除前端 typedLen 模拟打字/预览续打（第三轮改造已完成主体）

## 明确的取舍 / 不做的事

- ❌ 创建面试入图（用户明确:创建不应进入图）
- ❌ 追问入问题队列（用户明确:追问直接 SSE 输出，不入队）
- ✅ LLM 判全部动作（接受多一次 LLM 判定延迟，judge_fast_model 关闭 thinking 已显著提速，约秒级）
- ⚠️ 分析并入判题链后，每题回答的处理时长会增加 4 路并行分析耗时——用户已确认该时序（先出题落库→分析→分析落库），保障数据一致性优先

## 执行步骤

1. `app/llm/workflow/interview.py`：重构节点（fast_decision 接 judge_fast_model、删 speech_correct 节点、改 run_fast_decision 签名与返回值、补 import time 与 QUESTION_STREAM_SLICE_DELAY=0.055 常量）
2. `app/prompt.py` + `app/llm/schemas/interview.py`：提示词融入纠错指令；schema 增加 corrected_answer
3. `app/services/interview_service.py`：`_judge_no_lock` 换图为 `run_fast_decision`；`_persist_and_advance_locked` 按新落库时机改造；删追问插队；调整 SSE 事件
4. `app/mq/consumers/interview_answer_consumer.py`：编排顺序调整（判题→落库题目→分析→分析落库）
5. 停用 `app/mq/consumers/interview_analysis_consumer.py`（分析并入主链）
6. 前端已完成的正文流消费验证
7. 构建部署前后端 + 完整链路测试

## 验证

1. 后端单测/冒烟：`run_fast_decision` 被调用（不再是死代码）；创建面试不发图
2. 完整面试流程（dev-login + 快速面试）：
   - 提交回答 → 追问以流式出现于前端题目卡片（SSE judge_stream 累积快照，前端整段替换）
   - 回答追问 → 追问行此时才落库 → 分析完成后 ai_score/ai_comment 就绪
   - 追问不占问题队列；基础题按序推进；全题答完/超时/Redis 手动中断均能结束并触发报告生成
3. Docker 日志：Answer Consumer 单条消息全链路完成（判题→落库→分析→落库），无"分析未就绪"轮询等待