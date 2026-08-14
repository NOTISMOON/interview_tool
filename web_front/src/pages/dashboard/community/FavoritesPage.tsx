import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar, App } from 'antd';
import {
  ArrowLeftOutlined,
  StarFilled,
  LikeOutlined,
  MessageOutlined,
  FireOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import type { CommunityPost } from '@/types';

const MOCK_FAVORITES: CommunityPost[] = [
  {
    id: '2', title: 'AI 模拟面试真的有用！拿到 offer 了',
    content: '用这个工具练习了两周，面试时明显感觉更自信了，推荐大家都试试...',
    author: { id: 'u2', nickname: '上岸的鱼', avatar: '' },
    tags: ['经验分享', 'Offer'], likes: 256, comments: 89, views: 5600,
    isPinned: false, isHot: true, createdAt: '2 小时前',
  },
  {
    id: '3', title: '分享一套后端面试常见问题整理',
    content: '整理了最近面试遇到的 50 道高频题，包括 JVM、并发、数据库、Redis 等核心知识点...',
    author: { id: 'u3', nickname: 'Go 夜读', avatar: '' },
    tags: ['资源分享', '后端'], likes: 89, comments: 23, views: 1800,
    isPinned: false, isHot: false, createdAt: '5 小时前',
  },
  {
    id: '5', title: '35 岁程序员何去何从？大龄转管理经验分享',
    content: '做了 10 年开发，最近成功转技术管理，分享一下我的转型心得...',
    author: { id: 'u5', nickname: '老码农', avatar: '' },
    tags: ['职业规划', '经验分享'], likes: 342, comments: 120, views: 8900,
    isPinned: false, isHot: true, createdAt: '昨天',
  },
];

const FavoritesPage = () => {
  const navigate = useNavigate();
  const { message: msg, modal } = App.useApp();
  const [favorites, setFavorites] = useState<CommunityPost[]>(MOCK_FAVORITES);

  const handleRemove = (id: string) => {
    modal.confirm({
      title: '取消收藏',
      content: '确定要取消收藏这个帖子吗？',
      okText: '确定',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => {
        setFavorites((prev) => prev.filter((p) => p.id !== id));
        msg.success('已取消收藏');
      },
    });
  };

  return (
    <div className="max-w-[700px] flex flex-col h-full">
      <div className="flex-shrink-0 flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/dashboard/profile')}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#0D1117]">我的收藏</h1>
      </div>

      {favorites.length === 0 ? (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mx-auto mb-4">
            <StarFilled className="text-2xl text-[#8B949E]" />
          </div>
          <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无收藏</h3>
          <p className="text-sm text-[#5F6B7A] mb-6">去社区发现感兴趣的内容并收藏吧</p>
          <button onClick={() => navigate('/dashboard/community')} className="btn-flame">
            去社区看看
          </button>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          {favorites.map((post) => (
            <div
              key={post.id}
              className="bg-white border border-[#E1E4E8] rounded-xl p-5 hover:border-[#FF6B35]/30 hover:shadow-sm transition-all group"
            >
              <div
                className="flex items-start gap-3 cursor-pointer"
                onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
              >
                <Avatar size={36} className="!bg-[#0D1117] flex-shrink-0">
                  {post.author.nickname[0]}
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <h4 className="text-sm font-semibold text-[#0D1117] truncate">{post.title}</h4>
                    {post.isHot && (
                      <span className="tag tag-flame">
                        <FireOutlined className="text-[10px]" /> 热
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#5F6B7A] line-clamp-2 mb-3">{post.content}</p>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-[#8B949E]">
                      <span className="font-medium text-[#5F6B7A]">{post.author.nickname}</span>
                      <span className="w-1 h-1 rounded-full bg-[#E1E4E8]" />
                      <span>{post.createdAt}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-[#8B949E]">
                      <span className="inline-flex items-center gap-1"><LikeOutlined /> {post.likes}</span>
                      <span className="inline-flex items-center gap-1"><MessageOutlined /> {post.comments}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex justify-end mt-3 pt-3 border-t border-[#F0F2F5]">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemove(post.id);
                  }}
                  className="text-xs text-[#8B949E] hover:text-[#CF222E] transition-colors inline-flex items-center gap-1 opacity-0 group-hover:opacity-100"
                >
                  <DeleteOutlined /> 取消收藏
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default FavoritesPage;