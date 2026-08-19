/** 用户模块API客户端，对接后端 /api/v1/users 端点。 */

import request from '@/lib/request';

// ============================================================
// 后端响应类型（与后端 schemas/user.py 字段对齐）
// ============================================================

/** 个人信息响应（后端 UserProfileResponse） */
export interface UserProfileResponse {
  id: number;
  email: string | null;
  nickname: string;
  avatar: string | null;
  gender: number; // 0-未设置 1-男 2-女
  birthday: string | null; // ISO date
  bio: string;
  phone: string | null;
  location: string | null;
  profile_visibility: number; // 0-公开 1-仅关注者 2-仅自己
  following_count: number;
  followers_count: number;
  posts_count: number;
  created_at: string;
  updated_at: string;
}

/** 更新资料请求 */
export interface UserUpdateRequest {
  nickname?: string;
  avatar?: string;
  gender?: number;
  birthday?: string;
  bio?: string;
  phone?: string;
  location?: string;
}

/** 更新资料可见性请求 */
export interface ProfileVisibilityUpdateRequest {
  profile_visibility: number;
}

/** 他人公开资料响应 */
export interface UserPublicProfileResponse {
  id: number;
  nickname: string;
  avatar: string | null;
  bio: string;
  location: string | null;
  following_count: number;
  followers_count: number;
  posts_count: number;
  created_at: string;
}

/** 受限卡片响应 */
export interface UserCardResponse {
  id: number;
  nickname: string;
  avatar: string | null;
}

/** 关注/粉丝列表项 */
export interface FollowItemResponse {
  id: number;
  nickname: string;
  avatar: string | null;
  bio: string;
  location: string | null;
  followed_at: string;
  is_following: boolean;
  is_mutual: boolean;
}

/** 关注/粉丝列表分页响应 */
export interface FollowListResponse {
  items: FollowItemResponse[];
  next_cursor: number | null;
  following_count: number;
  followers_count: number;
  restricted: boolean;
}

// ============================================================
// API 函数
// ============================================================

/** 获取当前用户完整资料 */
export async function getMyProfile(): Promise<UserProfileResponse> {
  const { data } = await request.get<UserProfileResponse>('/users/me');
  return data;
}

/** 更新当前用户资料 */
export async function updateMyProfile(body: UserUpdateRequest): Promise<UserProfileResponse> {
  const { data } = await request.put<UserProfileResponse>('/users/me', body);
  return data;
}

/** 更新当前用户资料可见性 */
export async function updateProfileVisibility(body: ProfileVisibilityUpdateRequest): Promise<UserProfileResponse> {
  const { data } = await request.put<UserProfileResponse>('/users/me/profile-visibility', body);
  return data;
}

/** 获取我的关注列表 */
export async function getMyFollowing(cursor?: number, pageSize = 20): Promise<FollowListResponse> {
  const { data } = await request.get<FollowListResponse>('/users/me/following', {
    params: { cursor, page_size: pageSize },
  });
  return data;
}

/** 获取我的粉丝列表 */
export async function getMyFollowers(cursor?: number, pageSize = 20): Promise<FollowListResponse> {
  const { data } = await request.get<FollowListResponse>('/users/me/followers', {
    params: { cursor, page_size: pageSize },
  });
  return data;
}

/** 获取他人公开资料 */
export async function getUserPublicProfile(userId: number): Promise<UserPublicProfileResponse | UserCardResponse> {
  const { data } = await request.get<UserPublicProfileResponse | UserCardResponse>(`/users/${userId}`);
  return data;
}

/** 获取他人关注列表 */
export async function getUserFollowing(
  userId: number,
  cursor?: number,
  pageSize = 20,
): Promise<FollowListResponse> {
  const { data } = await request.get<FollowListResponse>(`/users/${userId}/following`, {
    params: { cursor, page_size: pageSize },
  });
  return data;
}

/** 获取他人粉丝列表 */
export async function getUserFollowers(
  userId: number,
  cursor?: number,
  pageSize = 20,
): Promise<FollowListResponse> {
  const { data } = await request.get<FollowListResponse>(`/users/${userId}/followers`, {
    params: { cursor, page_size: pageSize },
  });
  return data;
}

/** 关注用户 */
export async function followUser(userId: number): Promise<void> {
  await request.post(`/users/${userId}/follow`);
}

/** 取消关注用户 */
export async function unfollowUser(userId: number): Promise<void> {
  await request.delete(`/users/${userId}/follow`);
}

/** 注销账号 */
export async function deleteAccount(): Promise<{ message: string }> {
  const { data } = await request.delete<{ message: string }>('/users/me');
  return data;
}