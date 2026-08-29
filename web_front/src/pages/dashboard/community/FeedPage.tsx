import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Avatar from 'antd/es/avatar';
import App from 'antd/es/app';
import Segmented from 'antd/es/segmented';
import Spin from 'antd/es/spin';
import Empty from 'antd/es/empty';
import {
  FireOutlined,
  LikeOutlined,
  MessageOutlined,
  UserAddOutlined,
  ReloadOutlined,
} from '@/components/icons';
import { getFeed } from '@/lib/api/feed';
import type { PostListItem } from '@/types';
import { useAppStore } from '@/store';
import { useTimelineLayout, useTimelineReveal } from '@/hooks/useTimelineLayout';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

/** 格式化时间为相对时间展示（超过7天显示具体日期） */
function formatTime(dateStr: string): string {
  const d = dayjs(dateStr);
  if (!d.isValid()) return dateStr;
  if (dayjs().diff(d, 'day') > 7) return d.format('YYYY-MM-DD HH:mm');
  return d.fromNow();
}

const FeedPage = () => {
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const { user } = useAppStore();
  const [filter, setFilter] = useState<string>('all');

  // 时间线布局模式（交错/单侧，localStorage 记忆）
  const { layout, setLayout, layoutClass } = useTimelineLayout('alt');

  const [posts, setPosts] = useState<PostListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState<number | undefined>(undefined);
  const [hasMore, setHasMore] = useState(true);

  // 时间线条目浮现动画
  useTimelineReveal([posts.length, filter, layout]);

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
            <h1 className="text-xl font-bold text-[#232529]">动态</h1>
            <p className="text-sm text-[#666666] mt-1">
              关注了 <span className="font-semibold text-[#D9A441]">{user?.followingCount ?? 0}</span> 人
            </p>
          </div>
          <button
            onClick={() => navigate('/dashboard/community')}
            className="btn-ghost"
          >
            <UserAddOutlined /> 发现更多
          </button>
        </div>

        <div className="mb-5 flex items-center justify-between">
          <Segmented
            value={filter}
            onChange={(val) => setFilter(val as string)}
            options={[
              { label: '全部动态', value: 'all' },
              { label: '热门', value: 'hot', icon: <FireOutlined /> },
            ]}
            className="!bg-[#F7F8FA] !p-1 !rounded-xl"
          />
          {/* 时间线布局切换：交错 / 单侧 */}
          <div className="flex items-center gap-0.5 bg-[#F7F8FA] border border-[#E8E8E8] rounded-lg p-0.5">
            <button
              onClick={() => setLayout('alt')}
              className={`px-2.5 py-1 text-xs rounded-md transition-all ${layout === 'alt' ? 'bg-white text-[#D9A441] font-semibold shadow-sm' : 'text-[#999999] hover:text-[#666666]'}`}
            >
              交错
            </button>
            <button
              onClick={() => setLayout('single')}
              className={`px-2.5 py-1 text-xs rounded-md transition-all ${layout === 'single' ? 'bg-white text-[#D9A441] font-semibold shadow-sm' : 'text-[#999999] hover:text-[#666666]'}`}
            >
              单侧
            </button>
          </div>
        </div>
      </div>

      {loading && posts.length === 0 ? (
        <div className="flex justify-center py-16">
          <Spin size="large" />
        </div>
      ) : filteredPosts.length === 0 ? (
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#F7F8FA] flex items-center justify-center mx-auto mb-4">
            <ReloadOutlined className="text-2xl text-[#999999]" />
          </div>
          <h3 className="text-base font-semibold text-[#232529] mb-2">暂无动态</h3>
          <p className="text-sm text-[#666666] mb-6">
            {user?.followingCount === 0
              ? '你还没有关注任何人，去社区发现有趣的用户吧'
              : '你关注的人还没有发布新内容'}
          </p>
          <button onClick={() => navigate('/dashboard/community')} className="btn-flame">
            去社区看看
          </button>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div className={`timeline pb-4 ${layoutClass}`}>
            {filteredPosts.map((post) => (
              <div key={post.id} className="tl-item">
                {/* 节点：热帖橙色，普通动态灰色 */}
                <div className={`tl-node ${post.is_hot ? 'hot' : 'event'}`}>
                  <span className="ring" />
                  <span className="pulse" />
                </div>
                {/* 轻量动态卡片 */}
                <div
                  className="tl-card cursor-pointer"
                  onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
                >
                  <div className="flex items-start gap-3">
                    <Avatar
                      size={32}
                      src={post.author?.avatar}
                      className="!bg-[#232529] flex-shrink-0"
                      onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                    >{post.author?.nickname?.[0] || '?'}</Avatar>
                    <div className="flex-1 min-w-0">
                      <div className="text-[13.5px] text-[#232529] leading-relaxed">
                        <span
                          className="font-semibold cursor-pointer hover:text-[#D9A441] transition-colors"
                          onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                        >{post.author?.nickname || '未知用户'}</span>
                        <span className="text-[#666666]"> 发布了新帖子 </span>
                        <span className="text-[#D9A441] font-semibold">《{post.title}》</span>
                      </div>
                      <div className="text-[11.5px] text-[#999999] mt-1.5 flex items-center gap-3">
                        <span>{formatTime(post.created_at)}</span>
                        <span className="inline-flex items-center gap-1">
                          <LikeOutlined /> {post.likes_count}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <MessageOutlined /> {post.comments_count}
                        </span>
                        {post.is_hot && (
                          <span className="tag tag-flame !text-[10px] !px-1.5 !py-px">
                            <FireOutlined className="text-[10px]" /> 热
                          </span>
                        )}
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
                  className="text-sm text-[#D9A441] hover:text-[#A97E24] disabled:opacity-50"
                >
                  {loading ? '加载中...' : '加载更多'}
                </button>
              </div>
            )}
            {!hasMore && filteredPosts.length > 0 && (
              <div className="text-center py-4 text-xs text-[#999999]">— 已加载全部动态 —</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default FeedPage;