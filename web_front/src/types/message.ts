export type MessageType = 'system' | 'comment' | 'like' | 'follow' | 'interview';

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
}

export const MESSAGE_TYPE_LABEL: Record<MessageType, string> = {
  system: '系统通知',
  comment: '评论',
  like: '点赞',
  follow: '关注',
  interview: '面试',
};