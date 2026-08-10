export interface User {
  id: string;
  email: string;
  nickname: string;
  avatar?: string;
  followingCount: number;
  followersCount: number;
  followingIds: string[];
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
  bio: string;
  isFollowing: boolean;
  isFollowedBy?: boolean;
  followingCount: number;
  followersCount: number;
  postsCount: number;
  posts: import('./community').CommunityPost[];
  activities: ActivityItem[];
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