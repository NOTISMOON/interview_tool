import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar, App, Segmented, Spin, Empty } from 'antd';
import {
  FireOutlined,
  LikeOutlined,
  MessageOutlined,
  UserAddOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { getFeed } from '@/lib/api/feed';
import type { PostListItem } from '@/types';
import { useAppStore } from '@/store';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

/** 格式化时间为相对时间展示 */
function formatTime(dateStr: string): string {
  return dayjs(dateStr).fromNow();
}

const FeedPage = () => {
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const { user } = useAppStore();
  const [filter, setFilter] = useState<string>('all');

  const [posts, setPosts] = useState<PostListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState<number | undefined>(undefined);
  const [hasMore, setHasMore] = useState(true);

  /** 获取Feed信息流 */
  const fetchFeed = useCallback(async (resetCursor?: boolean) => {
    setLoading(true);
    try {
      const cur = resetCursor ? undefined : cursor;
      const res = await getFeed({ cursor: cur, limit: 20 });
      if (resetCursor || cur === undefined) {
        setPosts(res.items);
      } else {
        setPosts((prev) => [...prev, ...res.items]);
      }
      setCursor(res.next_cursor ?? undefined);
      setHasMore(res.next_cursor !== null);
    } catch {
      msg.error('加载动态失败');
    } finally {
      setLoading(false);
    }
  }, [cursor, msg]);

  useEffect(() => {
    fetchFeed(true);
  }, []);

  /** 根据筛选条件过滤 */
  const filteredPosts = filter === 'hot'
    ? posts.filter((p) => p.is_hot)
    : posts;

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

      {loading && posts.length === 0 ? (
        <div className="flex justify-center py-16">
          <Spin size="large" />
        </div>
      ) : filteredPosts.length === 0 ? (
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
                  src={post.author?.avatar}
                  className="!bg-[#0D1117] flex-shrink-0 cursor-pointer"
                  onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                >
                  {post.author?.nickname?.[0] || '?'}
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <h4 className="text-sm font-semibold text-[#0D1117] truncate">{post.title}</h4>
                    {post.is_hot && (
                      <span className="tag tag-flame">
                        <FireOutlined className="text-[10px]" /> 热
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#5F6B7A] line-clamp-2 mb-3">{post.content_preview || post.title}</p>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-[#8B949E]">
                      <span
                        className="font-medium text-[#5F6B7A] cursor-pointer hover:text-[#FF6B35]"
                        onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                      >{post.author?.nickname || '未知用户'}</span>
                      <span className="w-1 h-1 rounded-full bg-[#E1E4E8]" />
                      <span>{formatTime(post.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-[#8B949E]">
                      <span className="inline-flex items-center gap-1">
                        <LikeOutlined /> {post.likes_count}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <MessageOutlined /> {post.comments_count}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
          {hasMore && (
            <div className="flex justify-center py-4">
              <button
                onClick={() => fetchFeed()}
                disabled={loading}
                className="text-sm text-[#FF6B35] hover:text-[#E85D26] disabled:opacity-50"
              >
                {loading ? '加载中...' : '加载更多'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FeedPage;