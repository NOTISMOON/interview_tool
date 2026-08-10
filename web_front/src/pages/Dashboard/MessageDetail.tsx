import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { App, Dropdown } from 'antd';
import {
  ArrowLeftOutlined,
  BellOutlined,
  LikeOutlined,
  CommentOutlined,
  TeamOutlined,
  VideoCameraOutlined,
  MessageOutlined,
  MoreOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { MESSAGE_TYPE_LABEL } from '@/types';
import { mockMessages } from '@/mocks/data';
import type { SystemMessage } from '@/types';

const getIcon = (type: string) => {
  switch (type) {
    case 'system': return <BellOutlined className="text-[#FF6B35]" />;
    case 'like': return <LikeOutlined className="text-[#CF222E]" />;
    case 'comment': return <CommentOutlined className="text-[#2DA44E]" />;
    case 'follow': return <TeamOutlined className="text-[#0D1117]" />;
    case 'interview': return <VideoCameraOutlined className="text-[#5F6B7A]" />;
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
    case 'interview': return 'bg-[#F0F2F5]';
    case 'dm': return 'bg-[#FFF3ED]';
    default: return 'bg-[#F6F8FA]';
  }
};

const MessageDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message: msgFn, modal } = App.useApp();
  const [messages, setMessages] = useState<SystemMessage[]>(mockMessages);

  const messageItem = messages.find((m) => m.id === id);

  if (!messageItem) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <h2 className="text-lg font-bold text-[#0D1117] mb-2">消息不存在</h2>
        <p className="text-sm text-[#5F6B7A] mb-6">该消息可能已被删除或链接无效</p>
        <button onClick={() => navigate('/dashboard/messages')} className="btn-flame">
          返回消息中心
        </button>
      </div>
    );
  }

  const handleDelete = () => {
    modal.confirm({
      title: '确认删除',
      content: '删除后将无法恢复，确定要删除这条消息吗？',
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => {
        setMessages((prev) => prev.filter((m) => m.id !== id));
        msgFn.success('消息已删除');
        navigate('/dashboard/messages', { replace: true });
      },
    });
  };

  const handleActionClick = () => {
    if (messageItem.type === 'like') {
      navigate('/dashboard/community/post/1');
    } else if (messageItem.type === 'comment') {
      navigate('/dashboard/community/post/1');
    } else if (messageItem.type === 'follow') {
      if (messageItem.fromUser) {
        navigate(`/dashboard/user/${messageItem.fromUser.id}`);
      }
    } else if (messageItem.type === 'interview') {
      navigate('/dashboard/interview');
    } else if (messageItem.type === 'system') {
      if (messageItem.relatedId?.startsWith('report')) {
        navigate(`/dashboard/report/${messageItem.relatedId}`);
      } else {
        navigate('/dashboard/interview');
      }
    }
  };

  const getActionLabel = (): string => {
    switch (messageItem.type) {
      case 'system':
        if (messageItem.relatedId?.startsWith('report')) return '查看报告';
        return '开始面试';
      case 'like': return '查看详情';
      case 'comment': return '查看帖子';
      case 'follow': return '查看主页';
      case 'interview': return '进入面试';
      case 'dm': return '查看私信';
      default: return '查看详情';
    }
  };

  const getRelatedCard = () => {
    if (messageItem.type === 'system') {
      if (messageItem.relatedId?.startsWith('report')) {
        return (
          <div
            className="bg-white border border-[#E1E4E8] rounded-2xl p-4 hover:shadow-sm hover:border-[#FF6B35]/30 transition-all cursor-pointer"
            onClick={() => navigate(`/dashboard/report/${messageItem.relatedId}`)}
          >
            <div className="flex items-center gap-3 mb-2">
              <span className="tag tag-success">面试报告</span>
              <span className="text-xs text-[#8B949E]">AI 模拟面试</span>
            </div>
            <h4 className="text-sm font-semibold text-[#0D1117] mb-1">面试报告已生成</h4>
            <p className="text-xs text-[#5F6B7A] line-clamp-2">总得分 82 分，查看详细分析和建议</p>
          </div>
        );
      }
      return null;
    }

    if (messageItem.type === 'comment') {
      return (
        <div
          className="bg-white border border-[#E1E4E8] rounded-2xl p-4 hover:shadow-sm hover:border-[#FF6B35]/30 transition-all cursor-pointer"
          onClick={() => navigate('/dashboard/community/post/1')}
        >
          <div className="flex items-center gap-3 mb-2">
            <span className="tag tag-flame">帖子</span>
            <span className="text-xs text-[#8B949E]">面试经验</span>
          </div>
          <h4 className="text-sm font-semibold text-[#0D1117] mb-1">前端三年经验，面试字节挂了三次，求大佬指点</h4>
          <p className="text-xs text-[#5F6B7A] line-clamp-2">三年 Vue 经验，最近在学 React，面试总挂在系统设计上...</p>
        </div>
      );
    }

    if (messageItem.type === 'like') {
      return (
        <div
          className="bg-white border border-[#E1E4E8] rounded-2xl p-4 hover:shadow-sm hover:border-[#FF6B35]/30 transition-all cursor-pointer"
          onClick={() => navigate('/dashboard/community/post/1')}
        >
          <div className="flex items-center gap-3 mb-2">
            <span className="tag tag-flame">帖子</span>
            <span className="text-xs text-[#8B949E]">面试经验</span>
          </div>
          <h4 className="text-sm font-semibold text-[#0D1117] mb-1">前端三年经验，面试字节挂了三次，求大佬指点</h4>
          <p className="text-xs text-[#5F6B7A] line-clamp-2">128 赞 · 45 评论 · 2300 浏览</p>
        </div>
      );
    }

    if (messageItem.type === 'follow' && messageItem.fromUser) {
      return (
        <div
          className="bg-white border border-[#E1E4E8] rounded-2xl p-4 hover:shadow-sm hover:border-[#FF6B35]/30 transition-all cursor-pointer"
          onClick={() => navigate(`/dashboard/user/${messageItem.fromUser!.id}`)}
        >
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-[#0D1117] flex items-center justify-center text-white text-base font-bold flex-shrink-0">
              {messageItem.fromUser.name[0]}
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-[#0D1117]">{messageItem.fromUser.name}</h4>
              <p className="text-xs text-[#5F6B7A] line-clamp-1">
                已拿到大厂 offer，分享面试经验
              </p>
            </div>
            <button
              className="btn-flame !py-1.5 !px-4 !text-xs"
              onClick={(e) => {
                e.stopPropagation();
                msgFn.success('已关注');
              }}
            >
              + 关注
            </button>
          </div>
        </div>
      );
    }

    if (messageItem.type === 'interview') {
      return (
        <div
          className="bg-white border border-[#E1E4E8] rounded-2xl p-4 hover:shadow-sm hover:border-[#FF6B35]/30 transition-all cursor-pointer"
          onClick={() => navigate('/dashboard/interview')}
        >
          <div className="flex items-center gap-3 mb-2">
            <span className="tag tag-flame">面试邀请</span>
            <span className="text-xs text-[#8B949E]">字节跳动</span>
          </div>
          <h4 className="text-sm font-semibold text-[#0D1117] mb-1">高级前端工程师</h4>
          <p className="text-xs text-[#5F6B7A]">地点：北京 · 薪资：30K-50K</p>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="max-w-[700px] animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard/messages')}
            className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-lg font-bold text-[#0D1117]">消息详情</h1>
        </div>

        <Dropdown
          menu={{
            items: [
              {
                key: 'delete',
                label: '删除消息',
                icon: <DeleteOutlined />,
                danger: true,
                onClick: handleDelete,
              },
            ],
          }}
          trigger={['click']}
          placement="bottomRight"
        >
          <button className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors">
            <MoreOutlined />
          </button>
        </Dropdown>
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 mb-4">
        <div className="flex items-center gap-3 mb-4">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${getIconBg(messageItem.type)}`}>
            {getIcon(messageItem.type)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="tag tag-flame">{MESSAGE_TYPE_LABEL[messageItem.type]}</span>
              <span className="text-xs text-[#8B949E]">{messageItem.createdAt}</span>
            </div>
          </div>
        </div>

        <h2 className="text-lg font-extrabold text-[#0D1117] mb-4 leading-snug">
          {messageItem.title}
        </h2>

        <div className="text-sm text-[#0D1117] leading-relaxed whitespace-pre-line">
          {messageItem.content}
        </div>
      </div>

      {getRelatedCard() && (
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-[#8B949E] mb-3 uppercase tracking-wide">关联内容</h3>
          {getRelatedCard()}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={handleActionClick}
          className="btn-flame"
        >
          {getActionLabel()}
        </button>
        <button
          onClick={() => navigate('/dashboard/messages')}
          className="btn-ghost"
        >
          返回消息列表
        </button>
      </div>
    </div>
  );
};

export default MessageDetailPage;