# 面试模块数据库重构计划（对齐前端 v2 原型）

## Context（背景）

前端面试相关页面已按 `interview-v2-prototype.html` 重构，核心变化：

1. **语音回答**：面试间改为暗色沉浸式，每题先 20 秒思考倒计时，再录音作答（波形动画 + 计时），不再是文本框输入。
2. **追问题**：AI 会基于回答动态追问，题目带「追问」徽标，需关联父题目。
3. **题目维度**：题目按「技术基础 / 项目经验 / 综合素质 / 架构设计」四维度分类（与现有 `question_type` 题型正交）。
4. **设备检测**：进入面试前需通过麦克风 + 摄像头检测。
5. **完成统计**：面试结束展示总题数、追问次数、总用时。

现有 `interview` / `interview_question` / `interview_report` 三张表无法承载上述数据，需补字段。社区、消息、用户等模块不受影响。

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| `category` 存储 | `TINYINT UNSIGNED` 枚举（1-技术基础 2-项目经验 3-综合素质 4-架构设计） | 与现有 `question_type`、`status` 等枚举字段保持一致，紧凑高效 |
| 语音回答存储 | `audio_url` + `answer_duration` 直接挂在 `interview_question` 上 | 一题一答为 1:1，无需独立答案表；`user_answer` 保留用于存转写文本 |
| 追问关联 | `is_follow_up` + `parent_question_id` | 支持追问挂到父题目，便于追溯 |
| 统计字段冗余 | `total_duration` / `follow_up_count` 同时存于 `interview` 与 `interview_report` | 与现有 `question_count` 冗余策略一致，列表展示免聚合 |
| 设备检测 | `device_check_passed` 存于 `interview` | 单次会话级状态，无需独立表 |
| 思考时长 | `thinking_duration` 存于 `interview_question`（可空） | 成本低，便于分析候选人思考习惯 |
| 变更方式 | `ALTER TABLE ... ADD COLUMN`（非破坏性） | 现有表无数据丢失风险，新字段均带默认值或可空 |

## 实施步骤

### 步骤 1：修改数据库（MySQL ALTER TABLE）

通过 MCP MySQL `execute_sql` 执行以下三条 ALTER（非破坏性，可回滚 DROP COLUMN）：

**1.1 `interview` 表** — 增 3 列：
```sql
ALTER TABLE `interview`
  ADD COLUMN `total_duration`      INT UNSIGNED     DEFAULT NULL COMMENT '面试总时长（秒）' AFTER `total_score`,
  ADD COLUMN `follow_up_count`     INT UNSIGNED     NOT NULL DEFAULT 0 COMMENT '追问次数' AFTER `total_duration`,
  ADD COLUMN `device_check_passed` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '设备检测是否通过 0-未通过 1-已通过' AFTER `follow_up_count`;
```

**1.2 `interview_question` 表** — 增 6 列：
```sql
ALTER TABLE `interview_question`
  ADD COLUMN `category`           TINYINT UNSIGNED DEFAULT NULL COMMENT '题目维度 1-技术基础 2-项目经验 3-综合素质 4-架构设计' AFTER `question_type`,
  ADD COLUMN `is_follow_up`       TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '是否追问题 0-否 1-是' AFTER `category`,
  ADD COLUMN `parent_question_id` BIGINT UNSIGNED  DEFAULT NULL COMMENT '父题目ID（追问关联，指向 interview_question.id）' AFTER `is_follow_up`,
  ADD COLUMN `audio_url`          VARCHAR(512)     DEFAULT NULL COMMENT '语音回答文件地址' AFTER `user_answer`,
  ADD COLUMN `answer_duration`    INT UNSIGNED     DEFAULT NULL COMMENT '回答时长（秒）' AFTER `audio_url`,
  ADD COLUMN `thinking_duration`  INT UNSIGNED     DEFAULT NULL COMMENT '思考时长（秒）' AFTER `answer_duration`;
```

**1.3 `interview_report` 表** — 增 2 列：
```sql
ALTER TABLE `interview_report`
  ADD COLUMN `follow_up_count` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '追问次数' AFTER `question_count`,
  ADD COLUMN `total_duration`  INT UNSIGNED DEFAULT NULL COMMENT '面试总时长（秒）' AFTER `follow_up_count`;
```

> 不新增索引：现有 `idx_interview_id` / `idx_interview_no` 已覆盖按会话取题与排序；`category`、`is_follow_up` 通常随会话批量读取，无独立查询需求。

### 步骤 2：更新数据库设计文档

文件：[docs/数据库设计文档.md](file:///d:/项目/interview_tool/docs/数据库设计文档.md)

- 顶部版本：`v1.2` → `v1.3`，更新日期为 2026-08-17，修订说明补「面试模块对齐前端 v2：语音回答、追问题、题目维度、设备检测、时长统计」。
- **2.6 `interview`** 表 DDL 与字段说明表补 `total_duration` / `follow_up_count` / `device_check_passed` 三列。
- **2.7 `interview_question`** 表 DDL 与字段说明表补 `category` / `is_follow_up` / `parent_question_id` / `audio_url` / `answer_duration` / `thinking_duration` 六列；新增「`category` 枚举约定」与「追问关联说明」小节。
- **2.8 `interview_report`** 表 DDL 与字段说明表补 `follow_up_count` / `total_duration` 两列。
- **六、开发注意事项**：补一条「面试语音回答：`audio_url` 为文件地址，`user_answer` 存转写文本；追问通过 `is_follow_up` + `parent_question_id` 自关联」。

### 步骤 3：验证

- 用 `get_schema_info` 复核三张表新字段存在且类型/可空性正确。
- 用 `get_table_sample` 确认现有数据未被破坏（表为空亦属正常，此前未插入测试数据）。

## 不在本次范围

- 后端 SQLAlchemy ORM 模型（`api_server/app/models/` 目前仅 user/user_auth，面试模型后续单独建）。
- 前端 mock 数据调整（已在前序任务完成）。
- 插入测试数据（用户此前未要求）。
