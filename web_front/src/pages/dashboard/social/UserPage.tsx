import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Avatar from 'antd/es/avatar';
import App from 'antd/es/app';
import Tabs from 'antd/es/tabs';
import Spin from 'antd/es/spin';
import Empty from 'antd/es/empty';
import {
  ArrowLeftOutlined,
  MessageOutlined,
  UserAddOutlined,
  UserOutlined,
  LikeOutlined,
  FireOutlined,
  EnvironmentOutlined,
  SmileOutlined,
  FileTextOutlined,
} from '@/components/icons';
import { getUserPublicProfile, followUser, unfollowUser } from '@/lib/api/user';
import type { UserPublicProfileResponse, UserCardResponse } from '@/lib/api/user';
import { listPosts } from '@/lib/api/posts';
import { useAppStore } from '@/store';
import type { PostListItem } from '@/types';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

/** 格式化时间为相对时间展示 */
function formatTime(dateStr: string): string {
  return dayjs(dateStr).fromNow();
}

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
  const [posts, setPosts] = useState<PostListItem[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [postsCursor, setPostsCursor] = useState<number | undefined>(undefined);
  const [postsHasMore, setPostsHasMore] = useState(true);

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
            isFollowing: full.is_following,
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

  /** 获取用户帖子列表 */
  const fetchPosts = useCallback(async (resetCursor?: boolean) => {
    if (!id) return;
    setPostsLoading(true);
    try {
      const cur = resetCursor ? undefined : postsCursor;
      const res = await listPosts({ author_id: Number(id), cursor: cur, limit: 20, sort: 'latest' });
      if (resetCursor || cur === undefined) {
        setPosts(res.items);
      } else {
        setPosts((prev) => [...prev, ...res.items]);
      }
      setPostsCursor(res.next_cursor ?? undefined);
      setPostsHasMore(res.next_cursor !== null);
    } catch {
      msgFn.error('加载帖子列表失败');
    } finally {
      setPostsLoading(false);
    }
  }, [id, postsCursor, msgFn]);

  useEffect(() => {
    if (profile && !profile.isCard) {
      fetchPosts(true);
    }
  }, [profile?.id]);

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
        <div className="w-16 h-16 rounded-2xl bg-[#F7F8FA] flex items-center justify-center mb-4">
          <UserOutlined className="text-2xl text-[#999999]" />
        </div>
        <h2 className="text-lg font-bold text-[#232529] mb-2">用户不存在</h2>
        <p className="text-sm text-[#666666] mb-6">该用户可能已注销或链接无效</p>
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
          className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-lg font-bold text-[#232529]">用户主页</h1>
      </div>

      <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6 mb-4">
        <div className="flex flex-col items-center text-center">
          <Avatar size={80} src={profile.avatar} className="!bg-[#232529] !text-2xl !font-bold mb-4">
            {profile.nickname[0]}
          </Avatar>

          <h2 className="text-xl font-extrabold text-[#232529] mb-4">{profile.nickname}</h2>

          {profile.isCard ? (
            <p className="text-sm text-[#999999] mb-5">该用户设置了隐私保护</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 mb-5 px-2">
                {profile.location && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-[#666666]">
                    <EnvironmentOutlined className="text-[#00B578]" />
                    {profile.location}
                  </span>
                )}
                {profile.bio && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-[#666666]">
                    <SmileOutlined className="text-[#FFAA00]" />
                    {profile.bio}
                  </span>
                )}
              </div>
            </>
          )}

          <div className="flex items-center gap-8 mb-5">
            <div className="text-center">
              <div className="text-lg font-bold text-[#232529]">{profile.followingCount}</div>
              <div className="text-xs text-[#999999]">关注</div>
            </div>
            <div className="w-px h-8 bg-[#E8E8E8]" />
            <div className="text-center">
              <div className="text-lg font-bold text-[#232529]">{profile.followersCount}</div>
              <div className="text-xs text-[#999999]">粉丝</div>
            </div>
            <div className="w-px h-8 bg-[#E8E8E8]" />
            <div className="text-center">
              <div className="text-lg font-bold text-[#232529]">{profile.postsCount}</div>
              <div className="text-xs text-[#999999]">帖子</div>
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

      {!profile.isCard && (
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6">
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key)}
            items={[
              {
                key: 'posts',
                label: (
                  <span className="inline-flex items-center gap-1.5">
                    <FileTextOutlined />
                    帖子
                  </span>
                ),
                children: (
                  <div className="-mx-2">
                    {postsLoading && posts.length === 0 ? (
                      <div className="flex justify-center py-12">
                        <Spin size="small" />
                      </div>
                    ) : posts.length === 0 ? (
                      <Empty description="暂无帖子" className="py-8" />
                    ) : (
                      <div className="space-y-3">
                        {posts.map((post) => (
                          <div
                            key={post.id}
                            className="border border-[#E8E8E8] rounded-xl p-4 hover:border-[#D9A441]/30 hover:shadow-sm transition-all cursor-pointer"
                            onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
                          >
                            <div className="flex items-center gap-2 mb-1.5">
                              <h4 className="text-sm font-semibold text-[#232529] truncate">{post.title}</h4>
                              {post.is_hot && (
                                <span className="tag tag-flame">
                                  <FireOutlined className="text-[10px]" /> 热
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-[#666666] line-clamp-2 mb-3">{post.content_preview || post.title}</p>
                            <div className="flex items-center gap-4 text-xs text-[#999999]">
                              <span className="inline-flex items-center gap-1">
                                <LikeOutlined /> {post.likes_count}
                              </span>
                              <span className="inline-flex items-center gap-1">
                                <MessageOutlined /> {post.comments_count}
                              </span>
                              <span>{formatTime(post.created_at)}</span>
                            </div>
                          </div>
                        ))}
                        {postsHasMore && (
                          <div className="flex justify-center py-3">
                            <button
                              onClick={() => fetchPosts()}
                              disabled={postsLoading}
                              className="text-sm text-[#D9A441] hover:text-[#A97E24] disabled:opacity-50"
                            >
                              {postsLoading ? '加载中...' : '加载更多'}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ),
              },
            ]}
            className="user-profile-tabs"
          />
        </div>
      )}
    </div>
  );
};

export default UserPage;