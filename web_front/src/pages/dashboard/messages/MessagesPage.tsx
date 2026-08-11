import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tabs } from 'antd';
import {
  ArrowLeftOutlined,
  BellOutlined,
  LikeOutlined,
  CommentOutlined,
  TeamOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { mockMessages } from '@/lib/mocks/data';
import type { SystemMessage } from '@/types';

const MessagesPage = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('all');

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

  const filtered = activeTab === 'all' ? mockMessages : mockMessages.filter((m) => m.type === activeTab);
  const unreadCount = mockMessages.filter((m) => !m.isRead).length;

  const handleMessageClick = (msg: SystemMessage) => {
    if (msg.type === 'dm') {
      navigate(`/dashboard/messages/chat/${msg.fromUser?.id || 'u3'}`);
    } else {
      navigate(`/dashboard/messages/${msg.id}`);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/dashboard')}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#0D1117]">消息中心</h1>
        {unreadCount > 0 && <span className="tag tag-flame">{unreadCount} 条未读</span>}
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

      <div className="space-y-2">
        {filtered.map((msg) => (
          <div
            key={msg.id}
            className={`bg-white border rounded-xl p-4 hover:shadow-sm transition-all cursor-pointer ${!msg.isRead ? 'border-[#FF6B35]/30 bg-[#FFF3ED]/30' : 'border-[#E1E4E8]'}`}
            onClick={() => handleMessageClick(msg)}
          >
            <div className="flex items-start gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${getIconBg(msg.type)}`}>
                {getIcon(msg.type)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <h4 className={`text-sm ${!msg.isRead ? 'font-semibold text-[#0D1117]' : 'font-medium text-[#5F6B7A]'}`}>
                    {msg.title}
                    {!msg.isRead && <span className="inline-block w-2 h-2 rounded-full bg-[#CF222E] ml-2 align-middle" />}
                  </h4>
                  <span className="text-xs text-[#8B949E] flex-shrink-0">{msg.createdAt}</span>
                </div>
                <p className="text-xs text-[#5F6B7A] line-clamp-2">{msg.content}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default MessagesPage;