import { useNavigate } from 'react-router-dom';
import { Avatar, App, Segmented } from 'antd';
import {
  FireOutlined,
  LikeOutlined,
  MessageOutlined,
  UserAddOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useState } from 'react';
import { useAppStore } from '@/store';

const FeedPage = () => {
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const { followedPosts, user } = useAppStore();
  const [filter, setFilter] = useState<string>('all');

  const filteredPosts = filter === 'hot'
    ? followedPosts.filter((p) => p.isHot)
    : followedPosts;

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-[#0D1117]">动态</h1>
            <p className="text-sm text-[#5F6B7A] mt-1">
              关注了 <span className="font-semibold text-[#FF6B35]">{user?.followingCount ?? 0}</span> 人
            </p>
          </div>
          <button
            onClick={() => navigate('/dashboard/community')}
            className="btn-ghost"
          >
            <UserAddOutlined /> 发现更多
          </button>
        </div>

        <div className="mb-5">
          <Segmented
            value={filter}
            onChange={(val) => setFilter(val as string)}
            options={[
              { label: '全部动态', value: 'all' },
              { label: '热门', value: 'hot', icon: <FireOutlined /> },
            ]}
            className="!bg-[#F6F8FA] !p-1 !rounded-xl"
          />
        </div>
      </div>

      {filteredPosts.length === 0 ? (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mx-auto mb-4">
            <ReloadOutlined className="text-2xl text-[#8B949E]" />
          </div>
          <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无动态</h3>
          <p className="text-sm text-[#5F6B7A] mb-6">
            {user?.followingCount === 0
              ? '你还没有关注任何人，去社区发现有趣的用户吧'
              : '你关注的人还没有发布新内容'}
          </p>
          <button onClick={() => navigate('/dashboard/community')} className="btn-flame">
            去社区看看
          </button>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          {filteredPosts.map((post) => (
            <div
              key={post.id}
              className="bg-white border border-[#E1E4E8] rounded-xl p-5 hover:border-[#FF6B35]/30 hover:shadow-sm transition-all cursor-pointer"
              onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
            >
              <div className="flex items-start gap-3">
                <Avatar
                  size={36}
                  className="!bg-[#0D1117] flex-shrink-0 cursor-pointer"
                  onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author.id}`); }}
                >
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
                      <span
                        className="font-medium text-[#5F6B7A] cursor-pointer hover:text-[#FF6B35]"
                        onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author.id}`); }}
                      >{post.author.nickname}</span>
                      <span className="w-1 h-1 rounded-full bg-[#E1E4E8]" />
                      <span>{post.createdAt}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-[#8B949E]">
                      <span className="inline-flex items-center gap-1">
                        <LikeOutlined /> {post.likes}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <MessageOutlined /> {post.comments}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default FeedPage;