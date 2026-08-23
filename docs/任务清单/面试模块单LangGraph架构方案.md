# 面试模块单 LangGraph 架构方案（v2 · 追问即时判定 + 分析异步化）

> 状态：**提案 v2**（替代 2026-08-23 的 v1；本次针对 v1「追问判定/分析迟缓、无真实面试感」的痛点重构）
> 更新日期：2026-08-23
> 关联：现行实现见 [面试流程功能文档](../功能模块流程/面试流程功能文档.md)（手写状态机 + 三单轮图 + 同步合并调用）

---

## 一、要解决的痛点（v1 的不足）

现实现「提交回答 → 同步单次合并 LLM 调用（分析+评分+追问预生成，5~15 秒）→ 才返回下一题」，
真实面试中用户需要即时进入下一题的紧张感，5~15 秒的等待不可接受。

**核心诉求**：
1. **追问判定必须即时**：回答完立刻知道「下一题是什么」（追问 or 下一基础题）；
2. **全量分析与评分异步**：答案深挖、打分、能力画像更新用户在面试中无需感知，
   异步落后台处理，面试结束后在报告页/逐题详情统一呈现。

---

## 二、新架构总览

```text
━━━━━━━━━━━━━━ 同步（面试请求内，毫秒~1秒级） ━━━━━━━━━━━━━━

一个 Interview Graph（thread_id = interview_id，Redis checkpointer）
   │
   ▼
Question Agent ── LLM 批量预生成基础题（创建时一次调用）
   │
   ▼
Fast Decision Agent ── 回答后【快速判定下一题】（追问 or 下一基础题）
   │
   ▼
Interrupt ── 返回下一题并挂起，等用户回答（图休眠）
   ▲
   │ 用户回答（POST /answers，幂等预检后 resume）
   └────────────

━━━━━━━━━━━━━━ 后台异步（RabbitMQ，用户无感知） ━━━━━━━━━━━━━━

用户回答（同步路径同时投递 MQ）
   │
   ▼
RabbitMQ（interview.analysis.queue）
   │
   ▼
Analysis Worker
   │
   ├── Answer Analysis  ── LLM 深挖回答（要点/薄弱点/追问依据）
   │
   ├── Score           ── LLM 打分（ai_score / ai_comment）
   │
   ├── 更新能力画像     ── 累计考生能力画像（面试中渐进，报告用）
   │
   └── 保存分析结果     ── 逐题落库 interview_question + 冗余计数
```

**关键解耦**：同步路径只做**轻量判定**（Fast Decision）快速出下一题并返回；
慢的**全量分析评分**（Answer Analysis / Score）全部走 MQ 异步落库，
**前端/同步 API 不等待**，面试结束后从 MySQL 读取完整分析在报告页呈现。

---

## 三、同步 Graph（面试节奏控制器）

### 3.1 图状态

```python
class InterviewState(TypedDict):
    interview_id: int
    user_id: int
    resume_id: int
    interview_type: int            # 1-完整 2-快速

    resume_context: dict           # 简历结构化上下文
    questions: list[dict]          # 题目队列（基础题 + 已判定的追问，发问顺序）
    current_index: int             # 当前发问题序（1 起）
    pending_answer: str | None     # interrupt 恢复时写入

    # Fast Decision 产出
    next_action: str               # "follow_up" | "next_base" | "end" | "time_bound_end"
    follow_up_question: str | None # 判定的追问（若有）
    # 本轮异步分析将落库的内容（用于 Worker 幂等校验）
    pending_analysis_ref: str      # 例如 "interview:{id}:q{question_id}:{attempt}" 唯一引用

    answered_count: int
    follow_up_total: int
    started_at: str
    # 终态
    report: dict | None
```

### 3.2 节点

| 节点 | 类型 | 职责 | 是否 LLM |
|---|---|---|---|
| `init` | 代码 | 加载 resume_context / 计数 | 否 |
| `question_agent` | LLM | 批量预生成基础题（复用现有 `question_generation`） | 是（创建时一次） |
| `fast_decision` | **快 LLM 或 规则** | 判定追问并产出下一题（见 §四） | **轻量** |
| `ask` | interrupt | 挂起等用户回答；resume 后进入 routing | 否 |
| `route` | 代码 | 按 `next_action` 分派：追问→append 到 questions 后 ask；下一基础题→ask；end→summary | 否 |
| `summary_agent` | 后台触发 | 生成报告（复用 `report_generation`） | 是 |
| `end` | 代码 | 落库终态 + 清理租约 + SSE report_ready | 否 |

### 3.3 流程（同步，毫秒~1秒返回）

```text
创建面试：init → question_agent → fast_decision(出第1题, 下一动作=pending) → ask(interrupt 首题)
提交回答：幂等预检 → resume({answer}) → 同步投递 MQ → fast_decision
            ├── next_action=follow_up  → 追问 append → ask(interrupt 追问)   ← 立即返回追问
            ├── next_action=next_base  → ask(interrupt 下一基础题)            ← 立即返回下一题
            └── next_action=end        → summary_agent(后台/立即)
```

> 追问规则（§10 现行）可**前移为 Fast Decision 的纯规则短路**（不调 LLM，
> 基于 resume_context + 当前回答长度/关键词快速给倾向），也可用极轻量 LLM 单次调用决策。
> 无论哪种，**判定都在同步路径内、亚秒级完成**，用户随即进入下一题。

---

## 四、Fast Decision Agent：即时判定（核心改动）

### 4.1 目标

回答后 **≤ ~0.5~1 秒** 返回「下一题是什么（追问/下一基础/结束）」，不等待全量分析。

### 4.2 两种实现取向（实施时二选一，或结合）

| 取向 | 做法 | 延迟 | 质量 | 适用 |
|---|---|---|---|---|
| A. 规则短路 | 基于 `resume_context` + 当前回答长度/关键词/§10 规则的简化预判 | 毫秒 | 中 | 追赶真实面试节奏，成本最低 |
| B. 轻量 Fast LLM | 一个低 temp、短 prompt、只出 `{next_action, follow_up_question}` 的小调用 | ~1 秒 | 较高 | 需追问贴合回答动态生成 |

**推荐结合**：用 A 规则判定「是否追问」给即时反馈，B 的追问文本可**后台**由 Analysis Worker 生成后补到下一题（若 Worker 还没产出，先展示追问占位并允许先答）。

> ⚠️ 若完全不要任何同步 LLM，又要求追问贴合回答，则只有两条路：
> ① 面试节奏设计成「**下一题先呈现基础题/固定追问池**」，追加的贴合追问靠异步补齐；
> ② 接受每题多 ~1 秒的 Fast LLM 成本。此为本方案要用户拍板的关键分叉（见 §八决策点）。

---

## 五、异步 Analysis Worker（RabbitMQ 冷静分析）

### 5.1 触发：同步路径投递 MQ

同步提交回答后，除图 resume 外，**在同一事务/紧接其后投递**

```python
sync_outbox_repository.insert_event(
    db,
    event_type="interview.analysis",               # 新事件类型
    aggregate_type="interview",
    aggregate_id=str(interview_id),
    payload={
        "interview_id": ..., "user_id": ...,
        "question_id": ..., "question_index": ...,
        "answer": ..., "answer_duration": ...,
        "priority_ref": f"interview:{interview_id}:q{question_id}:{attempt}",
    },
)
# 后续由 outbox relay 投递到 interview.analysis.queue
```

> 沿用现行 Outbox（Transactional Outbox）保证「回答落库 + 异步任务投递」原子一致，
> 与简历分析投递同构（见 `resume_service._schedule_analysis` + `sync_outbox_repository`）。

### 5.2 Worker 节点（独立进程，LangGraph 多节点图或顺序执行）

```text
answer_analysis ── LLM 深挖：correctness/key_points/weaknesses/追问依据
score           ── LLM 打分：ai_score(1-5)/ai_comment，落 interview_question
profile_update  ── 更新能力画像（面试中渐进，报告阶段汇总）
persist         ── 单事务写 interview_question(user_answer/ai_score/ai_comment/answer_duration) + 冗余计数
ssa_notify      ──（可选）SSE 推送"本题分析已完成"通知
```

- **并发保障**：沿用 `interview:analysis:lock:{interview_id}` 或按 `(interview_id, question_index)` 
  幂等键；Worker 先查 `interview_question.ai_score` 是否已写入，已写则跳过（防重复分析/重复投递）。
- **失败矩阵（§21 对齐）**：LLM 失败重试 N 次 → 置 `ai_comment="分析失败"`（ai_score NULL）并告警，
  可提供「本题重新分析」入口（可选）。

### 5.3 能力画像

- **平时**：Worker 每次 `profile_update` 累加 AVG 或最近 N 次汇总，存 Redis 画像缓存
  `interview:profile:{interview_id}`；
- **报告时**：`summary_agent` 读取该缓存 + 各题分数，生成 `capability_profile` 落报告表。

---

## 六、同步/异步一致性保障（关键约束）

| 约束 | 说明 |
|---|---|
| **返回下一题不等待分析** | 同步路径只返回 Fast Decision 结果与下一题；分析结果异步后补 |
| **逐题落库由 Worker 负责** | `user_answer` 由同步路径先落（答题即存，防丢），`ai_score/ai_comment` 由 Worker 补 |
| **进度计数以审题为准** | 面试进度/下一题由 Graph `current_index` 判定，不依赖 Worker 是否已分析完 |
| **报告依赖完整性** | `summary_agent` 触发前，先确保缺分析分的题补齐（轮询 Redis 画像/DB 计数，超时则带"待补充"标记生成） |
| **幂等** | 同步 `POST /answers` 幂等预检（§5.9）；Worker 按 `priority_ref`/`(id, question_index)` 幂等 |

---

## 七、API 契约（保持不变，响应更快）

| 方法 | 路径 | 响应变化 |
|---|---|---|
| POST | `/interviews` | 不变：返回 id + 首题 |
| GET | `/interviews/{id}` | 不变：状态/当前题；`analysis` 字段指示该题是否已有 Worker 分析 |
| POST | `/interviews/{id}/answers` | **立即返回下一题**（Fast Decision）；不再同步携带逐题 `analysis` 详情 |
| GET | `/interviews/{id}/report` | 不变：报告 + 逐题详情（此时 Worker 应已补齐各题评分） |
| (新增) | `/interviews/{id}/questions/{qid}/analysis` | 可选：单题异步分析结果查询（前端逐题区可轮询后补） |

**前端 UI 需同步改（用户已确认）**：
1. 提交回答后**立即进入下一题**（取消 "分析中 5~15 秒" 等待态）；
2. 每题作答完毕停留时的反馈 → 从「同步弹 AI 点评」改为「进场先给 Fast 判定可空，
   分析完成后经等待/轮询/SSE 后补展示」；
3. 面试完成页/报告页展示完整分析（报告功能不变）。

---

## 八、待用户拍板的关键决策

| # | 决策 | 选项 |
|---|---|---|
| 1 | **Fast Decision 是否含 LLM** | A. 纯规则（毫秒，追问不够贴合） / B. 轻量 LLM（~1s，贴合） / C. 规则返回 + 追问文本异步补 |
| 2 | **分析是否完全移出同步路径** | 彻底异步（下一题零等待） / 同步快分析+异步深挖（折中，仍 ~1s 才进下一题？） |
| 3 | **下一题能否是"未判定的追问占位"** | 立即给下一基础题、追问异步插队 / 必须等追问文本生成后再进下一题 |
| 4 | **MQ 重试与失败兜底时长** | 分析落后于用户进度时，报告前强制补齐的最长等待 |

> 建议默认：**决策1=C（规则即时判定是否追问 + 追问文本由 Worker 异步生成，先展示追问占位），
> 决策2=彻底异步，决策3=允许占位，决策4=报告前轮询补齐（如 60s，超时带"待补充"）**。

---

## 九、迁移范围与回归清单

**改动面**：
- 重写：`app/llm/workflow/interview.py`（三单轮图 → 一图，含 Fast Decision）；`interview_service` 编排；
- 新增：`app/mq/consumers/interview_analysis_consumer.py` + `QueueName.INTERVIEW_ANALYSIS` + 
  交换机 binding `interview.analysis`；能力画像缓存读写；
- 复用：Outbox 投递、Redis 并发三件套、SSE、报告查询/重试链路、前端大部分交互。

**回归清单**（浏览器实测）：
- [ ] 提交回答 → **秒级**进下一题（追问/下一基础/结束判定正确）
- [ ] Worker 异步：性能正常、每题的 ai_score/ai_comment 后补落库正确
- [ ] 幂等：同步重复提交 / Worker 重复消费均不重复分析
- [ ] 刷新恢复：answering（next_action 待定、Fast 后补）、Worker 分析中的题正确恢复
- [ ] 双开互斥 + 接管拉锯（同步路径不变）
- [ ] 放弃/超时中断；报告前分析补齐逻辑与"待补充"标记
- [ ] LLM 失败矩阵（同步 Fast 失败、异步分析失败）不丢数据、可重试
- [ ] 后端单测全量 + 面试模块单元测试重写 + e2e 冒烟

---

## 十、决策记录

| 日期 | 决策 | 说明 |
|---|---|---|
| 2026-08-23 | 提出 v2：Fast Decision 即时判定 + Analysis 全异步 | 解决 v1「追问判定/分析迟缓、无真实面试感」痛点；倾向前端/同步零等待、报告后完整呈现 |
| 待定 | 决策 1~4 由用户拍板后进入实施，或先出 POC 验证 Fast Decision 延迟与追问贴合度 |