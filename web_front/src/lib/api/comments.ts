/** 评论模块API客户端，对接后端 /api/v1/posts/{post_id}/comments 端点。 */

import request from '@/lib/request';

// ============================================================
// 后端响应类型（与后端 schemas/comment.py 字段对齐）
// ============================================================

/** 评论作者信息 */
export interface CommentAuthorResponse {
  id: number;
  nickname: string;
  avatar: string | null;
}

/** 评论响应 */
export interface CommentResponse {
  id: number;
  post_id: number;
  root_id: number | null;
  author: CommentAuthorResponse | null;
  reply_to: CommentAuthorResponse | null;
  content: string;
  likes_count: number;
  reply_count: number;
  is_liked: boolean;
  created_at: string;
  updated_at: string;
}

/** 评论列表分页响应 */
export interface CommentListResponse {
  items: CommentResponse[];
  next_cursor: number | null;
  total: number;
}

// ============================================================
// 请求类型
// ============================================================

/** 创建评论请求 */
export interface CommentCreateRequest {
  post_id?: number;
  content: string;
  root_id?: number | null;
  reply_user_id?: number | null;
}

// ============================================================
// API 函数
// ============================================================

/** 创建评论（一级评论或回复） */
export async function createComment(postId: number, data: CommentCreateRequest): Promise<CommentResponse> {
  const { data: result } = await request.post<CommentResponse>(
    `/posts/${postId}/comments`,
    { ...data, post_id: postId },
  );
  return result;
}

/** 获取帖子评论列表 */
export async function listComments(
  postId: number,
  params: {
    cursor?: number;
    limit?: number;
    sort?: 'latest' | 'hot';
  } = {},
): Promise<CommentListResponse> {
  const { data } = await request.get<CommentListResponse>(`/posts/${postId}/comments`, { params });
  return data;
}

/** 获取某条一级评论的回复列表 */
export async function listReplies(
  commentId: number,
  params: {
    cursor?: number;
    limit?: number;
  } = {},
): Promise<CommentListResponse> {
  const { data } = await request.get<CommentListResponse>(`/comments/${commentId}/replies`, { params });
  return data;
}

/** 删除评论 */
export async function deleteComment(commentId: number): Promise<void> {
  await request.delete(`/posts/comments/${commentId}`);
}