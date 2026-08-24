import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar, App, Spin, Empty } from 'antd';
import {
  ArrowLeftOutlined,
  StarFilled,
  LikeOutlined,
  MessageOutlined,
  FireOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { listFavorites, toggleFavorite } from '@/lib/api/interactions';
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
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#0D1117]">我的收藏</h1>
      </div>

      {loading && favorites.length === 0 ? (
        <div className="flex justify-center py-16">
          <Spin size="large" />
        </div>
      ) : favorites.length === 0 ? (
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
                <Avatar size={36} src={post.author?.avatar} className="!bg-[#0D1117] flex-shrink-0">
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
                      <span className="font-medium text-[#5F6B7A]">{post.author?.nickname || '未知用户'}</span>
                      <span className="w-1 h-1 rounded-full bg-[#E1E4E8]" />
                      <span>{formatTime(post.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-[#8B949E]">
                      <span className="inline-flex items-center gap-1"><LikeOutlined /> {post.likes_count}</span>
                      <span className="inline-flex items-center gap-1"><MessageOutlined /> {post.comments_count}</span>
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
                  disabled={removingId === post.id}
                  className="text-xs text-[#8B949E] hover:text-[#CF222E] transition-colors inline-flex items-center gap-1 opacity-0 group-hover:opacity-100 disabled:opacity-50"
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

export default FavoritesPage;