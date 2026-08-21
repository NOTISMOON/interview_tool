import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { App, Dropdown, Spin } from 'antd';
import {
  ArrowLeftOutlined,
  BellOutlined,
  LikeOutlined,
  CommentOutlined,
  TeamOutlined,
  MessageOutlined,
  VideoCameraOutlined,
  MoreOutlined,
  DeleteOutlined,
  FireOutlined,
} from '@ant-design/icons';
import { getMessageDetail, deleteMessage } from '@/lib/api/messages';
import type { MessageResponse } from '@/lib/api/messages';
import { getPostDetail } from '@/lib/api/posts';
import type { PostDetail } from '@/types';
import { MESSAGE_TYPE_LABEL } from '@/types';
import type { SystemMessage } from '@/types';
import { useAppStore } from '@/store';
import { updateCachedMessage, removeCachedMessage } from '@/lib/messageCache';

const TYPE_MAP: Record<string, SystemMessage['type']> = {
  system: 'system',
  like: 'like',
  comment: 'comment',
  follow: 'follow',
  dm: 'dm',
  interview: 'interview',
  follow_post: 'follow_post',
};

const getIcon = (type: string) => {
  switch (type) {
    case 'system': return <BellOutlined className="text-[#FF6B35]" />;
    case 'like': return <LikeOutlined className="text-[#CF222E]" />;
    case 'comment': return <CommentOutlined className="text-[#2DA44E]" />;
    case 'follow': return <TeamOutlined className="text-[#0D1117]" />;
    case 'dm': return <MessageOutlined className="text-[#FF6B35]" />;
    case 'interview': return <VideoCameraOutlined className="text-[#0D1117]" />;
    case 'follow_post': return <FireOutlined className="text-[#FF6B35]" />;
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
    case 'interview': return 'bg-[#F6F8FA]';
    case 'follow_post': return 'bg-[#FFF3ED]';
    default: return 'bg-[#F6F8FA]';
  }
};

/** 格式化后端ISO时间为易读形式 */
const formatTime = (iso: string) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
};

const MessageDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message: msgFn, modal } = App.useApp();
  const { user } = useAppStore();
  const [detail, setDetail] = useState<MessageResponse | null>(null);
  const [post, setPost] = useState<PostDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [deleting, setDeleting] = useState(false);

  /** 拉取消息详情；关联帖子时顺带拉取帖子摘要用于关联卡片 */
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setNotFound(false);
      setPost(null);
      try {
        const data = await getMessageDetail(Number(id));
        if (cancelled) return;
        setDetail(data);
        // 访问详情接口已标记已读，同步消息列表缓存（返回列表时状态一致）
        if (user) {
          updateCachedMessage(user.id, String(id), { isRead: true });
        }
        if (data.related?.type_name === 'post') {
          try {
            const p = await getPostDetail(data.related.id);
            if (!cancelled) setPost(p);
          } catch {
            // 帖子可能已被删除/软删，关联卡片静默降级为仅按钮跳转
          }
        }
      } catch {
        if (!cancelled) {
          setNotFound(true);
          setDetail(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [id, user]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spin size="large" />
      </div>
    );
  }

  if (!detail) {
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

  const type = TYPE_MAP[detail.type_name] || 'system';

  const handleDelete = () => {
    modal.confirm({
      title: '确认删除',
      content: '删除后将无法恢复，确定要删除这条消息吗？',
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setDeleting(true);
        try {
          await deleteMessage(Number(id));
          // 同步消息列表缓存，返回列表时不再显示已删除消息
          if (user) {
            removeCachedMessage(user.id, String(id));
          }
          msgFn.success('消息已删除');
          navigate('/dashboard/messages', { replace: true });
        } catch {
          msgFn.error('删除失败，请稍后重试');
        } finally {
          setDeleting(false);
        }
      },
    });
  };

  const postLink = detail.related?.type_name === 'post' ? detail.related.id : null;
  const userLink = detail.related?.type_name === 'user' ? detail.related.id : detail.from_user?.id ?? null;
  const reportLink = detail.related?.type_name === 'report' ? detail.related.id : null;

  const handleActionClick = () => {
    if (type === 'dm') {
      navigate(`/dashboard/messages/chat/${detail.from_user?.id ?? ''}`);
    } else if (type === 'follow') {
      if (userLink) navigate(`/dashboard/user/${userLink}`);
    } else if (type === 'comment' || type === 'like' || type === 'follow_post') {
      if (postLink) navigate(`/dashboard/community/post/${postLink}`);
    } else if (reportLink) {
      navigate(`/dashboard/report/${reportLink}`);
    } else {
      navigate('/dashboard/interview');
    }
  };

  const getActionLabel = (): string => {
    switch (type) {
      case 'system':
        return reportLink ? '查看报告' : '开始面试';
      case 'like': return '查看详情';
      case 'comment': return '查看帖子';
      case 'follow': return '查看主页';
      case 'follow_post': return '查看帖子';
      case 'dm': return '查看私信';
      case 'interview': return '查看面试';
      default: return '查看详情';
    }
  };

  const getRelatedCard = () => {
    if (type === 'follow' && detail.from_user) {
      return (
        <div
          className="bg-white border border-[#E1E4E8] rounded-2xl p-4 hover:shadow-sm hover:border-[#FF6B35]/30 transition-all cursor-pointer"
          onClick={() => userLink && navigate(`/dashboard/user/${userLink}`)}
        >
          <div className="flex items-center gap-3">
            {detail.from_user.avatar ? (
              <img
                src={detail.from_user.avatar}
                alt={detail.from_user.nickname}
                className="w-12 h-12 rounded-full object-cover flex-shrink-0"
              />
            ) : (
              <div className="w-12 h-12 rounded-full bg-[#0D1117] flex items-center justify-center text-white text-base font-bold flex-shrink-0">
                {detail.from_user.nickname[0]}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-[#0D1117]">{detail.from_user.nickname}</h4>
              <p className="text-xs text-[#5F6B7A] line-clamp-1">点击查看 TA 的主页</p>
            </div>
          </div>
        </div>
      );
    }

    if ((type === 'comment' || type === 'like' || type === 'follow_post') && post) {
      return (
        <div
          className="bg-white border border-[#E1E4E8] rounded-2xl p-4 hover:shadow-sm hover:border-[#FF6B35]/30 transition-all cursor-pointer"
          onClick={() => postLink && navigate(`/dashboard/community/post/${postLink}`)}
        >
          <div className="flex items-center gap-3 mb-2">
            <span className="tag tag-flame">帖子</span>
            {post.tags.slice(0, 2).map((t) => (
              <span key={t} className="text-xs text-[#8B949E]">#{t}</span>
            ))}
          </div>
          <h4 className="text-sm font-semibold text-[#0D1117] mb-1">{post.title}</h4>
          <p className="text-xs text-[#5F6B7A] line-clamp-2">
            {post.likes_count} 赞 · {post.comments_count} 评论 · {post.views_count} 浏览
          </p>
        </div>
      );
    }

    if (reportLink) {
      return (
        <div
          className="bg-white border border-[#E1E4E8] rounded-2xl p-4 hover:shadow-sm hover:border-[#FF6B35]/30 transition-all cursor-pointer"
          onClick={() => navigate(`/dashboard/report/${reportLink}`)}
        >
          <div className="flex items-center gap-3 mb-2">
            <span className="tag tag-success">面试报告</span>
            <span className="text-xs text-[#8B949E]">AI 模拟面试</span>
          </div>
          <h4 className="text-sm font-semibold text-[#0D1117] mb-1">面试报告已生成</h4>
          <p className="text-xs text-[#5F6B7A] line-clamp-2">点击查看详细分析和建议</p>
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
                disabled: deleting,
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
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${getIconBg(type)}`}>
            {getIcon(type)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="tag tag-flame">{MESSAGE_TYPE_LABEL[type]}</span>
              <span className="text-xs text-[#8B949E]">{formatTime(detail.created_at)}</span>
            </div>
          </div>
        </div>

        <h2 className="text-lg font-extrabold text-[#0D1117] mb-4 leading-snug">
          {detail.title}
        </h2>

        <div className="text-sm text-[#0D1117] leading-relaxed whitespace-pre-line">
          {detail.content}
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
