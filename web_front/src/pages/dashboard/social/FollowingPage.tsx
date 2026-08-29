import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Avatar from 'antd/es/avatar';
import App from 'antd/es/app';
import Spin from 'antd/es/spin';
import { ArrowLeftOutlined, TeamOutlined } from '@/components/icons';
import { getMyFollowing, unfollowUser } from '@/lib/api/user';
import type { FollowItemResponse } from '@/lib/api/user';
import type { UserBrief } from '@/types';

/** 将后端FollowItemResponse映射为前端UserBrief */
function mapFollowItem(item: FollowItemResponse): UserBrief {
  return {
    id: String(item.id),
    nickname: item.nickname,
    avatar: item.avatar || undefined,
    bio: item.bio || '',
    isFollowing: true,
    isFollowedBy: item.is_mutual,
  };
}

const FollowingPage = () => {
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const [followingList, setFollowingList] = useState<UserBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [totalCount, setTotalCount] = useState(0);

  /** 加载关注列表 */
  const loadFollowing = useCallback(async (cursor?: number) => {
    try {
      const res = await getMyFollowing(cursor, 20);
      const items = res.items.map(mapFollowItem);
      if (cursor) {
        setFollowingList((prev) => [...prev, ...items]);
      } else {
        setFollowingList(items);
      }
      setNextCursor(res.next_cursor);
      setTotalCount(res.following_count);
    } catch {
      msg.error('加载关注列表失败');
    }
  }, [msg]);

  useEffect(() => {
    setLoading(true);
    loadFollowing().finally(() => setLoading(false));
  }, [loadFollowing]);

  /** 加载更多 */
  const handleLoadMore = async () => {
    if (loadingMore || nextCursor === null) return;
    setLoadingMore(true);
    await loadFollowing(nextCursor);
    setLoadingMore(false);
  };

  const handleToggleFollow = async (userId: string) => {
    try {
      await unfollowUser(Number(userId));
      setFollowingList((prev) => prev.filter((u) => u.id !== userId));
      setTotalCount((prev) => prev - 1);
      msg.success('已取消关注');
    } catch {
      msg.error('操作失败，请重试');
    }
  };

  const handleUserClick = (userId: string) => {
    navigate(`/dashboard/user/${userId}`);
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
          className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#232529]">我的关注 ({totalCount})</h1>
      </div>

      {followingList.length === 0 ? (
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#F7F8FA] flex items-center justify-center mx-auto mb-4">
            <TeamOutlined className="text-2xl text-[#999999]" />
          </div>
          <h3 className="text-base font-semibold text-[#232529] mb-2">尚未关注任何人</h3>
          <p className="text-sm text-[#666666] mb-6">去社区发现有趣的用户并关注他们吧</p>
          <button onClick={() => navigate('/dashboard/community')} className="btn-flame">
            去社区看看
          </button>
        </div>
      ) : (
        <div className="bg-white border border-[#E8E8E8] rounded-2xl overflow-hidden">
          {followingList.map((user, idx) => (
            <div key={user.id}>
              {idx > 0 && <div className="border-t border-[#F2F3F5]" />}
              <div className="flex items-center gap-4 px-5 py-4 hover:bg-[#F7F8FA] transition-colors">
                <Avatar
                  size={44}
                  src={user.avatar}
                  className="!bg-[#232529] flex-shrink-0 !text-sm cursor-pointer"
                  onClick={() => handleUserClick(user.id)}
                >
                  {user.nickname[0]}
                </Avatar>
                <div
                  className="flex-1 min-w-0 cursor-pointer"
                  onClick={() => handleUserClick(user.id)}
                >
                  <h4 className="text-sm font-semibold text-[#232529] truncate">{user.nickname}</h4>
                  <p className="text-xs text-[#666666] truncate mt-0.5">{user.bio}</p>
                </div>
                <button
                  onClick={() => handleToggleFollow(user.id)}
                  className="flex-shrink-0 px-4 py-1.5 rounded-lg text-sm font-medium transition-all bg-[#F7F8FA] text-[#666666] border border-[#E8E8E8] hover:border-[#F53535] hover:text-[#F53535] hover:bg-[#FDECEC]"
                >
                  已关注
                </button>
              </div>
            </div>
          ))}
          {nextCursor !== null && (
            <div className="border-t border-[#F2F3F5] p-4 text-center">
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="text-sm text-[#D9A441] font-medium hover:text-[#A97E24] transition-colors"
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

export default FollowingPage;