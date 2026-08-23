import { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Avatar, App, Spin } from 'antd';
import { ArrowLeftOutlined, SendOutlined, MessageOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { useMessageVersion } from '@/lib/messageVersion';
import {
  createChatConversation,
  getChatMessages,
  getChatConversations,
  connectChatWS,
  buildSendPayload,
  genClientMsgId,
  markChatConversationRead,
  type ChatMessage,
  type ChatConversation,
} from '@/lib/api/chat';

/** 本地乐观消息：未落库/待发送状态 */
type LocalMsg = ChatMessage & {
  client_msg_id?: string;
  status?: 'pending' | 'sent' | 'failed';
};

/** 判断消息是否为本人发送 */
const isSelf = (msg: LocalMsg, currentUserId: string) => String(msg.from_user_id) === currentUserId;

/** 时间格式化：当天显示时分，跨天显示月-日 时分 */
function formatTime(dateStr: string) {
  const d = new Date(dateStr);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const hm = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  if (sameDay) return hm;
  return `${d.getMonth() + 1}-${d.getDate()} ${hm}`;
}

const ChatPage = () => {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const { message: msgFn } = App.useApp();
  const user = useAppStore((s) => s.user);
  const { bump: bumpMsgVersion, revision: msgRevision } = useMessageVersion();

  const [peerName, setPeerName] = useState('...');
  const [messages, setMessages] = useState<LocalMsg[]>([]);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [inputValue, setInputValue] = useState('');

  const peerIdRef = useRef<number>(0);
  const convIdRef = useRef<number>(0);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // 待确认的乐观消息映射：client_msg_id -> LocalMsg（用于回执后标记 sent）
  const pendingMapRef = useRef<Map<string, LocalMsg>>(new Map());

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  /** 迭代历史分页消息（兼容 cursor 翻页） */
  const loadMessages = useCallback(async (convId: number) => {
    const all: ChatMessage[] = [];
    let cursor = 0;
    for (let i = 0; i < 5; i++) {
      const res = await getChatMessages(convId, cursor || undefined, 30);
      all.push(...res.items);
      if (res.next_cursor === null || res.items.length === 0) break;
      cursor = res.next_cursor;
    }
    // 后端按 seq DESC 返回，需倒置为正序展示
    return all.reverse();
  }, []);

  /** 建立 WS 连接并绑定收发回调 */
  const connectWS = useCallback(
    (convId: number) => {
      const socket = connectChatWS();
      wsRef.current = socket;
      socket.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string);
          if (data.action === 'new_message') {
            // 对端推送的新消息（本用户另一标签页/对端发的）
            const newMsg: LocalMsg = {
              id: 0,
              conversation_id: data.conversation_id,
              from_user_id: data.from_user_id,
              receiver_id: 0,
              content_type: data.content_type,
              content: data.content,
              seq: data.seq,
              is_read: false,
              created_at: new Date().toISOString(),
            };
            if (data.conversation_id === convIdRef.current) {
              setMessages((prev) => {
                if (prev.some((m) => m.seq === data.seq && m.from_user_id === data.from_user_id)) {
                  return prev;
                }
                return [...prev, newMsg];
              });
              scrollToBottom();
              // 收到对方新消息：通知全局消息版本号 +1，使消息中心等共享域页面刷新
              bumpMsgVersion('chat_message');
              // 收到对方新消息时自动标记该会话已读（停留聊天页未读即时清零）
              if (String(data.from_user_id) !== String(user?.id) && convIdRef.current) {
                markChatConversationRead(convIdRef.current).catch(() => {
                  /* 已读失败不影响展示 */
                });
              }
            }
          } else if (data.conversation_id === convIdRef.current) {
            // 回执：sent/duplicate/error，更新对应 client_msg_id 的乐观消息状态
            const pending = pendingMapRef.current.get(data.client_msg_id);
            if (pending) {
              const updated: LocalMsg = {
                ...pending,
                seq: data.seq ?? pending.seq,
                status: data.action === 'error' ? 'failed' : 'sent',
              };
              pendingMapRef.current.set(data.client_msg_id, updated);
              setMessages((prev) =>
                prev.map((m) => (m.client_msg_id === data.client_msg_id ? updated : m)),
              );
            }
          }
        } catch {
          // 忽略非 JSON 消息
        }
      };
      socket.onclose = () => {
        // 简单重连（带退避避免风暴）
        setTimeout(() => {
          if (convIdRef.current && wsRef.current?.readyState === WebSocket.CLOSED) {
            connectWS(convIdRef.current);
          }
        }, 3000);
      };
    },
    [scrollToBottom, user?.id, bumpMsgVersion],
  );

  /** 初始化：解析 userId -> 获取/创建会话 -> 加载历史 -> 连 WS */
  useEffect(() => {
    if (!userId || !user) return;
    const peerId = Number(userId);
    if (!Number.isFinite(peerId) || peerId <= 0) return;

    let cancelled = false;
    setLoading(true);
    const bootstrap = async () => {
      try {
        // 1. 获取或创建会话
        const conv = await createChatConversation(peerId);
        convIdRef.current = conv.id;
        peerIdRef.current = peerId;

        // 2. 加载历史消息
        const history = await loadMessages(conv.id);
        if (!cancelled) setMessages(history);

        // 3. 建立 WS 连接
        connectWS(conv.id);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail;
        if (msg === '不能与自己私信') {
          msgFn.error('不能与自己私信');
        } else {
          msgFn.error('加载会话失败');
        }
        setPeerName('加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    bootstrap();
    return () => {
      cancelled = true;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [userId, user, loadMessages, connectWS, msgFn]);

  /** 加载对方昵称 */
  useEffect(() => {
    if (!peerIdRef.current) return;
    import('@/lib/api/user').then(({ getUserPublicProfile }) => {
      getUserPublicProfile(peerIdRef.current)
        .then((p) => {
          if (p.nickname) setPeerName(p.nickname);
        })
        .catch(() => {
          /* 昵称加载失败静默 */
        });
    });
  }, [peerIdRef]);

  /** 加载右侧私信会话列表（初始 + 版本号变化时刷新，保持列表最新） */
  useEffect(() => {
    let cancelled = false;
    const loadConvs = () => {
      getChatConversations()
        .then((res) => {
          if (!cancelled) setConversations(res.items);
        })
        .catch(() => {
          /* 会话列表加载失败静默 */
        });
    };
    loadConvs();
    return () => { cancelled = true; };
  }, [msgRevision, user?.id]);

  const handleSend = useCallback(() => {
    const content = inputValue.trim();
    if (!content || sending || !convIdRef.current) return;
    const cmid = genClientMsgId();
    const optimistic: LocalMsg = {
      id: 0,
      conversation_id: convIdRef.current,
      from_user_id: Number(user?.id),
      receiver_id: peerIdRef.current,
      content_type: 1,
      content,
      seq: 0,
      is_read: true,
      created_at: new Date().toISOString(),
      client_msg_id: cmid,
      status: 'pending',
    };
    pendingMapRef.current.set(cmid, optimistic);
    setMessages((prev) => [...prev, optimistic]);
    setInputValue('');
    setSending(true);

    const send = () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify(
            buildSendPayload(convIdRef.current, peerIdRef.current, cmid, content),
          ),
        );
      } else {
        // WS 未就绪：标记失败（由重连后的下一条补偿）
        pendingMapRef.current.set(cmid, { ...optimistic, status: 'failed' });
        setMessages((prev) =>
          prev.map((m) => (m.client_msg_id === cmid ? { ...m, status: 'failed' } : m)),
        );
      }
      setSending(false);
    };
    // 等待 WS 打开（若刚建立）
    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      wsRef.current.onopen = send;
    } else {
      send();
    }
  }, [inputValue, sending, user]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spin size="large" />
      </div>
    );
  }

  if (!convIdRef.current && !loading) {
    return (
      <div className="max-w-[700px] animate-fade-in">
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate('/dashboard/messages')}
            className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-lg font-bold text-[#0D1117]">私信</h1>
        </div>
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 text-center">
          <h3 className="text-base font-semibold text-[#0D1117] mb-2">会话不可用</h3>
          <p className="text-sm text-[#5F6B7A] mb-6">无法建立与该用户的私信会话</p>
          <button onClick={() => navigate('/dashboard/messages')} className="btn-flame">
            返回消息列表
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-60px-3rem)] flex gap-4 animate-fade-in">
      {/* 左栏：当前聊天窗口 */}
      <div className="flex-1 max-w-[700px] flex flex-col min-w-0">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard/messages')}
            className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-lg font-bold text-[#0D1117]">私信</h1>
        </div>
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#F0F2F5]">
          <div className="flex items-center gap-3">
            <Avatar
              size={40}
              className="!bg-[#0D1117] flex-shrink-0 !text-sm cursor-pointer"
              onClick={() => navigate(`/dashboard/user/${peerIdRef.current}`)}
            >
              {peerName[0] || '?'}
            </Avatar>
            <div
              className="text-sm font-semibold text-[#0D1117] cursor-pointer hover:text-[#FF6B35]"
              onClick={() => navigate(`/dashboard/user/${peerIdRef.current}`)}
            >
              {peerName}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-2 min-h-0">
          {messages.map((msg, idx) => {
            const self = isSelf(msg, user?.id ?? '');
            const prev = idx > 0 ? messages[idx - 1] : undefined;
            const showSep =
              !prev || new Date(msg.created_at).getTime() - new Date(prev.created_at).getTime() > 5 * 60 * 1000;
            return (
              <div key={msg.client_msg_id || msg.id || `${msg.seq}-${msg.from_user_id}`}>
                {showSep && (
                  <div className="flex items-center justify-center my-3">
                    <span className="text-xs text-[#8B949E] bg-[#F6F8FA] px-3 py-1 rounded-full">
                      {formatTime(msg.created_at)}
                    </span>
                  </div>
                )}
                <div className={`flex ${self ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[70%] px-4 py-2.5 text-sm leading-relaxed rounded-2xl break-words ${
                      self
                        ? 'bg-[#FF6B35] text-white rounded-br-md'
                        : 'bg-[#F6F8FA] text-[#0D1117] rounded-bl-md'
                    }`}
                  >
                    {msg.content}
                    {msg.status === 'pending' && (
                      <span className="ml-2 text-xs opacity-70">发送中...</span>
                    )}
                    {msg.status === 'failed' && (
                      <span className="ml-2 text-xs opacity-80">未发送</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>

        <div className="px-5 py-4 border-t border-[#F0F2F5]">
          <div className="flex items-end gap-3">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息..."
              rows={1}
              className="flex-1 px-4 py-2.5 border border-[#E1E4E8] rounded-xl text-sm text-[#0D1117] placeholder:text-[#8B949E] resize-none focus:outline-none focus:border-[#FF6B35] focus:ring-1 focus:ring-[#FF6B35]/20 transition-all max-h-[120px]"
            />
            <button
              onClick={handleSend}
              disabled={!inputValue.trim() || sending}
              className="w-10 h-10 rounded-xl bg-[#FF6B35] text-white flex items-center justify-center hover:bg-[#E85D26] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            >
              <SendOutlined />
            </button>
          </div>
          <div className="text-xs text-[#8B949E] mt-2">按 Enter 发送，Shift + Enter 换行</div>
        </div>
      </div>
      </div>
      {/* 右栏：私信会话列表（利用右侧空白） */}
      <aside className="w-[320px] flex flex-col flex-shrink-0 min-h-0">
        <div className="flex items-center gap-2 px-1 mb-3">
          <MessageOutlined className="text-[#FF6B35]" />
          <h2 className="text-sm font-semibold text-[#0D1117]">会话</h2>
        </div>
        <div className="bg-white border border-[#E1E4E8] rounded-2xl flex-1 overflow-y-auto min-h-0">
          {conversations.length === 0 ? (
            <div className="p-8 text-center text-sm text-[#8B949E]">暂无会话</div>
          ) : (
            conversations.map((conv) => {
              const isActive = conv.peer?.id === peerIdRef.current;
              return (
                <div
                  key={conv.id}
                  onClick={() => navigate(`/dashboard/messages/chat/${conv.peer?.id}`)}
                  className={`flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors border-b border-[#F6F8FA] last:border-b-0 ${
                    isActive ? 'bg-[#FFF3ED]' : 'hover:bg-[#FAFBFC]'
                  }`}
                >
                  <Avatar size={40} className="!bg-[#0D1117] flex-shrink-0 !text-sm">
                    {(conv.peer?.nickname || '?')[0]}
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className={`text-sm truncate ${isActive ? 'font-semibold text-[#FF6B35]' : 'font-medium text-[#0D1117]'}`}>
                        {conv.peer?.nickname || `用户${conv.peer?.id}`}
                      </span>
                      {conv.last_message_at && (
                        <span className="text-xs text-[#8B949E] flex-shrink-0 ml-2">
                          {new Date(conv.last_message_at).toLocaleTimeString('zh-CN', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <p className="text-xs text-[#5F6B7A] truncate flex-1 mr-2">
                        {conv.last_message || '暂无消息'}
                      </p>
                      {conv.unread > 0 && (
                        <span className="w-5 h-5 rounded-full bg-[#FF6B35] text-white text-[10px] font-semibold flex items-center justify-center flex-shrink-0">
                          {conv.unread > 99 ? '99+' : conv.unread}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>
    </div>
  );
};

export default ChatPage;