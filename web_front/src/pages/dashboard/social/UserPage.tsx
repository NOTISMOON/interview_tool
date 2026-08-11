import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Avatar, App, Tabs } from 'antd';
import {
  ArrowLeftOutlined,
  MessageOutlined,
  UserAddOutlined,
  UserOutlined,
  LikeOutlined,
  CommentOutlined,
  FireOutlined,
  TeamOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { mockUserProfiles } from '@/lib/mocks/data';
import { useAppStore } from '@/store';
import type { UserProfile, CommunityPost, ActivityItem } from '@/types';

const UserPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message: msgFn } = App.useApp();
  const { user: currentUser } = useAppStore();
  const [activeTab, setActiveTab] = useState('posts');

  const profile: UserProfile | undefined = id ? mockUserProfiles[id] : undefined;

  if (!profile) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mb-4">
          <UserOutlined className="text-2xl text-[#8B949E]" />
        </div>
        <h2 className="text-lg font-bold text-[#0D1117] mb-2">用户不存在</h2>
        <p className="text-sm text-[#5F6B7A] mb-6">该用户可能已注销或链接无效</p>
        <button onClick={() => navigate('/dashboard/community')} className="btn-flame">
          返回社区
        </button>
      </div>
    );
  }

  const isSelf = currentUser?.id === profile.id;

  const handleFollow = () => {
    msgFn.success(profile.isFollowing ? '已取消关注' : '已关注');
  };

  const handleMessage = () => {
    navigate(`/dashboard/messages/chat/${profile.id}`);
  };

  const handlePostClick = (post: CommunityPost) => {
    navigate(`/dashboard/community/post/${post.id}`);
  };

  const handleActivityClick = (activity: ActivityItem) => {
    if (activity.type === 'post' && activity.relatedId) {
      navigate(`/dashboard/community/post/${activity.relatedId}`);
    } else if (activity.type === 'comment' && activity.relatedId) {
      navigate(`/dashboard/community/post/${activity.relatedId}`);
    }
  };

  const getActivityIcon = (type: ActivityItem['type']) => {
    switch (type) {
      case 'like': return <LikeOutlined className="text-[#CF222E]" />;
      case 'comment': return <CommentOutlined className="text-[#2DA44E]" />;
      case 'follow': return <TeamOutlined className="text-[#0D1117]" />;
      case 'post': return <FileTextOutlined className="text-[#FF6B35]" />;
    }
  };

  const getActivityBg = (type: ActivityItem['type']) => {
    switch (type) {
      case 'like': return 'bg-[#FFF0F1]';
      case 'comment': return 'bg-[#ECFDF3]';
      case 'follow': return 'bg-[#F6F8FA]';
      case 'post': return 'bg-[#FFF3ED]';
    }
  };

  return (
    <div className="max-w-[700px] animate-fade-in">
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(-1)}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-lg font-bold text-[#0D1117]">用户主页</h1>
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 mb-4">
        <div className="flex flex-col items-center text-center">
          <Avatar size={80} className="!bg-[#0D1117] !text-2xl !font-bold mb-4">
            {profile.avatar ? (
              <img src={profile.avatar} alt="" className="w-full h-full rounded-full object-cover" />
            ) : (
              profile.nickname[0]
            )}
          </Avatar>

          <h2 className="text-xl font-extrabold text-[#0D1117] mb-1">{profile.nickname}</h2>
          <p className="text-sm text-[#5F6B7A] mb-5 max-w-[400px]">{profile.bio}</p>

          <div className="flex items-center gap-8 mb-5">
            <div className="text-center">
              <div className="text-lg font-bold text-[#0D1117]">{profile.followingCount}</div>
              <div className="text-xs text-[#8B949E]">关注</div>
            </div>
            <div className="w-px h-8 bg-[#E1E4E8]" />
            <div className="text-center">
              <div className="text-lg font-bold text-[#0D1117]">{profile.followersCount}</div>
              <div className="text-xs text-[#8B949E]">粉丝</div>
            </div>
            <div className="w-px h-8 bg-[#E1E4E8]" />
            <div className="text-center">
              <div className="text-lg font-bold text-[#0D1117]">{profile.postsCount}</div>
              <div className="text-xs text-[#8B949E]">帖子</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {isSelf ? (
              <button
                onClick={() => navigate('/dashboard/profile')}
                className="btn-ghost"
              >
                编辑资料
              </button>
            ) : (
              <>
                <button
                  onClick={handleFollow}
                  className={profile.isFollowing ? 'btn-ghost' : 'btn-flame'}
                >
                  {profile.isFollowing ? (
                    <>
                      <UserAddOutlined /> 已关注
                    </>
                  ) : (
                    <>
                      <UserAddOutlined /> 关注
                    </>
                  )}
                </button>
                <button
                  onClick={handleMessage}
                  className="btn-flame"
                >
                  <MessageOutlined /> 私信
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        className="mb-4"
        items={[
          { key: 'posts', label: <span className="text-sm">他的帖子</span> },
          { key: 'activities', label: <span className="text-sm">他的动态</span> },
        ]}
      />

      {activeTab === 'posts' && (
        <>
          {profile.posts.length === 0 ? (
            <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 text-center">
              <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mx-auto mb-4">
                <FileTextOutlined className="text-2xl text-[#8B949E]" />
              </div>
              <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无帖子</h3>
              <p className="text-sm text-[#5F6B7A]">该用户还没有发布任何帖子</p>
            </div>
          ) : (
            <div className="space-y-3">
              {profile.posts.map((post) => (
                <div
                  key={post.id}
                  className="bg-white border border-[#E1E4E8] rounded-xl p-5 hover:border-[#FF6B35]/30 hover:shadow-sm transition-all cursor-pointer"
                  onClick={() => handlePostClick(post)}
                >
                  <div className="flex items-center gap-2 mb-2">
                    {post.isHot && (
                      <span className="tag tag-flame">
                        <FireOutlined className="text-[10px]" /> 热门
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm font-semibold text-[#0D1117] mb-2">{post.title}</h3>
                  <p className="text-xs text-[#5F6B7A] line-clamp-2 mb-3">{post.content}</p>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {post.tags.map((tag) => (
                      <span key={tag} className="tag tag-flame">{tag}</span>
                    ))}
                  </div>
                  <div className="flex items-center gap-4 text-xs text-[#8B949E]">
                    <span className="inline-flex items-center gap-1">
                      <LikeOutlined /> {post.likes}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <CommentOutlined /> {post.comments}
                    </span>
                    <span>{post.views} 次浏览</span>
                    <span className="ml-auto">{post.createdAt}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {activeTab === 'activities' && (
        <>
          {profile.activities.length === 0 ? (
            <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 text-center">
              <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mx-auto mb-4">
                <TeamOutlined className="text-2xl text-[#8B949E]" />
              </div>
              <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无动态</h3>
              <p className="text-sm text-[#5F6B7A]">该用户还没有公开动态</p>
            </div>
          ) : (
            <div className="bg-white border border-[#E1E4E8] rounded-2xl overflow-hidden">
              {profile.activities.map((activity, idx) => (
                <div key={activity.id}>
                  {idx > 0 && <div className="border-t border-[#F0F2F5]" />}
                  <div
                    className={`flex items-center gap-3 px-5 py-3.5 hover:bg-[#F6F8FA] transition-colors ${
                      (activity.type === 'post' || activity.type === 'comment') && activity.relatedId
                        ? 'cursor-pointer'
                        : ''
                    }`}
                    onClick={() => handleActivityClick(activity)}
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${getActivityBg(activity.type)}`}>
                      {getActivityIcon(activity.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[#0D1117] truncate">{activity.content}</p>
                    </div>
                    <span className="text-xs text-[#8B949E] flex-shrink-0">{activity.createdAt}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default UserPage;