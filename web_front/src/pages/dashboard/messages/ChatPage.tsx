import { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Avatar, App } from 'antd';
import {
  ArrowLeftOutlined,
  SendOutlined,
  UserAddOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { mockDmConversations } from '@/lib/mocks/data';
import type { DmConversation, DmMessage } from '@/types';

const ChatPage = () => {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const { message: msgFn } = App.useApp();
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const conversation: DmConversation | undefined = mockDmConversations.find(
    (c) => c.withUser.id === userId
  );

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation?.messages]);

  if (!conversation) {
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
          <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mx-auto mb-4">
            <UserOutlined className="text-2xl text-[#8B949E]" />
          </div>
          <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无对话</h3>
          <p className="text-sm text-[#5F6B7A] mb-6">该用户不在对话列表中</p>
          <button onClick={() => navigate('/dashboard/messages')} className="btn-flame">
            返回消息列表
          </button>
        </div>
      </div>
    );
  }

  const handleSend = () => {
    if (!inputValue.trim()) return;
    msgFn.success('消息已发送');
    setInputValue('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFollow = () => {
    msgFn.success('已关注');
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  const shouldShowTimeSeparator = (currentMsg: DmMessage, prevMsg?: DmMessage) => {
    if (!prevMsg) return true;
    const curr = new Date(currentMsg.createdAt).getTime();
    const prev = new Date(prevMsg.createdAt).getTime();
    return curr - prev > 5 * 60 * 1000;
  };

  return (
    <div className="max-w-[700px] h-full flex flex-col animate-fade-in">
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
              onClick={() => navigate(`/dashboard/user/${conversation.withUser.id}`)}
            >
              {conversation.withUser.name[0]}
            </Avatar>
            <div>
              <div
                className="text-sm font-semibold text-[#0D1117] cursor-pointer hover:text-[#FF6B35]"
                onClick={() => navigate(`/dashboard/user/${conversation.withUser.id}`)}
              >
                {conversation.withUser.name}
              </div>
              <div className="text-xs text-[#5F6B7A]">
                {conversation.withUser.isOnline ? (
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#2DA44E]" />
                    在线
                  </span>
                ) : (
                  '离线'
                )}
              </div>
            </div>
          </div>
          <button onClick={handleFollow} className="btn-flame !py-1.5 !px-4 !text-xs">
            <UserAddOutlined /> 关注
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {conversation.messages.map((msg, idx) => {
            const isSelf = msg.fromUserId === '1';
            const prevMsg = idx > 0 ? conversation.messages[idx - 1] : undefined;
            const showTimeSeparator = shouldShowTimeSeparator(msg, prevMsg);

            return (
              <div key={msg.id}>
                {showTimeSeparator && (
                  <div className="flex items-center justify-center my-4">
                    <span className="text-xs text-[#8B949E] bg-[#F6F8FA] px-3 py-1 rounded-full">
                      {formatTime(msg.createdAt)}
                    </span>
                  </div>
                )}
                <div className={`flex ${isSelf ? 'justify-end' : 'justify-start'}`}>
                  {!isSelf && (
                    <Avatar
                      size={28}
                      className="!bg-[#0D1117] flex-shrink-0 !text-xs mr-2 mt-1 cursor-pointer"
                      onClick={() => navigate(`/dashboard/user/${conversation.withUser.id}`)}
                    >
                      {conversation.withUser.name[0]}
                    </Avatar>
                  )}
                  <div
                    className={`max-w-[70%] px-4 py-2.5 text-sm leading-relaxed rounded-2xl break-words ${
                      isSelf
                        ? 'bg-[#FF6B35] text-white rounded-br-md'
                        : 'bg-[#F6F8FA] text-[#0D1117] rounded-bl-md'
                    }`}
                  >
                    {msg.content}
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
              disabled={!inputValue.trim()}
              className="w-10 h-10 rounded-xl bg-[#FF6B35] text-white flex items-center justify-center hover:bg-[#E85D26] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            >
              <SendOutlined />
            </button>
          </div>
          <div className="text-xs text-[#8B949E] mt-2">
            按 Enter 发送，Shift + Enter 换行
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;