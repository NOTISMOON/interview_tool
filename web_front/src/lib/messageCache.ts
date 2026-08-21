/** 消息中心前端缓存：首次全量加载后，后续进入页面仅拉取增量新消息并合并展示。
 *  模块级内存缓存（SPA会话内跨路由导航复用；刷新页面后自动重建全量；
 *  按用户ID隔离，切换账号自动失效）。
 */
import type { SystemMessage } from '@/types';

/** 缓存的消息列表（按id降序，最新在前） */
let cachedMessages: SystemMessage[] = [];
/** 缓存所属用户ID */
let cachedUserId: string | null = null;

/** 确保缓存归属当前用户，否则清空重建 */
function ensureOwner(userId: string): void {
  if (cachedUserId !== userId) {
    cachedMessages = [];
    cachedUserId = userId;
  }
}

/** 读取当前用户缓存列表（返回副本） */
export function getCachedMessages(userId: string): SystemMessage[] {
  ensureOwner(userId);
  return [...cachedMessages];
}

/** 缓存是否已有全量数据（空列表用户每次挂载都会重新全量拉取，开销一次请求） */
export function hasFullCache(userId: string): boolean {
  ensureOwner(userId);
  return cachedMessages.length > 0;
}

/** 整体覆写缓存（首次全量加载后写入，按id降序） */
export function setCachedMessages(userId: string, messages: SystemMessage[]): void {
  ensureOwner(userId);
  cachedMessages = [...messages].sort((a, b) => Number(b.id) - Number(a.id));
}

/** 合并增量新消息到缓存（按id去重、整体降序，新消息自然置顶） */
export function mergeCachedMessages(userId: string, newItems: SystemMessage[]): void {
  ensureOwner(userId);
  if (newItems.length === 0) return;
  const map = new Map(cachedMessages.map((m) => [m.id, m]));
  newItems.forEach((m) => map.set(m.id, m));
  cachedMessages = [...map.values()].sort((a, b) => Number(b.id) - Number(a.id));
}

/** 更新缓存中单条消息（如标记已读） */
export function updateCachedMessage(userId: string, id: string, patch: Partial<SystemMessage>): void {
  ensureOwner(userId);
  cachedMessages = cachedMessages.map((m) => (m.id === id ? { ...m, ...patch } : m));
}

/** 标记缓存中全部消息已读 */
export function markAllCachedRead(userId: string): void {
  ensureOwner(userId);
  cachedMessages = cachedMessages.map((m) => ({ ...m, isRead: true }));
}

/** 从缓存移除单条消息（删除消息后同步） */
export function removeCachedMessage(userId: string, id: string): void {
  ensureOwner(userId);
  cachedMessages = cachedMessages.filter((m) => m.id !== id);
}
