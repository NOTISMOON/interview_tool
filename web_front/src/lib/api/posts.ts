/** 帖子模块API客户端，对接后端 /api/v1/posts 端点。 */

import request from '@/lib/request';
import type { PostDetail, PostListData } from '@/types';

// ============================================================
// 请求类型
// ============================================================

/** 创建帖子请求 */
export interface PostCreateRequest {
  title: string;
  content: string;
  cover_url?: string;
  images?: string[];
  tags?: string[];
}

/** 更新帖子请求 */
export interface PostUpdateRequest {
  title?: string;
  content?: string;
  cover_url?: string;
  images?: string[];
  tags?: string[];
}

// ============================================================
// 响应类型（与后端 PostListResponse 对齐，前端已有 PostListData）
// ============================================================

/** 帖子列表分页响应 */
export type PostListResponse = PostListData;

/** 帖子详情响应 */
export type PostResponse = PostDetail;

// ============================================================
// API 函数
// ============================================================

/** 创建帖子 */
export async function createPost(data: PostCreateRequest): Promise<PostResponse> {
  const { data: result } = await request.post<PostResponse>('/posts/', data);
  return result;
}

/** 获取帖子详情 */
export async function getPostDetail(postId: number): Promise<PostResponse> {
  const { data } = await request.get<PostResponse>(`/posts/${postId}`);
  return data;
}

/** 获取帖子列表（游标分页） */
export async function listPosts(params: {
  author_id?: number;
  sort?: 'latest' | 'hot' | 'pinned';
  cursor?: number;
  limit?: number;
} = {}): Promise<PostListResponse> {
  const { data } = await request.get<PostListResponse>('/posts/', { params });
  return data;
}

/** 更新帖子 */
export async function updatePost(postId: number, data: PostUpdateRequest): Promise<PostResponse> {
  const { data: result } = await request.put<PostResponse>(`/posts/${postId}`, data);
  return result;
}

/** 删除帖子（软删除） */
export async function deletePost(postId: number): Promise<void> {
  await request.delete(`/posts/${postId}`);
}