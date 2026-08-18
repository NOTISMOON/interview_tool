# 后端待完成功能清单

> 基于前端工程 `web_front` 的需求分析，梳理后端 `api_server` 所有待开发的功能模块。
> 
> 已实现：GitHub OAuth 认证（登录/回调/刷新/退出）、用户基础模型。
> 
> 本文档版本：v1.0 | 日期：2026-08-18

---

## 目录

1. [数据库表设计](#1-数据库表设计)
2. [用户管理模块](#2-用户管理模块)
3. [简历管理模块](#3-简历管理模块)
4. [面试管理模块](#4-面试管理模块)
5. [社区帖子模块](#5-社区帖子模块)
6. [社交关注模块](#6-社交关注模块)
7. [消息通知模块](#7-消息通知模块)
8. [私信聊天模块](#8-私信聊天模块)
9. [收藏功能模块](#9-收藏功能模块)
10. [用户设置模块](#10-用户设置模块)
11. [文件上传模块](#11-文件上传模块)
12. [AI 服务集成模块](#12-ai-服务集成模块)
13. [API 路由汇总](#13-api-路由汇总)

---

## 1. 数据库表设计

### 1.1 resume（简历表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| user_id | BIGINT FK | 关联 user 表 |
| file_name | VARCHAR(255) | 原始文件名 |
| file_url | VARCHAR(512) | 文件存储URL |
| file_size | INT | 文件大小（字节） |
| status | TINYINT | 0-解析中 1-就绪 2-失败 |
| parsed_content | TEXT(JSON) | AI解析后的结构化内容（JSON） |
| created_at | DATETIME | 上传时间 |
| updated_at | DATETIME | 更新时间 |

### 1.2 interview（面试记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| user_id | BIGINT FK | 关联 user 表 |
| resume_id | BIGINT FK | 关联 resume 表 |
| type | VARCHAR(16) | full / quick |
| status | TINYINT | 0-进行中 1-已完成 |
| total_score | INT | 总分（完成时填充） |
| summary | TEXT | 综合评语 |
| strengths | TEXT(JSON) | 优势列表（JSON数组） |
| weaknesses | TEXT(JSON) | 待改进列表（JSON数组） |
| suggestions | TEXT(JSON) | 建议列表（JSON数组） |
| question_count | INT | 题目总数 |
| created_at | DATETIME | 创建时间 |
| completed_at | DATETIME | 完成时间 |

### 1.3 interview_question（面试题目表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| interview_id | BIGINT FK | 关联 interview 表 |
| question_no | INT | 题号 |
| question_text | TEXT | 题目文本 |
| question_type | VARCHAR(16) | technical / project / behavioral |
| category | VARCHAR(32) | 技术基础 / 项目经验 / 综合素质 / 架构设计 |
| follow_up | TINYINT | 0-否 1-是（追问） |
| user_answer | TEXT | 用户答案 |
| ai_score | INT | AI评分（1-5） |
| ai_comment | TEXT | AI评语 |
| sort_order | INT | 排序 |

### 1.4 post（社区帖子表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| author_id | BIGINT FK | 关联 user 表 |
| title | VARCHAR(200) | 帖子标题 |
| content | TEXT | 帖子内容 |
| tags | VARCHAR(512) | 标签（JSON数组） |
| likes_count | INT | 点赞数 |
| comments_count | INT | 评论数 |
| views_count | INT | 浏览数 |
| is_pinned | TINYINT | 0-否 1-置顶 |
| is_hot | TINYINT | 0-否 1-热门 |
| status | TINYINT | 0-删除 1-正常 |
| created_at | DATETIME | 发布时间 |
| updated_at | DATETIME | 更新时间 |

### 1.5 post_comment（帖子评论表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| post_id | BIGINT FK | 关联 post 表 |
| author_id | BIGINT FK | 关联 user 表 |
| content | TEXT | 评论内容 |
| likes_count | INT | 点赞数 |
| status | TINYINT | 0-删除 1-正常 |
| created_at | DATETIME | 评论时间 |

### 1.6 post_like（帖子点赞表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| user_id | BIGINT FK | 关联 user 表 |
| post_id | BIGINT FK | 关联 post 表 |
| created_at | DATETIME | 点赞时间 |

> 唯一索引：`(user_id, post_id)`

### 1.7 post_favorite（帖子收藏表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| user_id | BIGINT FK | 关联 user 表 |
| post_id | BIGINT FK | 关联 post 表 |
| created_at | DATETIME | 收藏时间 |

> 唯一索引：`(user_id, post_id)`

### 1.8 post_image（帖子图片表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| post_id | BIGINT FK | 关联 post 表 |
| image_url | VARCHAR(512) | 图片URL |
| sort_order | INT | 排序 |

### 1.9 user_follow（用户关注关系表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| follower_id | BIGINT FK | 关注者（粉丝） |
| followee_id | BIGINT FK | 被关注者 |
| created_at | DATETIME | 关注时间 |

> 唯一索引：`(follower_id, followee_id)`

### 1.10 message（消息通知表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| user_id | BIGINT FK | 接收者 |
| type | VARCHAR(16) | system / like / comment / follow / dm |
| title | VARCHAR(200) | 消息标题 |
| content | TEXT | 消息内容 |
| from_user_id | BIGINT | 发送者（点赞/评论/关注等场景） |
| related_id | BIGINT | 关联对象ID（帖子/报告/用户） |
| related_type | VARCHAR(16) | post / report / user |
| is_read | TINYINT | 0-未读 1-已读 |
| created_at | DATETIME | 通知时间 |

### 1.11 conversation（私信会话表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| user1_id | BIGINT FK | 参与方1 |
| user2_id | BIGINT FK | 参与方2 |
| last_message | VARCHAR(500) | 最后一条消息预览 |
| last_message_at | DATETIME | 最后消息时间 |
| created_at | DATETIME | 创建时间 |

### 1.12 dm_message（私信消息表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| conversation_id | BIGINT FK | 关联 conversation 表 |
| from_user_id | BIGINT FK | 发送者 |
| content | TEXT | 消息内容 |
| is_read | TINYINT | 0-未读 1-已读 |
| created_at | DATETIME | 发送时间 |

### 1.13 user_settings（用户设置表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| user_id | BIGINT FK UNIQUE | 关联 user 表 |
| email_notify | TINYINT | 邮件通知开关 |
| push_notify | TINYINT | 推送通知开关 |
| sound_enabled | TINYINT | 声音提示开关 |
| public_profile | TINYINT | 公开个人主页开关 |
| language | VARCHAR(16) | 语言偏好 |
| updated_at | DATETIME | 更新时间 |

### 1.14 扩展现有 user 表

需在现有 `user` 表基础上新增字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| profile_visibility | TEXT(JSON) | 资料字段可见性设置（JSON） |

---

## 2. 用户管理模块

### 2.1 获取当前用户信息

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/users/me` |
| 认证 | 需要 |
| 说明 | 返回已登录用户的完整信息，包括昵称、头像、性别、生日、简介、手机号、所在地、关注数、粉丝数、发帖数、资料可见性设置 |

### 2.2 更新个人资料

| 项目 | 说明 |
|------|------|
| 方法 | `PUT` |
| 路径 | `/api/v1/users/me` |
| 认证 | 需要 |
| 说明 | 更新昵称、头像（URL）、性别、生日、简介、手机号、所在地 |
| 请求体 | `{ nickname, avatar, gender, birthday, bio, phone, location }` |

### 2.3 更新资料可见性

| 项目 | 说明 |
|------|------|
| 方法 | `PUT` |
| 路径 | `/api/v1/users/me/profile-visibility` |
| 认证 | 需要 |
| 说明 | 设置各字段是否对外可见 |
| 请求体 | `{ gender, birthday, bio, location, phone }` |

### 2.4 获取其他用户公开资料

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/users/{user_id}` |
| 认证 | 需要 |
| 说明 | 返回用户公开资料（根据 profile_visibility 过滤），包含关注/粉丝数、帖子数、帖子列表、动态列表 |

### 2.5 注销账号

| 项目 | 说明 |
|------|------|
| 方法 | `DELETE` |
| 路径 | `/api/v1/users/me` |
| 认证 | 需要 |
| 说明 | 永久删除用户所有数据 |

---

## 3. 简历管理模块

### 3.1 上传简历

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/resumes/upload` |
| 认证 | 需要 |
| 说明 | 上传简历文件（支持 PDF、Word、图片），最大 10MB |
| 请求格式 | `multipart/form-data` |
| 后续 | 上传后触发 AI 解析 |

### 3.2 获取简历列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/resumes` |
| 认证 | 需要 |
| 说明 | 返回当前用户所有简历（按上传时间倒序） |

### 3.3 获取简历详情

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/resumes/{resume_id}` |
| 认证 | 需要 |
| 说明 | 返回简历详情，包括 AI 解析后的结构化内容 |

### 3.4 删除简历

| 项目 | 说明 |
|------|------|
| 方法 | `DELETE` |
| 路径 | `/api/v1/resumes/{resume_id}` |
| 认证 | 需要 |
| 说明 | 删除指定简历及其文件 |

### 3.5 AI 解析简历

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/resumes/{resume_id}/parse` |
| 认证 | 需要 |
| 说明 | 触发 AI 解析简历内容，提取姓名、技能、工作经历、教育背景等结构化信息 |

---

## 4. 面试管理模块

### 4.1 创建面试

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/interviews` |
| 认证 | 需要 |
| 说明 | 基于简历ID创建一次面试，触发 AI 生成题目 |
| 请求体 | `{ resume_id, type: "full" | "quick" }` |

### 4.2 获取面试列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/interviews` |
| 认证 | 需要 |
| 说明 | 返回当前用户所有面试记录（按时间倒序），含分页 |

### 4.3 获取面试详情

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/interviews/{interview_id}` |
| 认证 | 需要 |
| 说明 | 返回面试详情，包括题目列表、当前进度 |

### 4.4 AI 生成面试题目

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/interviews/{interview_id}/questions` |
| 认证 | 需要 |
| 说明 | 根据简历内容，AI 生成个性化面试题目（含追问） |

### 4.5 提交答案

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/interviews/{interview_id}/questions/{question_id}/answer` |
| 认证 | 需要 |
| 说明 | 提交单题答案（文本或语音转文字），触发 AI 评分 |
| 请求体 | `{ answer: string }` |

### 4.6 完成面试

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/interviews/{interview_id}/complete` |
| 认证 | 需要 |
| 说明 | 结束面试，AI 生成综合报告（总分、优势、劣势、建议） |

### 4.7 获取面试报告

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/interviews/{interview_id}/report` |
| 认证 | 需要 |
| 说明 | 返回面试报告详情（总分、评语、逐题详情） |

---

## 5. 社区帖子模块

### 5.1 获取帖子列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/posts` |
| 认证 | 需要 |
| 说明 | 获取帖子列表，支持分页、排序、筛选 |
| 参数 | `?sort=hot|latest&tag=面试经验&page=1&page_size=20` |

### 5.2 获取帖子详情

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/posts/{post_id}` |
| 认证 | 需要 |
| 说明 | 返回帖子完整内容，同时增加浏览计数 |

### 5.3 创建帖子

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/posts` |
| 认证 | 需要 |
| 说明 | 发布新帖子 |
| 请求体 | `{ title, content, tags, images }` |

### 5.4 删除帖子

| 项目 | 说明 |
|------|------|
| 方法 | `DELETE` |
| 路径 | `/api/v1/posts/{post_id}` |
| 认证 | 需要 |
| 说明 | 删除帖子（仅作者可操作） |

### 5.5 点赞/取消点赞帖子

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/posts/{post_id}/like` |
| 认证 | 需要 |
| 说明 | 切换点赞状态，幂等 |

### 5.6 获取帖子评论

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/posts/{post_id}/comments` |
| 认证 | 需要 |
| 说明 | 获取帖子评论列表，支持分页 |

### 5.7 发表评论

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/posts/{post_id}/comments` |
| 认证 | 需要 |
| 说明 | 对帖子发表评论 |
| 请求体 | `{ content }` |

### 5.8 删除评论

| 项目 | 说明 |
|------|------|
| 方法 | `DELETE` |
| 路径 | `/api/v1/comments/{comment_id}` |
| 认证 | 需要 |
| 说明 | 删除评论（仅作者可操作） |

### 5.9 点赞评论

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/comments/{comment_id}/like` |
| 认证 | 需要 |
| 说明 | 切换评论点赞状态 |

### 5.10 关注动态流

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/feed` |
| 认证 | 需要 |
| 说明 | 获取关注用户发布的帖子（Feed流），支持分页和热门筛选 |

---

## 6. 社交关注模块

### 6.1 关注/取消关注

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/users/{user_id}/follow` |
| 认证 | 需要 |
| 说明 | 切换关注状态，幂等。关注后自动更新双方的关注数/粉丝数 |

### 6.2 获取关注列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/users/me/following` |
| 认证 | 需要 |
| 说明 | 获取当前用户关注的人列表，支持分页 |

### 6.3 获取粉丝列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/users/me/followers` |
| 认证 | 需要 |
| 说明 | 获取当前用户粉丝列表，支持分页 |

### 6.4 获取指定用户的关注列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/users/{user_id}/following` |
| 认证 | 需要 |
| 说明 | 获取指定用户的关注列表 |

### 6.5 获取指定用户的粉丝列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/users/{user_id}/followers` |
| 认证 | 需要 |
| 说明 | 获取指定用户的粉丝列表 |

---

## 7. 消息通知模块

### 7.1 获取消息列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/messages` |
| 认证 | 需要 |
| 说明 | 获取消息列表，支持按类型筛选，分页 |
| 参数 | `?type=system|like|comment|follow|dm&page=1&page_size=20` |

### 7.2 获取消息详情

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/messages/{message_id}` |
| 认证 | 需要 |
| 说明 | 获取消息详情，自动标记为已读 |

### 7.3 删除消息

| 项目 | 说明 |
|------|------|
| 方法 | `DELETE` |
| 路径 | `/api/v1/messages/{message_id}` |
| 认证 | 需要 |
| 说明 | 删除指定消息 |

### 7.4 标记全部已读

| 项目 | 说明 |
|------|------|
| 方法 | `PUT` |
| 路径 | `/api/v1/messages/read-all` |
| 认证 | 需要 |
| 说明 | 将所有消息标记为已读 |

### 7.5 获取未读消息数

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/messages/unread-count` |
| 认证 | 需要 |
| 说明 | 返回未读消息总数 |

---

## 8. 私信聊天模块

### 8.1 获取会话列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/conversations` |
| 认证 | 需要 |
| 说明 | 返回当前用户所有私信会话列表（按最后消息时间倒序），含对方用户信息和最后消息预览 |

### 8.2 获取会话消息

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/conversations/{conversation_id}/messages` |
| 认证 | 需要 |
| 说明 | 获取指定会话的消息列表，支持分页，自动标记为已读 |

### 8.3 发送私信

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/conversations/{conversation_id}/messages` |
| 认证 | 需要 |
| 说明 | 发送私信消息 |
| 请求体 | `{ content }` |

### 8.4 创建/获取会话

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/conversations` |
| 认证 | 需要 |
| 说明 | 与指定用户创建或获取已有的私信会话 |
| 请求体 | `{ user_id }` |

---

## 9. 收藏功能模块

### 9.1 获取收藏列表

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/favorites` |
| 认证 | 需要 |
| 说明 | 获取当前用户收藏的帖子列表，支持分页 |

### 9.2 收藏帖子

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/favorites/{post_id}` |
| 认证 | 需要 |
| 说明 | 收藏帖子，幂等 |

### 9.3 取消收藏

| 项目 | 说明 |
|------|------|
| 方法 | `DELETE` |
| 路径 | `/api/v1/favorites/{post_id}` |
| 认证 | 需要 |
| 说明 | 取消收藏帖子 |

---

## 10. 用户设置模块

### 10.1 获取设置

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/api/v1/settings` |
| 认证 | 需要 |
| 说明 | 获取当前用户设置（通知偏好、隐私等） |

### 10.2 更新设置

| 项目 | 说明 |
|------|------|
| 方法 | `PUT` |
| 路径 | `/api/v1/settings` |
| 认证 | 需要 |
| 说明 | 更新用户设置 |
| 请求体 | `{ email_notify, push_notify, sound_enabled, public_profile, language }` |

---

## 11. 文件上传模块

### 11.1 上传头像

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/upload/avatar` |
| 认证 | 需要 |
| 说明 | 上传用户头像图片，限定格式和大小 |
| 请求格式 | `multipart/form-data` |

### 11.2 上传帖子图片

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/api/v1/upload/image` |
| 认证 | 需要 |
| 说明 | 上传帖子中的图片，返回图片URL |
| 请求格式 | `multipart/form-data` |

---

## 12. AI 服务集成模块

### 12.1 简历解析服务

- **功能**：从上传的简历文件（PDF/Word/图片）中提取结构化信息
- **输出**：姓名、技能列表、工作经历（公司/职位/时长/描述）、教育背景（学校/学历/专业/年份）

### 12.2 面试题生成服务

- **功能**：根据简历内容和技术栈，生成个性化面试题目
- **输出**：包含技术题、项目题、行为题，以及针对性的追问
- **要求**：题目覆盖技术基础、项目经验、综合素质、架构设计等维度

### 12.3 答案评分服务

- **功能**：对用户提交的面试答案进行评分（1-5分）
- **输出**：分数 + 评语（指出优点和不足）
- **要求**：从技术深度、表达逻辑、完整性等维度评估

### 12.4 面试报告生成服务

- **功能**：综合所有题目的作答情况，生成面试报告
- **输出**：总分、综合评语、优势列表、劣势列表、改进建议

### 12.5 实现建议

- 建议封装统一的 AI 服务接口层（如 `app/services/ai_service.py`）
- 支持接入 OpenAI / Claude / 国内大模型等
- 使用异步调用，避免阻塞请求
- 实现重试和降级策略

---

## 13. API 路由汇总

### 13.1 路由注册清单

```
api_v1_router (prefix="/api/v1")
├── auth                   (已实现) GitHub OAuth 认证
├── users                  (待开发) 用户管理
├── resumes                (待开发) 简历管理
├── interviews             (待开发) 面试管理
├── posts                  (待开发) 社区帖子
├── comments               (待开发) 帖子评论
├── messages               (待开发) 消息通知
├── conversations          (待开发) 私信聊天
├── favorites              (待开发) 收藏功能
├── settings               (待开发) 用户设置
├── upload                 (待开发) 文件上传
└── feed                   (待开发) 关注动态流
```

### 13.2 开发优先级建议

| 优先级 | 模块 | 原因 |
|--------|------|------|
| P0 | 用户管理 + 简历管理 + AI 服务 | 核心业务闭环：上传简历 → AI 出题 → 面试 → 报告 |
| P1 | 面试管理 | 核心功能，依赖简历和 AI 服务 |
| P2 | 社区帖子 + 评论 | 社区互动功能 |
| P3 | 社交关注 + 收藏 | 用户粘性功能 |
| P4 | 消息通知 + 私信 | 用户触达和私密交流 |
| P5 | 文件上传 + 用户设置 | 辅助功能 |

### 13.3 文件结构建议

```
api_server/app/
├── api/v1/
│   ├── __init__.py              (路由聚合)
│   └── controllers/
│       ├── auth.py              (已实现)
│       ├── users.py             (待开发)
│       ├── resumes.py           (待开发)
│       ├── interviews.py        (待开发)
│       ├── posts.py             (待开发)
│       ├── comments.py          (待开发)
│       ├── messages.py          (待开发)
│       ├── conversations.py     (待开发)
│       ├── favorites.py         (待开发)
│       ├── settings.py          (待开发)
│       ├── upload.py            (待开发)
│       └── feed.py              (待开发)
├── models/
│   ├── user.py                  (已实现)
│   ├── user_auth.py             (已实现)
│   ├── resume.py                (待开发)
│   ├── interview.py             (待开发)
│   ├── post.py                  (待开发)
│   ├── message.py               (待开发)
│   ├── conversation.py          (待开发)
│   └── user_settings.py         (待开发)
├── schemas/
│   ├── auth.py                  (已实现)
│   ├── user.py                  (待开发)
│   ├── resume.py                (待开发)
│   ├── interview.py             (待开发)
│   ├── post.py                  (待开发)
│   ├── message.py               (待开发)
│   └── conversation.py          (待开发)
├── services/
│   ├── auth_service.py          (已实现)
│   ├── github_oauth_service.py  (已实现)
│   ├── user_service.py          (待开发)
│   ├── resume_service.py        (待开发)
│   ├── interview_service.py     (待开发)
│   ├── post_service.py          (待开发)
│   ├── message_service.py       (待开发)
│   ├── conversation_service.py  (待开发)
│   └── ai_service.py            (待开发)
└── repositories/
    ├── user_repository.py       (已实现)
    ├── resume_repository.py     (待开发)
    ├── interview_repository.py  (待开发)
    ├── post_repository.py       (待开发)
    ├── message_repository.py    (待开发)
    └── conversation_repository.py (待开发)
```

---

> **共计待开发 API 接口**：约 40+ 个
> 
> **共计待新建数据库表**：12 张
> 
> **共计待新建 Python 模块**：约 30+ 个文件