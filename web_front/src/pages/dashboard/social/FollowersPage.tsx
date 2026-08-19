import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar, App, Spin } from 'antd';
import { ArrowLeftOutlined, TeamOutlined } from '@ant-design/icons';
import { getMyFollowers, followUser, unfollowUser } from '@/lib/api/user';
import type { FollowItemResponse } from '@/lib/api/user';
import type { UserBrief } from '@/types';

/** 将后端FollowItemResponse映射为前端UserBrief */
function mapFollowItem(item: FollowItemResponse): UserBrief {
  return {
    id: String(item.id),
    nickname: item.nickname,
    avatar: item.avatar || undefined,
    bio: item.bio || '',
    isFollowing: item.is_following,
    isFollowedBy: true,
  };
}

const FollowersPage = () => {
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const [followersList, setFollowersList] = useState<UserBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [totalCount, setTotalCount] = useState(0);

  /** 加载粉丝列表 */
  const loadFollowers = useCallback(async (cursor?: number) => {
    try {
      const res = await getMyFollowers(cursor, 20);
      const items = res.items.map(mapFollowItem);
      if (cursor) {
        setFollowersList((prev) => [...prev, ...items]);
      } else {
        setFollowersList(items);
      }
      setNextCursor(res.next_cursor);
      setTotalCount(res.followers_count);
    } catch {
      msg.error('加载粉丝列表失败');
    }
  }, [msg]);

  useEffect(() => {
    setLoading(true);
    loadFollowers().finally(() => setLoading(false));
  }, [loadFollowers]);

  /** 加载更多 */
  const handleLoadMore = async () => {
    if (loadingMore || nextCursor === null) return;
    setLoadingMore(true);
    await loadFollowers(nextCursor);
    setLoadingMore(false);
  };

  const handleToggleFollow = async (userId: string) => {
    const user = followersList.find((u) => u.id === userId);
    if (!user) return;
    try {
      if (user.isFollowing) {
        await unfollowUser(Number(userId));
        setFollowersList((prev) =>
          prev.map((u) => (u.id === userId ? { ...u, isFollowing: false } : u)),
        );
        msg.success('已取消关注');
      } else {
        await followUser(Number(userId));
        setFollowersList((prev) =>
          prev.map((u) => (u.id === userId ? { ...u, isFollowing: true } : u)),
        );
        msg.success('已关注');
      }
    } catch {
      msg.error('操作失败，请重试');
    }
  };

  const handleUserClick = (userId: string) => {
    navigate(`/dashboard/user/${userId}`);
  };

  const getButtonContent = (user: UserBrief) => {
    if (user.isFollowing && user.isFollowedBy) {
      return { text: '互相关注', className: 'bg-[#FFF3ED] text-[#FF6B35] border border-[#FF6B35]/20' };
    }
    if (user.isFollowing) {
      return { text: '已关注', className: 'bg-[#F6F8FA] text-[#5F6B7A] border border-[#E1E4E8] hover:border-[#CF222E] hover:text-[#CF222E] hover:bg-[#FFF0F1]' };
    }
    if (user.isFollowedBy) {
      return { text: '回关', className: 'btn-flame !py-1.5 !px-4 !text-sm' };
    }
    return { text: '关注', className: 'btn-flame !py-1.5 !px-4 !text-sm' };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="max-w-[700px]">
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/dashboard/profile')}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#0D1117]">我的粉丝 ({totalCount})</h1>
      </div>

      {followersList.length === 0 ? (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mx-auto mb-4">
            <TeamOutlined className="text-2xl text-[#8B949E]" />
          </div>
          <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无粉丝</h3>
          <p className="text-sm text-[#5F6B7A] mb-6">积极参与社区互动，吸引更多关注</p>
          <button onClick={() => navigate('/dashboard/community')} className="btn-flame">
            去社区互动
          </button>
        </div>
      ) : (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl overflow-hidden">
          {followersList.map((user, idx) => {
            const btn = getButtonContent(user);
            return (
              <div key={user.id}>
                {idx > 0 && <div className="border-t border-[#F0F2F5]" />}
                <div className="flex items-center gap-4 px-5 py-4 hover:bg-[#F6F8FA] transition-colors">
                  <Avatar
                    size={44}
                    src={user.avatar}
                    className="!bg-[#0D1117] flex-shrink-0 !text-sm cursor-pointer"
                    onClick={() => handleUserClick(user.id)}
                  >
                    {user.nickname[0]}
                  </Avatar>
                  <div
                    className="flex-1 min-w-0 cursor-pointer"
                    onClick={() => handleUserClick(user.id)}
                  >
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-semibold text-[#0D1117] truncate">{user.nickname}</h4>
                      {user.isFollowedBy && (
                        <span className="tag tag-ink text-[10px]">关注了你</span>
                      )}
                    </div>
                    <p className="text-xs text-[#5F6B7A] truncate mt-0.5">{user.bio}</p>
                  </div>
                  <button
                    onClick={() => handleToggleFollow(user.id)}
                    className={`flex-shrink-0 px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${btn.className}`}
                  >
                    {btn.text}
                  </button>
                </div>
              </div>
            );
          })}
          {nextCursor !== null && (
            <div className="border-t border-[#F0F2F5] p-4 text-center">
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="text-sm text-[#FF6B35] font-medium hover:text-[#E85D26] transition-colors"
              >
                {loadingMore ? '加载中...' : '加载更多'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FollowersPage;