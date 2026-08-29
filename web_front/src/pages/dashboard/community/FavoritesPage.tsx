import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Avatar from 'antd/es/avatar';
import App from 'antd/es/app';
import Spin from 'antd/es/spin';
import Empty from 'antd/es/empty';
import {
  ArrowLeftOutlined,
  StarFilled,
  LikeOutlined,
  MessageOutlined,
  FireOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
} from '@/components/icons';
import { listFavorites, toggleFavorite } from '@/lib/api/interactions';
import type { PostListItem } from '@/types';
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

const FavoritesPage = () => {
  const navigate = useNavigate();
  const { message: msg, modal } = App.useApp();

  const [favorites, setFavorites] = useState<PostListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState<number | undefined>(undefined);
  const [hasMore, setHasMore] = useState(true);
  const [removingId, setRemovingId] = useState<number | null>(null);

  /** 获取收藏列表 */
  const fetchFavorites = useCallback(async (resetCursor?: boolean) => {
    setLoading(true);
    try {
      const cur = resetCursor ? undefined : cursor;
      const res = await listFavorites({ cursor: cur, limit: 20 });
      if (resetCursor || cur === undefined) {
        setFavorites(res.items);
      } else {
        setFavorites((prev) => [...prev, ...res.items]);
      }
      setCursor(res.next_cursor ?? undefined);
      setHasMore(res.next_cursor !== null);
    } catch {
      msg.error('加载收藏列表失败');
    } finally {
      setLoading(false);
    }
  }, [cursor, msg]);

  useEffect(() => {
    fetchFavorites(true);
  }, []);

  /** 取消收藏 */
  const handleRemove = (postId: number) => {
    modal.confirm({
      title: '取消收藏',
      icon: <ExclamationCircleOutlined />,
      content: '确定要取消收藏这个帖子吗？',
      okText: '确定',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setRemovingId(postId);
        try {
          await toggleFavorite(postId);
          setFavorites((prev) => prev.filter((p) => p.id !== postId));
          msg.success('已取消收藏');
        } catch {
          msg.error('操作失败，请稍后重试');
        } finally {
          setRemovingId(null);
        }
      },
    });
  };

  return (
    <div className="max-w-[700px] flex flex-col h-full">
      <div className="flex-shrink-0 flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/dashboard/profile')}
          className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#232529]">我的收藏</h1>
      </div>

      {loading && favorites.length === 0 ? (
        <div className="flex justify-center py-16">
          <Spin size="large" />
        </div>
      ) : favorites.length === 0 ? (
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#F7F8FA] flex items-center justify-center mx-auto mb-4">
            <StarFilled className="text-2xl text-[#999999]" />
          </div>
          <h3 className="text-base font-semibold text-[#232529] mb-2">暂无收藏</h3>
          <p className="text-sm text-[#666666] mb-6">去社区发现感兴趣的内容并收藏吧</p>
          <button onClick={() => navigate('/dashboard/community')} className="btn-flame">
            去社区看看
          </button>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          {favorites.map((post) => (
            <div
              key={post.id}
              className="bg-white border border-[#E8E8E8] rounded-xl p-5 hover:border-[#D9A441]/30 hover:shadow-sm transition-all group"
            >
              <div
                className="flex items-start gap-3 cursor-pointer"
                onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
              >
                <Avatar size={36} src={post.author?.avatar} className="!bg-[#232529] flex-shrink-0">
                  {post.author?.nickname?.[0] || '?'}
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <h4 className="text-sm font-semibold text-[#232529] truncate">{post.title}</h4>
                    {post.is_hot && (
                      <span className="tag tag-flame">
                        <FireOutlined className="text-[10px]" /> 热
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#666666] line-clamp-2 mb-3">{post.content_preview || post.title}</p>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-[#999999]">
                      <span className="font-medium text-[#666666]">{post.author?.nickname || '未知用户'}</span>
                      <span className="w-1 h-1 rounded-full bg-[#E8E8E8]" />
                      <span>{formatTime(post.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-[#999999]">
                      <span className="inline-flex items-center gap-1"><LikeOutlined /> {post.likes_count}</span>
                      <span className="inline-flex items-center gap-1"><MessageOutlined /> {post.comments_count}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex justify-end mt-3 pt-3 border-t border-[#F2F3F5]">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemove(post.id);
                  }}
                  disabled={removingId === post.id}
                  className="text-xs text-[#999999] hover:text-[#F53535] transition-colors inline-flex items-center gap-1 opacity-0 group-hover:opacity-100 disabled:opacity-50"
                >
                  <DeleteOutlined /> {removingId === post.id ? '取消中...' : '取消收藏'}
                </button>
              </div>
            </div>
          ))}
          {hasMore && (
            <div className="flex justify-center py-4">
              <button
                onClick={() => fetchFavorites()}
                disabled={loading}
                className="text-sm text-[#D9A441] hover:text-[#A97E24] disabled:opacity-50"
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

export default FavoritesPage;