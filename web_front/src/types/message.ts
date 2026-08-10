export type MessageType = 'system' | 'comment' | 'like' | 'follow' | 'interview' | 'dm';

export interface RelatedContent {
  type: 'post' | 'report' | 'interview' | 'user';
  id: string;
  title: string;
  summary?: string;
  coverImage?: string;
}

export interface Message {
  id: string;
  type: MessageType;
  title: string;
  content: string;
  fromUser?: {
    id: string;
    name: string;
    avatar?: string;
  };
  isRead: boolean;
  createdAt: string;
  link?: string;
  relatedId?: string;
  relatedContent?: RelatedContent;
  actionLabel?: string;
  actionLink?: string;
}

export interface SystemMessage {
  id: string;
  type: MessageType;
  title: string;
  content: string;
  isRead: boolean;
  createdAt: string;
  relatedId?: string;
  fromUser?: {
    id: string;
    name: string;
    avatar?: string;
  };
}

export interface DmConversation {
  id: string;
  withUser: {
    id: string;
    name: string;
    avatar?: string;
    isOnline?: boolean;
  };
  messages: DmMessage[];
  lastMessage: string;
  lastMessageAt: string;
}

export interface DmMessage {
  id: string;
  conversationId: string;
  fromUserId: string;
  content: string;
  createdAt: string;
}

export const MESSAGE_TYPE_LABEL: Record<MessageType, string> = {
  system: '系统通知',
  comment: '评论',
  like: '点赞',
  follow: '关注',
  interview: '面试',
  dm: '私信',
};