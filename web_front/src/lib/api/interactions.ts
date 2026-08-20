/** 互动（点赞/收藏）API客户端，对接后端 /api/v1/posts 互动端点。 */

import request from '@/lib/request';
import type { PostListResponse } from './posts';

// ============================================================
// 响应类型
// ============================================================

/** 切换点赞响应 */
export interface ToggleLikeResponse {
  is_liked: boolean;
  likes_count: number;
}

/** 切换收藏响应 */
export interface ToggleFavoriteResponse {
  is_favorited: boolean;
}

// ============================================================
// API 函数
// ============================================================

/** 切换点赞状态（点赞/取消点赞） */
export async function toggleLike(postId: number): Promise<ToggleLikeResponse> {
  const { data } = await request.post<ToggleLikeResponse>(`/posts/${postId}/like`);
  return data;
}

/** 切换收藏状态（收藏/取消收藏） */
export async function toggleFavorite(postId: number): Promise<ToggleFavoriteResponse> {
  const { data } = await request.post<ToggleFavoriteResponse>(`/posts/${postId}/favorite`);
  return data;
}

/** 获取收藏列表 */
export async function listFavorites(params: {
  cursor?: number;
  limit?: number;
} = {}): Promise<PostListResponse> {
  const { data } = await request.get<PostListResponse>('/posts/favorites', { params });
  return data;
}