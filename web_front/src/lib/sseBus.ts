/**
 * 全局共享 SSE 事件总线（单例连接）。
 *
 * 背景：浏览器对同一源（host:port）的 HTTP/1.1 连接上限为 6。此前
 * DashboardLayout 与 InterviewSessionPage 各自 new EventSource，每个
 * 标签页占用 2 条长连接——多标签页（如面试双开场景）叠加页面刷新的
 * 僵尸连接后，连接池耗尽，该源上所有 XHR 请求排队挂起，表现为
 * 「后端全局无响应」（实际后端正常）。
 *
 * 方案：模块级单例 EventSource，全页签共享一条连接；组件通过
 * subscribeSSE 订阅事件、卸载时退订。断线由 EventSource 原生自动
 * 重连兜底（服务端断开后浏览器自动重连 /messages/stream）。
 */

import { buildSSEUrl } from '@/lib/api/messages';

/** SSE 事件处理器（入参为已解析的事件 JSON 对象） */
export type SSEHandler = (data: Record<string, unknown>) => void;

/** 当前订阅者集合 */
const handlers = new Set<SSEHandler>();

/** SSE 连接状态（供 UI 展示"实时通道"指示，诊断"是否走 SSE"） */
export type SSEStatus = 'connecting' | 'open' | 'closed';
const statusHandlers = new Set<(s: SSEStatus) => void>();
let lastStatus: SSEStatus = 'closed';

/** 通知所有状态订阅者（去重，避免重复渲染） */
function emitStatus(status: SSEStatus): void {
  if (status === lastStatus) return;
  lastStatus = status;
  statusHandlers.forEach((cb) => {
    try {
      cb(status);
    } catch {
      // 单个订阅者异常不影响其他订阅者
    }
  });
}

/** 查询当前 SSE 连接状态（首次调用前为 closed） */
export function getSSEStatus(): SSEStatus {
  const s = source;
  if (!s) return 'closed';
  return s.readyState === EventSource.OPEN ? 'open' : s.readyState === EventSource.CONNECTING ? 'connecting' : 'closed';
}

/** 订阅 SSE 连接状态变化（实时通道指示用），返回退订函数 */
export function subscribeSSEStatus(cb: (s: SSEStatus) => void): () => void {
  statusHandlers.add(cb);
  cb(lastStatus);
  return () => {
    statusHandlers.delete(cb);
  };
}

/** 单例 EventSource（首个订阅者出现时懒建立） */
let source: EventSource | null = null;

/**
 * 分发一条 SSE 事件数据给所有订阅者，并确保顶层带 kind（事件类型名）。
 *
 * 后端的 SSE 使用命名事件（event: message / event: unread_count 等），
 * EventSource 会将它们分别触发 addEventListener 对应类型，而非 onmessage。
 * 且后端在发送 unread_count 等命名事件时，data 内并未冗余携带顶层 kind 字段
 * （在 messages.py 中剥离了控制字段）。因此这里依据事件类型把 kind 注入 data，
 * 使下游各订阅者统一按 data.kind 判断事件类型，无需感知具体的命名事件。
 *
 * @param eventName SSE 事件类型名（也会作为 kind 注入）。
 * @param rawData SSE 事件中的 data 字段（JSON 字符串）。
 */
function dispatchRaw(eventName: string, rawData: string | null): void {
  if (!rawData) return;
  let data: unknown;
  try {
    data = JSON.parse(rawData);
  } catch {
    return;
  }
  if (!data || typeof data !== 'object') return;
  const payload = data as Record<string, unknown>;
  // 仅当 data 未自带 kind 时，用事件类型名补全（保证下游可统一按 kind 判断）
  if (!('kind' in payload)) {
    payload.kind = eventName;
  }
  handlers.forEach((handler) => {
    try {
      handler(payload);
    } catch {
      // 单个订阅者异常不影响其他订阅者
    }
  });
}

/** 确保共享连接已建立（若现有连接已断开则重建） */
function ensureConnection(): void {
  // 连接已打开 → 复用
  if (source && source.readyState === EventSource.OPEN) return;
  // 连接存在但未打开（CONNECTING / CLOSED）→ 关闭重建，确保用最新 Cookie
  if (source) {
    source.close();
    source = null;
  }
  try {
    // 跨域（前端5645 → 后端8000）必须携带HttpOnly Cookie，否则认证401
    source = new EventSource(buildSSEUrl(), { withCredentials: true });
    // 默认 message 事件 + 各命名事件（unread_count 等）统一交给 dispatchRaw
    source.onmessage = (event) => dispatchRaw('message', event.data);
    source.addEventListener('unread_count', (event) =>
      dispatchRaw('unread_count', (event as MessageEvent).data),
    );
    source.addEventListener('system_broadcast', (event) =>
      dispatchRaw('system_broadcast', (event as MessageEvent).data),
    );
    // 连接状态通知（"实时通道"指示）：open=已建立，error=断线重连中/失败
    source.onopen = () => emitStatus('open');
    source.onerror = () => {
      emitStatus(source?.readyState === EventSource.CONNECTING ? 'connecting' : 'closed');
    };
  } catch {
    source = null;
    emitStatus('closed');
  }
}

/**
 * 订阅共享 SSE 事件流（事件名 message 的所有事件均会分发）。
 *
 * @param handler 事件处理器，收到已解析的 JSON 对象（含 kind 等字段），
 *                由调用方自行过滤关心的事件类型。
 * @returns 退订函数（组件卸载时调用）。
 */
export function subscribeSSE(handler: SSEHandler): () => void {
  handlers.add(handler);
  ensureConnection();
  return () => {
    handlers.delete(handler);
    // 不主动断开连接：DashboardLayout 等常驻订阅者在会话期内复用同一连接；
    // 全部退订后保留连接可避免页面切换时的频繁建连与补偿查询开销
  };
}
