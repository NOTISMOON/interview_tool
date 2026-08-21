import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Avatar, App, Spin, Empty, Modal } from 'antd';
import {
  ArrowLeftOutlined,
  LikeOutlined,
  LikeFilled,
  StarOutlined,
  StarFilled,
  MessageOutlined,
  ShareAltOutlined,
  FireOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useAppStore } from '@/store';
import { getPostDetail, deletePost } from '@/lib/api/posts';
import { toggleLike, toggleFavorite } from '@/lib/api/interactions';
import { createComment, listComments } from '@/lib/api/comments';
import type { PostDetail, PostComment } from '@/types';
import { buildCosUrl } from '@/utils/cos';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

/** 格式化时间为相对时间展示 */
function formatTime(dateStr: string): string {
  return dayjs(dateStr).fromNow();
}

const PostDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message: msg, modal } = App.useApp();
  const { user } = useAppStore();

  const [post, setPost] = useState<PostDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const [isLiked, setIsLiked] = useState(false);
  const [isFavorited, setIsFavorited] = useState(false);
  const [likesCount, setLikesCount] = useState(0);

  const [comments, setComments] = useState<PostComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(true);
  const [commentText, setCommentText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  /** 获取帖子详情 */
  const fetchPost = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getPostDetail(Number(id));
      setPost(data);
      setIsLiked(data.is_liked);
      setIsFavorited(data.is_favorited);
      setLikesCount(data.likes_count);
      setNotFound(false);
    } catch {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  };

  /** 获取评论列表 */
  const fetchComments = async () => {
    if (!id) return;
    setCommentsLoading(true);
    try {
      const data = await listComments(Number(id), { limit: 20, sort: 'latest' });
      setComments(data.items);
    } catch {
      msg.error('加载评论失败');
    } finally {
      setCommentsLoading(false);
    }
  };

  useEffect(() => {
    fetchPost();
    fetchComments();
  }, [id]);

  /** 点赞/取消点赞 */
  const handleLike = async () => {
    if (!id) return;
    try {
      const res = await toggleLike(Number(id));
      setIsLiked(res.is_liked);
      setLikesCount(res.likes_count);
    } catch {
      msg.error('操作失败');
    }
  };

  /** 收藏/取消收藏 */
  const handleFavorite = async () => {
    if (!id) return;
    try {
      const res = await toggleFavorite(Number(id));
      setIsFavorited(res.is_favorited);
      msg.success(res.is_favorited ? '已收藏' : '已取消收藏');
    } catch {
      msg.error('操作失败');
    }
  };

  /** 发表评论 */
  const handleComment = async () => {
    if (!commentText.trim()) {
      msg.warning('请输入评论内容');
      return;
    }
    if (!id) return;
    setSubmitting(true);
    try {
      await createComment(Number(id), { content: commentText.trim() });
      msg.success('评论发表成功');
      setCommentText('');
      fetchComments();
      if (post) {
        setPost({ ...post, comments_count: post.comments_count + 1 });
      }
    } catch {
      msg.error('评论失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  /** 删除帖子 */
  const handleDelete = () => {
    modal.confirm({
      title: '删除帖子',
      icon: <ExclamationCircleOutlined />,
      content: '确定要删除这个帖子吗？删除后无法恢复。',
      okText: '确定删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (!id) return;
        try {
          await deletePost(Number(id));
          msg.success('帖子已删除');
          navigate('/dashboard/community');
        } catch {
          msg.error('删除失败，请稍后重试');
        }
      },
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spin size="large" />
      </div>
    );
  }

  if (notFound || !post) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <h2 className="text-lg font-bold text-[#0D1117] mb-2">帖子不存在</h2>
        <p className="text-sm text-[#5F6B7A] mb-6">该帖子可能已被删除或链接无效</p>
        <button onClick={() => navigate('/dashboard/community')} className="btn-flame">
          返回社区
        </button>
      </div>
    );
  }

  const isAuthor = user?.id === String(post.author?.id);

  return (
    <div className="max-w-[800px]">
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/dashboard/community')}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-lg font-bold text-[#0D1117]">帖子详情</h1>
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 mb-4">
        <div className="flex items-center gap-2 mb-3">
          {post.is_hot && <span className="tag tag-flame"><FireOutlined className="text-[10px]" /> 热门</span>}
        </div>

        <h1 className="text-xl font-extrabold text-[#0D1117] mb-4 leading-snug">
          {post.title}
        </h1>

        <div className="flex items-center gap-3 mb-5">
          <Avatar
            size={40}
            className="!bg-[#0D1117] flex-shrink-0 !text-base cursor-pointer"
            onClick={() => navigate(`/dashboard/user/${post.author?.id}`)}
          >
            {post.author?.nickname?.[0] || '?'}
          </Avatar>
          <div className="flex-1">
            <div
              className="text-sm font-semibold text-[#0D1117] cursor-pointer hover:text-[#FF6B35]"
              onClick={() => navigate(`/dashboard/user/${post.author?.id}`)}
            >{post.author?.nickname || '未知用户'}</div>
            <div className="text-xs text-[#8B949E]">{formatTime(post.created_at)}</div>
          </div>
          {isAuthor && (
            <button
              onClick={handleDelete}
              className="text-xs text-[#8B949E] hover:text-[#CF222E] transition-colors flex items-center gap-1"
            >
              <DeleteOutlined /> 删除
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2 mb-5">
          {post.tags.map((tag) => (
            <span key={tag} className="tag tag-flame">{tag}</span>
          ))}
        </div>

        <div className="text-sm text-[#0D1117] leading-relaxed whitespace-pre-line mb-6">
          {post.content}
        </div>

        {post.images && post.images.length > 0 && (
          <div className="grid grid-cols-2 gap-3 mb-6">
            {post.images.map((img, idx) => (
              <img
                key={idx}
                src={buildCosUrl(img)}
                alt={`帖子图片-${idx + 1}`}
                className="w-full rounded-xl object-cover max-h-[400px] border border-[#E1E4E8] cursor-pointer hover:opacity-90 transition-opacity"
                onClick={() => window.open(buildCosUrl(img), '_blank')}
              />
            ))}
          </div>
        )}

        <div className="flex items-center gap-4 text-sm text-[#8B949E] pb-5 border-b border-[#F0F2F5]">
          <span className="inline-flex items-center gap-1">
            <LikeOutlined /> {likesCount}
          </span>
          <span className="inline-flex items-center gap-1">
            <MessageOutlined /> {post.comments_count}
          </span>
          <span className="inline-flex items-center gap-1">
            {post.views_count} 次浏览
          </span>
        </div>

        <div className="flex items-center justify-between pt-4">
          <div className="flex items-center gap-2">
            <button
              onClick={handleLike}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                isLiked
                  ? 'bg-[#FFF3ED] text-[#FF6B35]'
                  : 'bg-[#F6F8FA] text-[#5F6B7A] hover:bg-[#FFF3ED] hover:text-[#FF6B35]'
              }`}
            >
              {isLiked ? <LikeFilled /> : <LikeOutlined />}
              {isLiked ? '已赞' : '点赞'}
            </button>
            <button
              onClick={() => msg.info('分享功能即将上线')}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-[#F6F8FA] text-[#5F6B7A] hover:bg-[#F0F2F5] transition-all"
            >
              <ShareAltOutlined /> 分享
            </button>
          </div>
          <button
            onClick={handleFavorite}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              isFavorited
                ? 'bg-[#FFF8E6] text-[#BF8700]'
                : 'bg-[#F6F8FA] text-[#5F6B7A] hover:bg-[#FFF8E6] hover:text-[#BF8700]'
            }`}
          >
            {isFavorited ? <StarFilled /> : <StarOutlined />}
            {isFavorited ? '已收藏' : '收藏'}
          </button>
        </div>
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 mb-4">
        <h3 className="text-sm font-bold text-[#0D1117] mb-4 flex items-center gap-2">
          <MessageOutlined className="text-[#FF6B35]" />
          评论 ({comments.length})
        </h3>
        {commentsLoading ? (
          <div className="flex justify-center py-8">
            <Spin size="small" />
          </div>
        ) : comments.length === 0 ? (
          <Empty description="暂无评论，快来抢沙发" className="py-4" />
        ) : (
          <div className="space-y-4">
            {comments.map((comment) => (
              <div key={comment.id} className="flex gap-3">
                <Avatar size={32} className="!bg-[#0D1117] flex-shrink-0 !text-xs">
                  {comment.author?.nickname?.[0] || '?'}
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-[#0D1117]">{comment.author?.nickname || '未知用户'}</span>
                    <span className="text-xs text-[#8B949E]">{formatTime(comment.created_at)}</span>
                  </div>
                  <p className="text-sm text-[#0D1117] leading-relaxed">{comment.content}</p>
                  <div className="flex items-center gap-3 mt-2">
                    <button
                      onClick={() => msg.info('评论点赞功能即将上线')}
                      className="text-xs text-[#8B949E] hover:text-[#FF6B35] transition-colors inline-flex items-center gap-1"
                    >
                      <LikeOutlined /> {comment.likes_count}
                    </button>
                    <button
                      onClick={() => msg.info('回复功能即将上线')}
                      className="text-xs text-[#8B949E] hover:text-[#0D1117] transition-colors"
                    >
                      回复
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6">
        <h3 className="text-sm font-bold text-[#0D1117] mb-4">发表评论</h3>
        <div className="flex gap-3">
          <Avatar size={32} className="!bg-[#FF6B35] flex-shrink-0 !text-xs">{user?.nickname?.[0] || 'U'}</Avatar>
          <div className="flex-1">
            <textarea
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="写下你的评论..."
              className="w-full px-4 py-3 border border-[#E1E4E8] rounded-xl text-sm text-[#0D1117] placeholder:text-[#8B949E] resize-none focus:outline-none focus:border-[#FF6B35] focus:ring-1 focus:ring-[#FF6B35]/20 transition-all min-h-[80px]"
            />
            <div className="flex justify-end mt-3">
              <button
                onClick={handleComment}
                disabled={!commentText.trim() || submitting}
                className="btn-flame !py-2 !px-5 !text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? '发表中...' : '发表评论'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PostDetailPage;