import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Tabs from 'antd/es/tabs';
import App from 'antd/es/app';
import Spin from 'antd/es/spin';
import Tooltip from 'antd/es/tooltip';
import Avatar from 'antd/es/avatar';
import {
  ArrowLeftOutlined,
  BellOutlined,
  LikeOutlined,
  CommentOutlined,
  TeamOutlined,
  MessageOutlined,
  CheckOutlined,
  FireOutlined,
  EyeOutlined,
  DeleteOutlined,
  EyeInvisibleOutlined,
} from '@/components/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

/** 格式化消息时间为相对时间 */
function formatMsgTime(dateStr: string): string {
  const d = dayjs(dateStr);
  if (!d.isValid()) return dateStr;
  const now = dayjs();
  if (now.diff(d, 'hour') < 24) return d.fromNow();
  if (now.diff(d, 'day') < 7) return d.format('dddd HH:mm');
  return d.format('M/D HH:mm');
}

import {
  getMessages,
  getUnreadCount,
  markMessageRead,
  markAllMessagesRead,
  deleteMessage,
} from '@/lib/api/messages';
import type { MessageResponse } from '@/lib/api/messages';
import {
  getChatConversations,
  hideChatConversation,
  deleteChatConversation,
  type ChatConversation,
} from '@/lib/api/chat';
import type { SystemMessage } from '@/types';
import { useMessageVersion } from '@/lib/messageVersion';
import { useAppStore } from '@/store';
import ContextMenu from '@/components/ContextMenu';
import {
  getCachedMessages,
  hasFullCache,
  setCachedMessages,
  mergeCachedMessages,
  updateCachedMessage,
  markAllCachedRead,
  removeCachedMessage,
} from '@/lib/messageCache';

/** 全量加载每页大小（后端cursor模式上限50） */
const PAGE_SIZE = 50;
/** 增量拉取每页大小（后端since_id模式上限10） */
const DELTA_LIMIT = 10;
/** 循环翻页安全上限（防异常死循环） */
const MAX_PAGES = 20;

/** 将后端MessageResponse映射为前端SystemMessage */
function mapMessage(m: MessageResponse): SystemMessage {
  const typeMap: Record<string, SystemMessage['type']> = {
    system: 'system',
    like: 'like',
    comment: 'comment',
    follow: 'follow',
    dm: 'dm',
    interview: 'interview',
    follow_post: 'follow_post',
  };
  return {
    id: String(m.id),
    type: typeMap[m.type_name] || 'system',
    title: m.title,
    content: m.content,
    fromUser: m.from_user
      ? { id: String(m.from_user.id), name: m.from_user.nickname, avatar: m.from_user.avatar || '' }
      : undefined,
    createdAt: m.created_at,
    isRead: m.is_read,
    relatedId: m.related?.id !== undefined && m.related?.id !== null ? String(m.related.id) : undefined,
    relatedType: m.related?.type,
  };
}

const MessagesPage = () => {
  const navigate = useNavigate();
  const { message: msg, modal } = App.useApp();
  const { user } = useAppStore();
  const { revision: msgRevision } = useMessageVersion();
  const [activeTab, setActiveTab] = useState('all');
  const [messages, setMessages] = useState<SystemMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const [markingAll, setMarkingAll] = useState(false);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  /** 右键浮窗状态（通知消息或私信会话） */
  const [menu, setMenu] = useState<
    | { kind: 'message'; item: SystemMessage; x: number; y: number }
    | { kind: 'conversation'; item: ChatConversation; x: number; y: number }
    | null
  >(null);
  const conversationsTotalUnread = conversations.reduce((sum, c) => sum + (c.unread || 0), 0);

  /** 全量加载：循环cursor翻页，直到取完所有历史消息 */
  const loadAllMessages = useCallback(async (): Promise<SystemMessage[]> => {
    const all: SystemMessage[] = [];
    let cursor = 0;
    for (let i = 0; i < MAX_PAGES; i++) {
      const res = await getMessages({ cursor: cursor || undefined, size: PAGE_SIZE });
      all.push(...res.items.map(mapMessage));
      if (res.next_cursor === null || res.items.length === 0) break;
      cursor = res.next_cursor;
    }
    return all;
  }, []);

  /** 增量加载：从缓存最后一条消息之后拉取新消息（未满页说明增量已取完） */
  const loadDeltaMessages = useCallback(async (sinceId: number): Promise<SystemMessage[]> => {
    const delta: SystemMessage[] = [];
    let currentSince = sinceId;
    for (let i = 0; i < MAX_PAGES; i++) {
      const res = await getMessages({ since_id: currentSince, limit: DELTA_LIMIT });
      const items = res.items.map(mapMessage);
      delta.push(...items);
      if (items.length < DELTA_LIMIT) break;
      currentSince = Math.max(...res.items.map((m) => m.id));
    }
    return delta;
  }, []);

  /** 加载未读计数 */
  const loadUnreadCount = useCallback(async () => {
    try {
      const res = await getUnreadCount();
      setUnreadCount(res.total);
    } catch {
      // 静默失败
    }
  }, []);

  /** 进入页面/版本号变更：首次全量加载建缓存，之后增量拉取合并（不闪烁） */
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    const bootstrap = async (isInit: boolean) => {
      if (isInit) setLoading(true);
      try {
        if (hasFullCache(user.id)) {
          // 已有全量缓存：先展示缓存，再增量拉取合并（版本号变更时无 loading）
          if (isInit) setMessages(getCachedMessages(user.id));
          const cached = getCachedMessages(user.id);
          const lastId = cached.length > 0 ? Math.max(...cached.map((m) => Number(m.id))) : 0;
          const delta = await loadDeltaMessages(lastId);
          if (!cancelled && delta.length > 0) {
            mergeCachedMessages(user.id, delta);
            setMessages(getCachedMessages(user.id));
          }
        } else {
          // 首次进入且无缓存：全量加载并写入缓存
          const all = await loadAllMessages();
          if (!cancelled) {
            setCachedMessages(user.id, all);
            setMessages(getCachedMessages(user.id));
          }
        }
      } catch {
        if (isInit) msg.error('加载消息失败');
      } finally {
        if (isInit && !cancelled) setLoading(false);
      }
    };
    bootstrap(true);
    loadUnreadCount();
    // 加载私信会话列表（独立于通知消息）
    getChatConversations()
      .then((res) => {
        if (!cancelled) setConversations(res.items);
      })
      .catch(() => {
        // 会话加载失败静默
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, loadAllMessages, loadDeltaMessages, loadUnreadCount, msg]);

  // 版本号变化（收到新通知）：仅增量合并，不显示 loading / 不整页重载
  useEffect(() => {
    if (!user || !hasFullCache(user.id)) return;
    let cancelled = false;
    const refresh = async () => {
      const cached = getCachedMessages(user.id);
      const lastId = cached.length > 0 ? Math.max(...cached.map((m) => Number(m.id))) : 0;
      try {
        const delta = await loadDeltaMessages(lastId);
        if (!cancelled && delta.length > 0) {
          mergeCachedMessages(user.id, delta);
          setMessages(getCachedMessages(user.id));
        }
      } catch {
        // 增量失败静默，下次版本变化再补
      }
    };
    refresh();
    // 刷新未读计数与私信会话列表（局部，不含消息列表）
    loadUnreadCount();
    getChatConversations()
      .then((res) => {
        if (!cancelled) setConversations(res.items);
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [msgRevision, user, loadDeltaMessages, loadUnreadCount, getChatConversations]);

  /** 标签筛选：全部消息已在缓存中，纯前端过滤，无需请求 */
  const filteredMessages =
    activeTab === 'all' ? messages : messages.filter((m) => m.type === activeTab);

  /** 点击消息 */
  const handleMessageClick = async (msgItem: SystemMessage) => {
    if (!msgItem.isRead && user) {
      try {
        await markMessageRead(Number(msgItem.id));
        updateCachedMessage(user.id, msgItem.id, { isRead: true });
        setMessages((prev) =>
          prev.map((m) => (m.id === msgItem.id ? { ...m, isRead: true } : m)),
        );
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch {
        // 标记已读失败不阻塞导航
      }
    }
    if (msgItem.type === 'dm') {
      navigate(`/dashboard/messages/chat/${msgItem.fromUser?.id || 'u3'}`);
    } else {
      // 其余类型（含 interview 题目生成/报告就绪）统一进入消息详情页，
      // 详情页按关联类型提供"去面试 / 查看报告"入口（避免列表直接跳转错位）
      navigate(`/dashboard/messages/${msgItem.id}`);
    }
  };

  /** 全部标为已读 */
  const handleMarkAllRead = async () => {
    setMarkingAll(true);
    try {
      const res = await markAllMessagesRead();
      if (user) {
        markAllCachedRead(user.id);
        setMessages(getCachedMessages(user.id));
      }
      msg.success(`已标记 ${res.count} 条消息为已读`);
      setUnreadCount(0);
    } catch {
      msg.error('操作失败');
    } finally {
      setMarkingAll(false);
    }
  };

  /** 右键查看通知消息（与点击一致：标已读并跳转） */
  const handleMenuViewMessage = (msgItem: SystemMessage) => {
    void handleMessageClick(msgItem);
  };

  /** 右键删除通知消息（同步移除缓存与列表） */
  const handleDeleteMessage = async (msgItem: SystemMessage) => {
    try {
      await deleteMessage(Number(msgItem.id));
      if (user) {
        removeCachedMessage(user.id, msgItem.id);
        setMessages(getCachedMessages(user.id));
      }
      if (!msgItem.isRead) setUnreadCount((prev) => Math.max(0, prev - 1));
      msg.success('已删除');
    } catch {
      msg.error('删除失败');
    }
  };

  /** 右键隐藏私信会话 */
  const handleHideConversation = async (conv: ChatConversation) => {
    try {
      await hideChatConversation(conv.id);
      setConversations((prev) => prev.filter((c) => c.id !== conv.id));
      msg.success('已隐藏会话');
    } catch {
      msg.error('操作失败');
    }
  };

  /** 右键删除私信会话（删除历史消息 + 隐藏，仅对当前用户生效） */
  const handleDeleteConversation = (conv: ChatConversation) => {
    modal.confirm({
      title: '删除会话',
      content: `将删除与「${conv.peer?.nickname || `用户${conv.peer?.id}`}」的历史消息并隐藏该会话（仅对您本人生效，对方记录不受影响）。确定删除？`,
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteChatConversation(conv.id);
          setConversations((prev) => prev.filter((c) => c.id !== conv.id));
          msg.success('已删除会话');
        } catch {
          msg.error('操作失败');
        }
      },
    });
  };

  const getIcon = (type: string) => {
    switch (type) {
      case 'system': return <BellOutlined className="text-[#D9A441]" />;
      case 'like': return <LikeOutlined className="text-[#F53535]" />;
      case 'comment': return <CommentOutlined className="text-[#00B578]" />;
      case 'follow': return <TeamOutlined className="text-[#232529]" />;
      case 'dm': return <MessageOutlined className="text-[#D9A441]" />;
      case 'follow_post': return <FireOutlined className="text-[#D9A441]" />;
      default: return <BellOutlined className="text-[#999999]" />;
    }
  };

  const getIconBg = (type: string) => {
    switch (type) {
      case 'system': return 'bg-[#F7EBD3]';
      case 'like': return 'bg-[#FDECEC]';
      case 'comment': return 'bg-[#F7EBD3]';
      case 'follow': return 'bg-[#F7F8FA]';
      case 'dm': return 'bg-[#F7EBD3]';
      case 'follow_post': return 'bg-[#F7EBD3]';
      default: return 'bg-[#F7F8FA]';
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate('/dashboard')}
            className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-xl font-bold text-[#232529]">消息中心</h1>
          {unreadCount > 0 && <span className="tag tag-flame">{unreadCount} 条未读</span>}
          {unreadCount > 0 && (
            <Tooltip title="全部标为已读">
              <button
                onClick={handleMarkAllRead}
                disabled={markingAll}
                className="ml-auto w-8 h-8 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#00B578] hover:border-[#00B578] transition-colors"
              >
                <CheckOutlined />
              </button>
            </Tooltip>
          )}
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          className="mb-4"
          items={[
            { key: 'all', label: '全部' },
            { key: 'system', label: '系统' },
            { key: 'like', label: '点赞' },
            { key: 'comment', label: '评论' },
            { key: 'follow', label: '关注' },
            { key: 'follow_post', label: '关注动态' },
            { key: 'dm', label: '私信' },
          ].map((tab) => ({ key: tab.key, label: <span className="text-sm">{tab.label}</span> }))}
        />

        {conversations.length > 0 && (
          <div className="mb-4">
            <div className="flex items-center gap-2 mb-2">
              <MessageOutlined className="text-[#D9A441]" />
              <span className="text-sm font-semibold text-[#232529]">私信</span>
              {conversationsTotalUnread > 0 && (
                <span className="tag tag-flame text-xs">{conversationsTotalUnread}</span>
              )}
            </div>
            <div className="bg-white border border-[#E8E8E8] rounded-xl divide-y divide-[#F2F3F5] overflow-hidden">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-[#F7F8FA] transition-colors cursor-pointer"
                  onClick={() => navigate(`/dashboard/messages/chat/${conv.peer?.id}`)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setMenu({ kind: 'conversation', item: conv, x: e.clientX, y: e.clientY });
                  }}
                >
                  <Avatar
                    size={40}
                    className="!bg-[#232529] flex-shrink-0 !text-sm"
                  >
                    {(conv.peer?.nickname || '?')[0]}
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-[#232529] truncate">
                        {conv.peer?.nickname || `用户${conv.peer?.id}`}
                      </span>
                      {conv.last_message_at && (
                        <span className="text-xs text-[#999999] flex-shrink-0">
                          {new Date(conv.last_message_at).toLocaleString('zh-CN', {
                            month: 'numeric',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <p className="text-xs text-[#666666] truncate flex-1 mr-2">
                        {conv.last_message || '暂无消息'}
                      </p>
                      {conv.unread > 0 && (
                        <span className="w-5 h-5 rounded-full bg-[#D9A441] text-white text-[10px] font-semibold flex items-center justify-center flex-shrink-0">
                          {conv.unread > 99 ? '99+' : conv.unread}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Spin size="large" />
          </div>
        ) : filteredMessages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24">
            <div className="w-16 h-16 rounded-2xl bg-[#F7F8FA] flex items-center justify-center mb-4">
              <BellOutlined className="text-2xl text-[#999999]" />
            </div>
            <h3 className="text-base font-semibold text-[#232529] mb-2">暂无消息</h3>
            <p className="text-sm text-[#666666]">当你收到通知时，会显示在这里</p>
          </div>
        ) : (
          filteredMessages.map((msgItem) => (
            <div
              key={msgItem.id}
              className={`group bg-white border rounded-xl p-4 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 cursor-pointer relative overflow-hidden ${!msgItem.isRead ? 'border-[#D9A441]/30 bg-[#F7EBD3]/30' : 'border-[#E8E8E8]'}`}
              onClick={() => handleMessageClick(msgItem)}
              onContextMenu={(e) => {
                e.preventDefault();
                setMenu({ kind: 'message', item: msgItem, x: e.clientX, y: e.clientY });
              }}
            >
              {!msgItem.isRead && <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-[#D9A441] rounded-full" />}
              <div className="flex items-start gap-3">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${getIconBg(msgItem.type)}`}>
                  {getIcon(msgItem.type)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className={`text-sm ${!msgItem.isRead ? 'font-semibold text-[#232529]' : 'font-medium text-[#666666]'}`}>
                      {msgItem.title}
                      {!msgItem.isRead && <span className="inline-block w-2 h-2 rounded-full bg-[#F53535] ml-2 align-middle animate-pulse" />}
                    </h4>
                    <span className="text-xs text-[#999999] flex-shrink-0 ml-3">{formatMsgTime(msgItem.createdAt)}</span>
                  </div>
                  <p className={`text-xs leading-relaxed line-clamp-2 ${!msgItem.isRead ? 'text-[#232529]' : 'text-[#666666]'}`}>{msgItem.content}</p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 右键浮窗：通知消息（查看/删除）、私信会话（查看/隐藏/删除） */}
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          items={
            menu.kind === 'message'
              ? [
                  {
                    key: 'view',
                    label: '查看',
                    icon: <EyeOutlined />,
                    onClick: () => handleMenuViewMessage(menu.item),
                  },
                  {
                    key: 'delete',
                    label: '删除',
                    icon: <DeleteOutlined />,
                    danger: true,
                    onClick: () => void handleDeleteMessage(menu.item),
                  },
                ]
              : [
                  {
                    key: 'view',
                    label: '查看',
                    icon: <EyeOutlined />,
                    onClick: () => navigate(`/dashboard/messages/chat/${menu.item.peer?.id}`),
                  },
                  {
                    key: 'hide',
                    label: '隐藏',
                    icon: <EyeInvisibleOutlined />,
                    onClick: () => void handleHideConversation(menu.item),
                  },
                  {
                    key: 'delete',
                    label: '删除',
                    icon: <DeleteOutlined />,
                    danger: true,
                    onClick: () => handleDeleteConversation(menu.item),
                  },
                ]
          }
        />
      )}
    </div>
  );
};

export default MessagesPage;
