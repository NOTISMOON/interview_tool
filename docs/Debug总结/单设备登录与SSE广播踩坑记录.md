# 单设备登录与 SSE 广播踩坑记录

## 概述

多实例部署（双后端实例 + Nginx 负载均衡）下，实现单设备登录（顶号）功能，要求新设备登录后旧设备收到实时下线通知。

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.0 + Redis Pub/Sub
- 前端：React + Ant Design + EventSource (SSE)
- 部署：Docker Compose + Nginx (least_conn 负载均衡)

## 完整链路

```
新设备登录
  → GitHub OAuth 回调 → /auth/github/callback
  → create_auth_tokens() 签发双Token
  → 检查 Redis auth:active_jti:{user_id} 是否有旧 jti
  → 有旧 jti → 发布 session_kicked 到 Redis Pub/Sub 通道 notify:push:{user_id}
  → 所有实例的 SSE Manager 通过 psubscribe("notify:push:*") 收到消息
  → 各实例查本地 SSE 队列池，推送到目标用户的队列
  → SSE 流读取队列，发送事件到前端
  → sseBus.ts 分发事件给所有订阅者
  → DashboardLayout 的 handler 检查 jti，过滤自身事件
  → 旧设备弹出下线提示框 → 跳转登录页
```

## 踩坑记录

### 坑1：SSE 事件数据格式错误导致前端无法识别

**问题**：`session_kicked` 事件被 SSE 端点 `messages.py` 的 `else` 分支处理，`event_data.get("message", event_data)` 提取了纯字符串 `"账号已在其他设备登录"`，丢失了 `kind` 字段。前端 `sseBus.ts` 收到纯字符串后 `typeof data !== 'object'` 直接 return，不触发任何 handler。

**日志表现**：SSE 事件已下发（DEBUG），但前端无反应。

**修复**：`messages.py` 新增 `elif kind == "session_kicked"` 分支，透传整个 `event_data`。

**文件**：`api_server/app/api/v1/controllers/messages.py`

### 坑2：Pub/Sub 监听器因日志异常崩溃

**问题**：`sse_manager.py` 的 `_push_to_user` 方法中，`payload.get("message", {}).get("id")` 在 `message` 字段为字符串时（`session_kicked` 事件）抛 `AttributeError: 'str' object has no attribute 'get'`。该异常未被捕获，导致整个 Pub/Sub 监听器崩溃，进入 2~60 秒指数退避重连，期间所有消息丢失。

**日志表现**：`SSE Pub/Sub 监听异常，2秒后重连` + `AttributeError: 'str' object has no attribute 'get'`

**修复**：`sse_manager.py` 日志处加 `isinstance(payload.get("message"), dict)` 检查。

**文件**：`api_server/app/services/sse_manager.py`

### 坑3：Pub/Sub 监听器缺乏异常保护

**问题**：`_dispatch` 方法中的 `_push_to_user` 和 `_broadcast_to_all` 调用没有 try-except 保护。任何异常（如坑2）都会传播到 `_listen_loop`，导致监听器崩溃重启，重启期间丢失消息。

**日志表现**：同坑2，监听器反复崩溃重启。

**修复**：`_dispatch` 中两个调用都包上 `try/except Exception`，异常只记录日志不崩溃监听器。

**文件**：`api_server/app/services/sse_manager.py`

### 坑4：未登录时创建的 EventSource 连接失效后未重建

**问题**：`sseBus.ts` 的 `ensureConnection` 函数检查 `if (source) return;`。当 `MessageVersionProvider` 在首页/登录页（未认证）就创建了 EventSource，服务端返回 401 后连接关闭（`readyState = CLOSED`）。登录后 `subscribeSSE` 再次调用 `ensureConnection`，但 `source` 已存在（非 null），直接 return，**不会创建新连接**。旧连接处于 CLOSED 状态，无法接收任何事件。

**日志表现**：后端 `SSE Pub/Sub 收到 session_kicked` → `已分发到本地队列`，但前端收不到事件（EventSource 未连接）。

**修复**：`ensureConnection` 增加 `readyState` 检查，仅在 `OPEN` 状态时复用，否则关闭重建。

**文件**：`web_front/src/lib/sseBus.ts`

### 坑5：MessageVersionProvider 在全局层创建 SSE 连接

**问题**：`MessageVersionProvider` 包裹整个应用，检测到 `isLoggedIn=true` 后立即创建 EventSource。此时 `DashboardLayout` 尚未挂载（还在 `/callback` 页，未跳转 `/dashboard`），`session_kicked` 事件被 `MessageVersionProvider` 的 handler 消费了，但 `DashboardLayout` 的 handler 还没注册。等跳转到 `/dashboard` 后 handler 才注册，事件已经过去了。

**日志表现**：`SSE事件已下发`（DEBUG），但前端 `DashboardLayout` 的 handler 未收到。

**修复**：移除 `MessageVersionProvider` 的 SSE 订阅，由 `DashboardLayout` 统一管理 SSE 连接和事件处理。

**文件**：`web_front/src/lib/messageVersion.tsx`、`web_front/src/components/layout/DashboardLayout.tsx`

### 坑6：Token 刷新触发重复 session_kicked

**问题**：`refresh_tokens()` 内部调用了 `create_auth_tokens()`，而 `create_auth_tokens()` 在检测到旧 jti 存在时会发布 `session_kicked`。token 刷新时 `auth:active_jti:{user_id}` 刚被覆盖，`old_jti` 永远存在，导致每次页面刷新（自动续期 token）都发布一次 `session_kicked`，形成循环通知。

**日志表现**：`session_kicked 已推送` 出现多次，且前后设备互相触发。

**修复**：`create_auth_tokens` 增加 `publish_kick_event` 参数，`refresh_tokens` 传入 `False`，仅初次登录才触发下线通知。

**文件**：`api_server/app/services/auth_service.py`

### 坑7：前端 Volume 未更新导致旧代码运行

**问题**：Docker volume `interview_tool_frontend_dist` 已存在时，重建前端容器不会覆盖 volume 内容，nginx 一直喂旧的前端代码给浏览器，导致修复不生效。

**日志表现**：前端 build 成功，但浏览器加载的仍是旧 JS。

**修复**：`docker compose down` → `docker volume rm -f interview_tool_frontend_dist` → `docker compose up -d`，强制重建 volume。

### 坑8：GitHub OAuth 回调超时

**问题**：axios 默认 5 秒超时，GitHub OAuth 回调涉及 GitHub API 调用（exchange code + fetch user），可能超过 5 秒导致请求被取消，前端显示"GitHub 授权失败"。

**日志表现**：浏览器 Network 面板显示 callback 请求被 cancelled。

**修复**：`githubCallback` 请求的超时设为 30 秒。

**文件**：`web_front/src/lib/api/auth.ts`

### 坑9：新设备接收自身 session_kicked 事件

**问题**：`session_kicked` 通过 Redis Pub/Sub 广播给所有实例，新设备建立 SSE 连接后也会收到该事件，导致新设备自己弹出下线提示。

**日志表现**：两个设备都收到 `SSE事件已下发`。

**修复**：事件携带新设备的 `jti`，前端 `DashboardLayout` 中检查 `data.jti === localStorage.getItem('auth_jti')`，相同则跳过处理。

**注意**：旧设备（在 `auth_jti` 功能部署前登录的）`localStorage` 中没有 `auth_jti`，此时 `myJti` 为 null，`if (myJti && ...)` 为 false，事件正常触发下线提示，不受影响。

**文件**：`api_server/app/services/auth_service.py`、`web_front/src/components/layout/DashboardLayout.tsx`

## 旧设备未收到下线提示排查步骤

当旧设备未收到下线提示时，按以下顺序排查：

### 步骤1：确认事件已发布

```bash
docker compose logs --tail=200 backend-1 backend-2 | grep "session_kicked 已推送"
```

期望输出：`session_kicked 已推送 user_id=X receivers=Y`

- `receivers=0` → 两个实例的 SSE 监听器都没有运行（监听器全挂了）
- `receivers=1` → 只有一个实例的监听器在运行（另一个实例的监听器可能崩溃了）
- `receivers=2` → 正常，两个实例都收到了

### 步骤2：确认实例收到 Pub/Sub 消息

```bash
docker compose logs --tail=200 backend-1 backend-2 | grep "SSE Pub/Sub 收到 session_kicked"
```

期望：每个实例都输出一行 `SSE Pub/Sub 收到 session_kicked user_id=X`

- 缺少某个实例的输出 → 该实例的 Redis Pub/Sub 连接异常，检查 `SSE Pub/Sub 监听异常` 日志

### 步骤3：确认事件已分发到本地队列

```bash
docker compose logs --tail=200 backend-1 backend-2 | grep "session_kicked 已分发到本地队列"
```

期望：输出 `session_kicked 已分发到本地队列 user_id=X queues=Y`

- `queues=0` 或没有此日志 → 该实例上该用户的 SSE 队列不存在（用户未连接到此实例）
- `queues=1` → 正常，事件已推送到该用户的 SSE 队列

如果 `queues=0`，检查是否有 `session_kicked 目标用户不在本实例，跳过` 日志：
- 有该日志 → 用户的 SSE 连接在另一个实例上，这是正常的（跨实例由 Pub/Sub 保证投递到正确的实例）
- 无该日志 + 无 `已分发到本地队列` → 监听器可能未运行，检查步骤1

### 步骤4：确认事件已下发到前端

```bash
docker compose logs --tail=200 backend-1 backend-2 | grep "SSE事件已下发.*session_kicked"
```

期望：输出 `SSE事件已下发 user_id=X kind=session_kicked`

- 有该日志 → 后端已正常发送，问题在前端
- 无该日志 → SSE 流生成器未读取到队列消息（队列可能被其他协程消费了）

### 步骤5：前端排查

如果后端日志完整（事件已下发到前端），但前端未弹出提示，检查：

1. **浏览器控制台**：查看是否有 SSE 连接错误（EventSource 的 `onerror`）
2. **session_kicked 事件数据**：在 `DashboardLayout` 的 handler 开头加 `console.log('session_kicked', data)`，确认事件是否到达
3. **auth_jti 检查**：检查 `localStorage.getItem('auth_jti')` 的值和 `data.jti` 的值是否相同（如果相同说明是新设备自身的 jti，事件被正确跳过）
4. **浏览器缓存**：Ctrl+Shift+R 强制刷新，确保加载最新前端代码

### 步骤6：SSE 监听器健康检查

```bash
docker compose logs --tail=200 backend-1 backend-2 | grep "SSE Pub/Sub 监听"
```

期望输出（启动时）：
```
SSE Pub/Sub 监听已启动 channels=notify:push:*,notify:broadcast
```

不期望：
```
SSE Pub/Sub 监听异常，2秒后重连
```

如果看到 `监听异常`，检查前后是否有 `AttributeError` 或其他异常，修复后重启服务。

## auth_jti 兼容性说明

`auth_jti` 功能是在部署后新增的，旧设备（功能部署前登录的）的 `localStorage` 中没有 `auth_jti`。

前端 `DashboardLayout` 的 handler 中：
```typescript
const myJti = localStorage.getItem('auth_jti');
if (myJti && data.jti === myJti) {
    return;  // 跳过自身事件
}
```

- **旧设备（无 `auth_jti`）**：`myJti` 为 null，`if (myJti && ...)` 为 false，事件正常触发下线提示 ✓
- **新设备（有 `auth_jti`）**：`myJti` 为自身 jti，`data.jti` 为新登录设备的 jti，两者不同，事件正常触发下线提示 ✓
- **新设备接收自身事件**：`myJti` 与 `data.jti` 相同，事件被跳过 ✓

不需要额外兼容处理。

## 日志排查指南

### 关键日志点

| 日志 | 级别 | 位置 | 含义 |
|------|------|------|------|
| `session_kicked 已推送 user_id=X receivers=Y` | INFO | `auth_service.py` | 事件已发布，Y 个实例收到 |
| `session_kicked 推送无实例接收` | WARNING | `auth_service.py` | 无实例订阅推送通道（SSE 监听器全挂） |
| `SSE Pub/Sub 收到 session_kicked` | INFO | `sse_manager.py` | SSE 管理器收到 Pub/Sub 消息 |
| `session_kicked 目标用户不在本实例，跳过` | INFO | `sse_manager.py` | 该实例无该用户 SSE 连接 |
| `session_kicked 已分发到本地队列` | INFO | `sse_manager.py` | 事件已推送到用户 SSE 队列 |
| `SSE事件已下发 user_id=X kind=session_kicked` | DEBUG | `messages.py` | 事件已发送到前端 |
| `SSE Pub/Sub 监听异常` | ERROR | `sse_manager.py` | 监听器崩溃，消息丢失 |

### 排查命令

```bash
# 查看 session_kicked 完整链路
docker compose logs --tail=200 backend-1 backend-2 | grep "session_kicked"

# 查看 SSE 监听器状态
docker compose logs --tail=100 backend-1 backend-2 | grep "SSE Pub/Sub"

# 查看监听器异常
docker compose logs --tail=100 backend-1 backend-2 | grep "监听异常"
```

## 最终修复清单

| # | 文件 | 修改 |
|---|------|------|
| 1 | `api_server/app/api/v1/controllers/messages.py` | 新增 `session_kicked` 事件分支，透传完整数据 |
| 2 | `api_server/app/services/sse_manager.py` | 日志加 `isinstance` 检查，`_dispatch` 加 try-except，`_push_to_user` 加 session_kicked 专用日志 |
| 3 | `api_server/app/services/auth_service.py` | 新增 `publish_kick_event` 参数，刷新时不发通知；加 receivers 日志 |
| 4 | `web_front/src/lib/messageVersion.tsx` | 移除 SSE 订阅，由 DashboardLayout 统一管理 |
| 5 | `web_front/src/components/layout/DashboardLayout.tsx` | 统一处理 SSE 事件：bump 版本号 + jti 检查 |
| 6 | `web_front/src/lib/sseBus.ts` | `ensureConnection` 检查 `readyState`，断开时重建连接 |
| 7 | `web_front/src/lib/api/auth.ts` | callback 超时从 5s 改为 30s |
| 8 | `web_front/src/store/index.ts` | 登录后存储 `auth_jti`，退出时清除 |
| 9 | `web_front/src/lib/request.ts` | 401 拦截器清除 `auth_jti` |
| 10 | `api_server/app/schemas/auth.py` | `TokenResponse` 增加 `jti` 字段 |