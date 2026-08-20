/** 帖子作者信息（与后端 PostAuthor 对齐） */
export interface PostAuthor {
  id: number;
  nickname: string;
  avatar: string | null;
}

/** 帖子详情（与后端 PostResponse 对齐） */
export interface PostDetail {
  id: number;
  author: PostAuthor | null;
  title: string;
  content: string;
  tags: string[];
  likes_count: number;
  comments_count: number;
  views_count: number;
  is_pinned: boolean;
  is_hot: boolean;
  is_liked: boolean;
  is_favorited: boolean;
  created_at: string;
  updated_at: string;
}

/** 帖子列表项（与后端 PostListItem 对齐，比详情精简） */
export interface PostListItem {
  id: number;
  author: PostAuthor | null;
  title: string;
  content_preview: string;
  tags: string[];
  likes_count: number;
  comments_count: number;
  views_count: number;
  is_pinned: boolean;
  is_hot: boolean;
  is_liked: boolean;
  is_favorited: boolean;
  created_at: string;
}

/** 帖子列表分页响应 */
export interface PostListData {
  items: PostListItem[];
  next_cursor: number | null;
  total: number;
}

// ============================================================
// 兼容旧类型（逐步迁移中）
// ============================================================

/** @deprecated 使用 PostDetail 替代 */
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

/** @deprecated 使用 PostListItem 替代 */
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

/** 评论（与后端 CommentResponse 对齐） */
export interface PostComment {
  id: number;
  post_id: number;
  root_id: number | null;
  author: {
    id: number;
    nickname: string;
    avatar: string | null;
  } | null;
  reply_to: {
    id: number;
    nickname: string;
    avatar: string | null;
  } | null;
  content: string;
  likes_count: number;
  reply_count: number;
  is_liked: boolean;
  created_at: string;
  updated_at: string;
}

export interface CommunityState {
  posts: Post[];
  currentPost: Post | null;
  loading: boolean;
}