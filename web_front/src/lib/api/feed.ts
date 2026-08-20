/** Feed信息流API客户端，对接后端 /api/v1/feed 端点。 */

import request from '@/lib/request';
import type { PostListResponse } from './posts';

// ============================================================
// API 函数
// ============================================================

/** 获取当前用户个性化信息流（关注者帖子 + 热门推荐） */
export async function getFeed(params: {
  cursor?: number;
  limit?: number;
} = {}): Promise<PostListResponse> {
  const { data } = await request.get<PostListResponse>('/feed', { params });
  return data;
}