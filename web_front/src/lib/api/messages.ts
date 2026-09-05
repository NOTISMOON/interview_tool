/** 消息通知模块API客户端，对接后端 /api/v1/messages 端点。 */

import request from '@/lib/request';

// ============================================================
// 后端响应类型（与后端 schemas/message.py 字段对齐）
// ============================================================

/** 消息发送者简要信息 */
export interface FromUserInfo {
  id: number;
  nickname: string;
  avatar: string | null;
}

/** 关联实体简要信息 */
export interface RelatedInfo {
  id: number;
  type: number;
  type_name: string | null;
}

/** 消息响应模型 */
export interface MessageResponse {
  id: number;
  type: number;
  type_name: string;
  title: string;
  content: string; // 后端 alias "content_text" → 序列化 key "content"
  from_user: FromUserInfo | null;
  related: RelatedInfo | null;
  created_at: string;
  is_read: boolean;
}

/** 消息列表响应 */
export interface MessageListResponse {
  items: MessageResponse[];
  next_cursor: number | null;
  unread_total: number;
}

/** 未读计数响应 */
export interface UnreadCountResponse {
  total: number;
  by_type: Record<string, number>;
}

// ============================================================
// API 函数
// ============================================================

/** 查询消息列表（since_id增量优先，cursor翻页降级） */
export async function getMessages(params: {
  since_id?: number;
  limit?: number;
  cursor?: number;
  size?: number;
  type?: string;
}): Promise<MessageListResponse> {
  const { data } = await request.get<MessageListResponse>('/messages', { params });
  return data;
}

/** 获取未读计数 */
export async function getUnreadCount(): Promise<UnreadCountResponse> {
  const { data } = await request.get<UnreadCountResponse>('/messages/unread-count');
  return data;
}

/** 获取消息详情（访问即标记已读） */
export async function getMessageDetail(messageId: number): Promise<MessageResponse> {
  const { data } = await request.get<MessageResponse>(`/messages/${messageId}`);
  return data;
}

/** 单条标记已读 */
export async function markMessageRead(messageId: number): Promise<{ ok: boolean }> {
  const { data } = await request.put<{ ok: boolean }>(`/messages/${messageId}/read`);
  return data;
}

/** 全部标记已读 */
export async function markAllMessagesRead(): Promise<{ ok: boolean; count: number }> {
  const { data } = await request.put<{ ok: boolean; count: number }>('/messages/read-all');
  return data;
}

/** 删除单条通知 */
export async function deleteMessage(messageId: number): Promise<{ ok: boolean }> {
  const { data } = await request.delete<{ ok: boolean }>(`/messages/${messageId}`);
  return data;
}

/** 构建 SSE 流连接 URL（前端直接使用 EventSource，与原 API 同源） */
export function buildSSEUrl(sinceId?: number): string {
  const base = request.defaults.baseURL || '';
  const params = new URLSearchParams();
  if (sinceId !== undefined && sinceId !== null) {
    params.set('since_id', String(sinceId));
  }
  const qs = params.toString();
  return `${base}/messages/stream${qs ? `?${qs}` : ''}`;
}