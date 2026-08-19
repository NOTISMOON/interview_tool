/** 个人资料字段可见性设置（0-不可见 1-可见） */
export interface ProfileVisibility {
  gender: boolean;
  birthday: boolean;
  bio: boolean;
  location: boolean;
  phone: boolean;
}

export interface User {
  id: string;
  email: string;
  nickname: string;
  avatar?: string;
  gender?: 'male' | 'female' | 'other';
  birthday?: string;
  bio?: string;
  phone?: string;
  location?: string;
  followingCount: number;
  followersCount: number;
  followingIds: string[];
  /** 个人资料字段可见性设置 */
  profileVisibility: ProfileVisibility;
}

export interface UserBrief {
  id: string;
  nickname: string;
  avatar?: string;
  bio: string;
  isFollowing: boolean;
  isFollowedBy?: boolean;
}

export interface UserProfile {
  id: string;
  nickname: string;
  avatar?: string;
  gender?: 'male' | 'female' | 'other';
  birthday?: string;
  bio: string;
  phone?: string;
  location?: string;
  isFollowing: boolean;
  isFollowedBy?: boolean;
  followingCount: number;
  followersCount: number;
  postsCount: number;
  posts: import('./community').CommunityPost[];
  activities: ActivityItem[];
  /** 个人资料字段可见性设置 */
  profileVisibility?: ProfileVisibility;
}

export interface ActivityItem {
  id: string;
  type: 'like' | 'comment' | 'follow' | 'post';
  content: string;
  relatedId?: string;
  createdAt: string;
}

export interface LoginForm {
  email: string;
  password: string;
}

export interface RegisterForm {
  nickname: string;
  email: string;
  password: string;
  confirmPassword: string;
}