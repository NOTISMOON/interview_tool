import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tabs, App, Spin, Tooltip } from 'antd';
import {
  ArrowLeftOutlined,
  BellOutlined,
  LikeOutlined,
  CommentOutlined,
  TeamOutlined,
  MessageOutlined,
  CheckOutlined,
} from '@ant-design/icons';
import { getMessages, getUnreadCount, markMessageRead, markAllMessagesRead } from '@/lib/api/messages';
import type { MessageResponse } from '@/lib/api/messages';
import type { SystemMessage } from '@/types';
import { useAppStore } from '@/store';
import {
  getCachedMessages,
  hasFullCache,
  setCachedMessages,
  mergeCachedMessages,
  updateCachedMessage,
  markAllCachedRead,
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
  };
}

const MessagesPage = () => {
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const { user } = useAppStore();
  const [activeTab, setActiveTab] = useState('all');
  const [messages, setMessages] = useState<SystemMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const [markingAll, setMarkingAll] = useState(false);

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

  /** 进入页面：有缓存则增量拉取合并，无缓存则全量加载建缓存 */
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    const bootstrap = async () => {
      setLoading(true);
      try {
        if (hasFullCache(user.id)) {
          // 已有全量缓存：先展示缓存，再拉取缓存之后的新消息合并
          setMessages(getCachedMessages(user.id));
          const cached = getCachedMessages(user.id);
          const lastId = Math.max(...cached.map((m) => Number(m.id)));
          const delta = await loadDeltaMessages(lastId);
          if (!cancelled && delta.length > 0) {
            mergeCachedMessages(user.id, delta);
            setMessages(getCachedMessages(user.id));
          }
        } else {
          // 首次进入：全量加载并写入缓存
          const all = await loadAllMessages();
          if (!cancelled) {
            setCachedMessages(user.id, all);
            setMessages(getCachedMessages(user.id));
          }
        }
      } catch {
        msg.error('加载消息失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    bootstrap();
    loadUnreadCount();
    return () => { cancelled = true; };
  }, [user, loadAllMessages, loadDeltaMessages, loadUnreadCount, msg]);

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

  const getIcon = (type: string) => {
    switch (type) {
      case 'system': return <BellOutlined className="text-[#FF6B35]" />;
      case 'like': return <LikeOutlined className="text-[#CF222E]" />;
      case 'comment': return <CommentOutlined className="text-[#2DA44E]" />;
      case 'follow': return <TeamOutlined className="text-[#0D1117]" />;
      case 'dm': return <MessageOutlined className="text-[#FF6B35]" />;
      default: return <BellOutlined className="text-[#8B949E]" />;
    }
  };

  const getIconBg = (type: string) => {
    switch (type) {
      case 'system': return 'bg-[#FFF3ED]';
      case 'like': return 'bg-[#FFF0F1]';
      case 'comment': return 'bg-[#ECFDF3]';
      case 'follow': return 'bg-[#F6F8FA]';
      case 'dm': return 'bg-[#FFF3ED]';
      default: return 'bg-[#F6F8FA]';
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate('/dashboard')}
            className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-xl font-bold text-[#0D1117]">消息中心</h1>
          {unreadCount > 0 && <span className="tag tag-flame">{unreadCount} 条未读</span>}
          {unreadCount > 0 && (
            <Tooltip title="全部标为已读">
              <button
                onClick={handleMarkAllRead}
                disabled={markingAll}
                className="ml-auto w-8 h-8 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#2DA44E] hover:border-[#2DA44E] transition-colors"
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
            { key: 'dm', label: '私信' },
          ].map((tab) => ({ key: tab.key, label: <span className="text-sm">{tab.label}</span> }))}
        />
      </div>

      <div className="flex-1 overflow-y-auto space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Spin size="large" />
          </div>
        ) : filteredMessages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24">
            <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mb-4">
              <BellOutlined className="text-2xl text-[#8B949E]" />
            </div>
            <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无消息</h3>
            <p className="text-sm text-[#5F6B7A]">当你收到通知时，会显示在这里</p>
          </div>
        ) : (
          filteredMessages.map((msgItem) => (
            <div
              key={msgItem.id}
              className={`bg-white border rounded-xl p-4 hover:shadow-sm transition-all cursor-pointer ${!msgItem.isRead ? 'border-[#FF6B35]/30 bg-[#FFF3ED]/30' : 'border-[#E1E4E8]'}`}
              onClick={() => handleMessageClick(msgItem)}
            >
              <div className="flex items-start gap-3">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${getIconBg(msgItem.type)}`}>
                  {getIcon(msgItem.type)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className={`text-sm ${!msgItem.isRead ? 'font-semibold text-[#0D1117]' : 'font-medium text-[#5F6B7A]'}`}>
                      {msgItem.title}
                      {!msgItem.isRead && <span className="inline-block w-2 h-2 rounded-full bg-[#CF222E] ml-2 align-middle" />}
                    </h4>
                    <span className="text-xs text-[#8B949E] flex-shrink-0">{msgItem.createdAt}</span>
                  </div>
                  <p className="text-xs text-[#5F6B7A] line-clamp-2">{msgItem.content}</p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default MessagesPage;
