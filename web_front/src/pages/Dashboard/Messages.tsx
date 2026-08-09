import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Tabs } from 'antd';
import {
  ArrowLeftOutlined,
  BellOutlined,
  LikeOutlined,
  CommentOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type { SystemMessage } from '@/types';

const MOCK_MESSAGES: SystemMessage[] = [
  { id: '1', type: 'system', title: '欢迎加入面试教练', content: '上传你的简历，AI 将为你生成个性化面试题。', isRead: false, createdAt: '刚刚' },
  { id: '2', type: 'like', title: '新的点赞', content: '你的面试报告获得了 3 个点赞', isRead: true, createdAt: '2 小时前', relatedId: 'report_1' },
  { id: '3', type: 'comment', title: '新的评论', content: '前端小张 评论了你的帖子', isRead: true, createdAt: '5 小时前', relatedId: 'post_1' },
  { id: '4', type: 'follow', title: '新的关注', content: '上岸的鱼 关注了你', isRead: true, createdAt: '昨天', relatedId: 'u2' },
  { id: '5', type: 'system', title: '面试报告已生成', content: '你的 AI 模拟面试报告已生成，总得分 82 分', isRead: true, createdAt: '昨天', relatedId: 'report_1' },
];

const MessagesPage = () => {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [activeTab, setActiveTab] = useState('all');

  const getIcon = (type: string) => {
    switch (type) {
      case 'system': return <BellOutlined className="text-[#FF6B35]" />;
      case 'like': return <LikeOutlined className="text-[#CF222E]" />;
      case 'comment': return <CommentOutlined className="text-[#2DA44E]" />;
      case 'follow': return <TeamOutlined className="text-[#0D1117]" />;
      default: return <BellOutlined className="text-[#8B949E]" />;
    }
  };

  const getIconBg = (type: string) => {
    switch (type) {
      case 'system': return 'bg-[#FFF3ED]';
      case 'like': return 'bg-[#FFF0F1]';
      case 'comment': return 'bg-[#ECFDF3]';
      case 'follow': return 'bg-[#F6F8FA]';
      default: return 'bg-[#F6F8FA]';
    }
  };

  const filtered = activeTab === 'all' ? MOCK_MESSAGES : MOCK_MESSAGES.filter((m) => m.type === activeTab);
  const unreadCount = MOCK_MESSAGES.filter((m) => !m.isRead).length;

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
        ].map((tab) => ({ key: tab.key, label: <span className="text-sm">{tab.label}</span> }))}
      />

      <div className="space-y-2">
        {filtered.map((msg) => (
          <div
            key={msg.id}
            className={`bg-white border rounded-xl p-4 hover:shadow-sm transition-all cursor-pointer ${!msg.isRead ? 'border-[#FF6B35]/30 bg-[#FFF3ED]/30' : 'border-[#E1E4E8]'}`}
            onClick={() => message.info('消息详情即将上线')}
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