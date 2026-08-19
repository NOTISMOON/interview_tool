import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Avatar, App, Tabs, Spin } from 'antd';
import {
  ArrowLeftOutlined,
  MessageOutlined,
  UserAddOutlined,
  UserOutlined,
  LikeOutlined,
  CommentOutlined,
  TeamOutlined,
  FileTextOutlined,
  ManOutlined,
  WomanOutlined,
  EnvironmentOutlined,
  CalendarOutlined,
  SmileOutlined,
} from '@ant-design/icons';
import { getUserPublicProfile, followUser, unfollowUser } from '@/lib/api/user';
import type { UserPublicProfileResponse, UserCardResponse } from '@/lib/api/user';
import { useAppStore } from '@/store';
import type { CommunityPost, ActivityItem } from '@/types';

/** 前端用户资料展示类型 */
interface UserProfileView {
  id: string;
  nickname: string;
  avatar?: string;
  bio: string;
  location?: string;
  followingCount: number;
  followersCount: number;
  postsCount: number;
  isFollowing: boolean;
  isCard: boolean; // 是否为受限卡片
}

const UserPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message: msgFn } = App.useApp();
  const { user: currentUser } = useAppStore();
  const [activeTab, setActiveTab] = useState('posts');
  const [profile, setProfile] = useState<UserProfileView | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const isSelf = currentUser?.id === id;

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setNotFound(false);
    getUserPublicProfile(Number(id))
      .then((res) => {
        // 判断是完整公开资料还是受限卡片
        if ('bio' in res && 'following_count' in res) {
          const full = res as UserPublicProfileResponse;
          setProfile({
            id: String(full.id),
            nickname: full.nickname,
            avatar: full.avatar || undefined,
            bio: full.bio || '',
            location: full.location || undefined,
            followingCount: full.following_count,
            followersCount: full.followers_count,
            postsCount: full.posts_count,
            isFollowing: false,
            isCard: false,
          });
        } else {
          const card = res as UserCardResponse;
          setProfile({
            id: String(card.id),
            nickname: card.nickname,
            avatar: card.avatar || undefined,
            bio: '',
            followingCount: 0,
            followersCount: 0,
            postsCount: 0,
            isFollowing: false,
            isCard: true,
          });
        }
      })
      .catch(() => {
        setNotFound(true);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const handleFollow = async () => {
    if (!profile) return;
    try {
      if (profile.isFollowing) {
        await unfollowUser(Number(profile.id));
        setProfile((prev) => prev ? { ...prev, isFollowing: false, followersCount: prev.followersCount - 1 } : null);
        msgFn.success('已取消关注');
      } else {
        await followUser(Number(profile.id));
        setProfile((prev) => prev ? { ...prev, isFollowing: true, followersCount: prev.followersCount + 1 } : null);
        msgFn.success('已关注');
      }
    } catch {
      msgFn.error('操作失败，请重试');
    }
  };

  const handleMessage = () => {
    navigate(`/dashboard/messages/chat/${profile?.id}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spin size="large" />
      </div>
    );
  }

  if (notFound || !profile) {
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
          <Avatar size={80} src={profile.avatar} className="!bg-[#0D1117] !text-2xl !font-bold mb-4">
            {profile.nickname[0]}
          </Avatar>

          <h2 className="text-xl font-extrabold text-[#0D1117] mb-4">{profile.nickname}</h2>

          {profile.isCard ? (
            <p className="text-sm text-[#8B949E] mb-5">该用户设置了隐私保护</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 mb-5 px-2">
                {profile.location && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-[#5F6B7A]">
                    <EnvironmentOutlined className="text-[#2DA44E]" />
                    {profile.location}
                  </span>
                )}
                {profile.bio && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-[#5F6B7A]">
                    <SmileOutlined className="text-[#BF8700]" />
                    {profile.bio}
                  </span>
                )}
              </div>
            </>
          )}

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

          {!isSelf && (
            <div className="flex items-center gap-3">
              <button
                onClick={handleFollow}
                className={profile.isFollowing ? 'btn-ghost' : 'btn-flame'}
              >
                <UserAddOutlined /> {profile.isFollowing ? '已关注' : '关注'}
              </button>
              <button onClick={handleMessage} className="btn-flame">
                <MessageOutlined /> 私信
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UserPage;