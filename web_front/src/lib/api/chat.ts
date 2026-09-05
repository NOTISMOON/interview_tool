/** 私信模块API客户端，对接后端 /api/v1/chat 端点（REST 读路径 + 类型定义）。 */

import request from '@/lib/request';

// ============================================================
// 响应类型（与后端 schemas/chat.py 对齐）
// ============================================================

/** 会话对方用户简要信息 */
export interface PeerInfo {
  id: number;
  nickname: string;
  avatar?: string | null;
}

/** 私信会话项 */
export interface ChatConversation {
  id: number;
  peer: PeerInfo | null;
  last_message: string | null;
  last_message_at: string | null;
  last_message_id: number | null;
  unread: number;
}

/** 会话列表响应 */
export interface ChatConversationListResponse {
  items: ChatConversation[];
}

/** 私信消息 */
export interface ChatMessage {
  id: number;
  conversation_id: number;
  from_user_id: number;
  receiver_id: number;
  content_type: number;
  content: string;
  seq: number;
  is_read: boolean;
  created_at: string;
}

/** 消息列表响应 */
export interface ChatMessageListResponse {
  items: ChatMessage[];
  next_cursor: number | null;
  unread_total: number;
}

/** 获取/创建会话响应 */
export interface CreateConversationResponse {
  id: number;
  created: boolean;
}

/** WS 发送回执 */
export interface WSSendAck {
  action: 'sent' | 'duplicate' | 'error';
  client_msg_id: string;
  conversation_id?: number;
  seq?: number;
  status?: string;
  error?: string;
}

/** WS 入站实时消息（对端推送到接收方） */
export interface WSNewMessage {
  action: 'new_message';
  conversation_id: number;
  from_user_id: number;
  client_msg_id: string;
  content: string;
  content_type: number;
  seq: number;
}

// ============================================================
// REST API
// ============================================================

// 私信接口统一超时：首建会话/历史拉取偶发较慢，全局默认 5s 不足，显式放宽到 15s
const CHAT_REQUEST_TIMEOUT = 15000;

/** 查询当前用户私信会话列表 */
export async function getChatConversations(): Promise<ChatConversationListResponse> {
  const { data } = await request.get<ChatConversationListResponse>('/chat/conversations', {
    timeout: CHAT_REQUEST_TIMEOUT,
  });
  return data;
}

/** 获取或创建与某用户的会话（首次创建走 DB 写路径，放宽超时避免误判失败） */
export async function createChatConversation(
  userId: number,
): Promise<CreateConversationResponse> {
  const { data } = await request.post<CreateConversationResponse>(
    '/chat/conversations',
    { user_id: userId },
    { timeout: CHAT_REQUEST_TIMEOUT },
  );
  return data;
}

/** 分页查询会话历史消息（cursor=0 取最新一页，并清未读） */
export async function getChatMessages(
  conversationId: number,
  cursor?: number,
  size = 30,
): Promise<ChatMessageListResponse> {
  const { data } = await request.get<ChatMessageListResponse>(
    `/chat/conversations/${conversationId}/messages`,
    { params: { cursor: cursor || 0, size }, timeout: CHAT_REQUEST_TIMEOUT },
  );
  return data;
}

/** 将会话标记为已读（清 DB 未读 + Redis 未读计数） */
export async function markChatConversationRead(
  conversationId: number,
): Promise<{ ok: boolean; count: number }> {
  const { data } = await request.put<{ ok: boolean; count: number }>(
    `/chat/conversations/${conversationId}/read`,
    { timeout: CHAT_REQUEST_TIMEOUT },
  );
  return data;
}

/** 隐藏私信会话（仅对当前用户生效，并清除该会话未读） */
export async function hideChatConversation(
  conversationId: number,
): Promise<{ ok: boolean }> {
  const { data } = await request.put<{ ok: boolean }>(
    `/chat/conversations/${conversationId}/hide`,
    { timeout: CHAT_REQUEST_TIMEOUT },
  );
  return data;
}

/** 删除私信会话（软删自己的历史消息 + 隐藏会话，仅影响当前用户） */
export async function deleteChatConversation(
  conversationId: number,
): Promise<{ ok: boolean }> {
  const { data } = await request.delete<{ ok: boolean }>(
    `/chat/conversations/${conversationId}`,
    { timeout: CHAT_REQUEST_TIMEOUT },
  );
  return data;
}

// ============================================================
// WebSocket 客户端
// ============================================================

const WS_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')
  .replace(/^http/, 'ws')
  .replace(/\/api\/v1$/, ''); // baseURL 已含 /api/v1，WS 路径需去掉避免重复前缀

/**
 * 建立私信 WebSocket 连接。
 *
 * 浏览器访问 http://localhost:8000 的 WS 时自动携带 HttpOnly Cookie（跨域。
 * 系统核心：连接 /api/v1/chat/ws 做实时收发。断线由调用方负责重连。
 *
 * @returns WebSocket 实例。
 */
export function connectChatWS(): WebSocket {
  return new WebSocket(`${WS_BASE}/api/v1/chat/ws`);
}

/** 构造 WS 发送消息体 */
export function buildSendPayload(
  conversationId: number,
  receiverId: number,
  clientMsgId: string,
  content: string,
): Record<string, unknown> {
  return {
    action: 'send',
    conversation_id: conversationId,
    receiver_id: receiverId,
    client_msg_id: clientMsgId,
    content,
    content_type: 1,
  };
}

/** 生成客户端消息幂等键（UUID，作为 client_msg_id） */
export function genClientMsgId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // 兜底：无 crypto API 时用随机串
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}