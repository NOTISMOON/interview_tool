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