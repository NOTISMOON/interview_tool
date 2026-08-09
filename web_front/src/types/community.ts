export interface Post {
  id: string;
  authorId: string;
  authorName: string;
  authorAvatar?: string;
  title: string;
  content: string;
  tags: string[];
  likes: number;
  comments: number;
  views: number;
  createdAt: string;
  isLiked?: boolean;
}

export interface PostAuthor {
  id: string;
  nickname: string;
  avatar: string;
}

export interface CommunityPost {
  id: string;
  title: string;
  content: string;
  author: PostAuthor;
  tags: string[];
  likes: number;
  comments: number;
  views: number;
  isPinned: boolean;
  isHot: boolean;
  createdAt: string;
}

export interface PostComment {
  id: string;
  postId: string;
  authorId: string;
  authorName: string;
  authorAvatar?: string;
  content: string;
  likes: number;
  createdAt: string;
}

export interface CommunityState {
  posts: Post[];
  currentPost: Post | null;
  loading: boolean;
}