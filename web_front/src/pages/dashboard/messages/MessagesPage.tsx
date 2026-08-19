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

/** localStorage键：最后一条已接收消息ID，跨页面/跨重启共用 */
const NOTIFY_LAST_ID_KEY = 'notify:last_msg_id';

/** 将后端MessageResponse映射为前端SystemMessage */
function mapMessage(m: MessageResponse): SystemMessage {
  const typeMap: Record<string, SystemMessage['type']> = {
    system: 'system',
    like: 'like',
    comment: 'comment',
    follow: 'follow',
    dm: 'dm',
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
  const [activeTab, setActiveTab] = useState('all');
  const [messages, setMessages] = useState<SystemMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [markingAll, setMarkingAll] = useState(false);

  /** 加载消息列表。
   *  - 首次加载（无 cursor 且 tab 为 'all'）：增量模式 since_id + limit=10
   *  - 按类型筛选 / 加载更多：翻页模式 cursor + size=20
   */
  const loadMessages = useCallback(async (cursor?: number | null, type?: string) => {
    try {
      const isFirstLoad = !cursor && (!type || type === 'all');
      const params: { since_id?: number; limit?: number; cursor?: number; size?: number; type?: string } = {};

      if (isFirstLoad) {
        const lastId = Number(localStorage.getItem(NOTIFY_LAST_ID_KEY) || 0);
        params.since_id = lastId;
        params.limit = 10;
      } else {
        params.size = 20;
        if (cursor) params.cursor = cursor;
        if (type && type !== 'all') params.type = type;
      }

      const res = await getMessages(params);
      const items = res.items.map(mapMessage);

      if (cursor) {
        setMessages((prev) => {
          const existingIds = new Set(prev.map((m) => m.id));
          const newItems = items.filter((m) => !existingIds.has(m.id));
          return [...prev, ...newItems];
        });
      } else {
        setMessages(items);
      }

      setNextCursor(res.next_cursor);
      setUnreadCount(res.unread_total);

      // 更新本地 last_msg_id（取本次返回的最大 id）
      if (items.length > 0) {
        const maxId = Math.max(...items.map((m) => Number(m.id)));
        const prev = Number(localStorage.getItem(NOTIFY_LAST_ID_KEY) || 0);
        if (maxId > prev) {
          localStorage.setItem(NOTIFY_LAST_ID_KEY, String(maxId));
        }
      }
    } catch {
      msg.error('加载消息失败');
    }
  }, [msg]);

  /** 加载未读计数 */
  const loadUnreadCount = useCallback(async () => {
    try {
      const res = await getUnreadCount();
      setUnreadCount(res.total);
    } catch {
      // 静默失败
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    loadMessages().finally(() => setLoading(false));
    loadUnreadCount();
  }, [loadMessages, loadUnreadCount]);

  /** 切换标签时重新加载 */
  useEffect(() => {
    setLoading(true);
    setMessages([]);
    setNextCursor(null);
    loadMessages(null, activeTab).finally(() => setLoading(false));
  }, [activeTab, loadMessages]);

  /** 加载更多 */
  const handleLoadMore = async () => {
    if (loadingMore || nextCursor === null) return;
    setLoadingMore(true);
    await loadMessages(nextCursor, activeTab);
    setLoadingMore(false);
  };

  /** 点击消息 */
  const handleMessageClick = async (msgItem: SystemMessage) => {
    if (!msgItem.isRead) {
      try {
        await markMessageRead(Number(msgItem.id));
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
      msg.success(`已标记 ${res.count} 条消息为已读`);
      setMessages((prev) => prev.map((m) => ({ ...m, isRead: true })));
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
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24">
            <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mb-4">
              <BellOutlined className="text-2xl text-[#8B949E]" />
            </div>
            <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无消息</h3>
            <p className="text-sm text-[#5F6B7A]">当你收到通知时，会显示在这里</p>
          </div>
        ) : (
          messages.map((msgItem) => (
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
        {nextCursor !== null && !loading && (
          <div className="p-4 text-center">
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="text-sm text-[#FF6B35] font-medium hover:text-[#E85D26] transition-colors"
            >
              {loadingMore ? '加载中...' : '加载更多'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default MessagesPage;