import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Avatar, App } from 'antd';
import {
  ArrowLeftOutlined,
  LikeOutlined,
  LikeFilled,
  StarOutlined,
  StarFilled,
  MessageOutlined,
  ShareAltOutlined,
  FireOutlined,
  PushpinOutlined,
} from '@ant-design/icons';
import { mockPostDetailComments } from '@/lib/mocks/data';
import type { CommunityPost } from '@/types';

const MOCK_POSTS: CommunityPost[] = [
  {
    id: '1', title: '前端三年经验，面试字节挂了三次，求大佬指点',
    content: '三年 Vue 经验，最近在学 React，面试总挂在系统设计上。\n\n具体来说，我面的是字节的「高级前端工程师」岗位，一共面了三轮技术面加一轮 HR 面。\n\n**第一轮**：问了 Vue 和 React 的差异、虚拟 DOM、组件通信等基础问题，答得还可以。\n\n**第二轮**：开始问系统设计，让我设计一个实时协作编辑系统，我完全没准备过这类题目，答得很差。\n\n**第三轮**：问了性能优化和工程化相关，这部分我比较熟悉，答得不错。\n\n**总结**：\n1. 系统设计是我的薄弱环节，需要系统性地学习\n2. 面试前应该多看看面经，了解面试风格\n3. 心态要稳住，不要因为一题没答好就影响后面的发挥\n\n求各位大佬指点，系统设计应该怎么准备？有没有推荐的资料？',
    author: { id: 'u1', nickname: '前端小张', avatar: '' },
    tags: ['面试经验', '前端'], likes: 128, comments: 45, views: 2300,
    isPinned: true, isHot: true, createdAt: '10 分钟前',
  },
  {
    id: '2', title: 'AI 模拟面试真的有用！拿到 offer 了',
    content: '用这个工具练习了两周，面试时明显感觉更自信了，推荐大家都试试...',
    author: { id: 'u2', nickname: '上岸的鱼', avatar: '' },
    tags: ['经验分享', 'Offer'], likes: 256, comments: 89, views: 5600,
    isPinned: false, isHot: true, createdAt: '2 小时前',
  },
  {
    id: '3', title: '分享一套后端面试常见问题整理',
    content: '整理了最近面试遇到的 50 道高频题...',
    author: { id: 'u3', nickname: 'Go 夜读', avatar: '' },
    tags: ['资源分享', '后端'], likes: 89, comments: 23, views: 1800,
    isPinned: false, isHot: false, createdAt: '5 小时前',
  },
  {
    id: '4', title: '面试时如何回答"你的缺点是什么"？',
    content: '每次被问到这个问题都不知道怎么回答...',
    author: { id: 'u4', nickname: '求职小白', avatar: '' },
    tags: ['面试技巧', '求助'], likes: 67, comments: 34, views: 1200,
    isPinned: false, isHot: false, createdAt: '昨天',
  },
  {
    id: '5', title: '35 岁程序员何去何从？大龄转管理经验分享',
    content: '做了 10 年开发，最近成功转技术管理...',
    author: { id: 'u5', nickname: '老码农', avatar: '' },
    tags: ['职业规划', '经验分享'], likes: 342, comments: 120, views: 8900,
    isPinned: false, isHot: true, createdAt: '昨天',
  },
];

const PostDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const [isLiked, setIsLiked] = useState(false);
  const [isFavorited, setIsFavorited] = useState(false);
  const [likes, setLikes] = useState(0);
  const [commentText, setCommentText] = useState('');

  const post = MOCK_POSTS.find((p) => p.id === id);
  const comments = mockPostDetailComments;

  if (!post) {
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

  const handleLike = () => {
    if (isLiked) {
      setLikes((prev) => prev - 1);
    } else {
      setLikes((prev) => prev + 1);
    }
    setIsLiked(!isLiked);
  };

  const handleComment = () => {
    if (!commentText.trim()) {
      msg.warning('请输入评论内容');
      return;
    }
    msg.success('评论发表成功');
    setCommentText('');
  };

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
          {post.isPinned && <PushpinOutlined className="text-[#CF222E] text-xs" />}
          {post.isHot && <span className="tag tag-flame"><FireOutlined className="text-[10px]" /> 热门</span>}
        </div>

        <h1 className="text-xl font-extrabold text-[#0D1117] mb-4 leading-snug">
          {post.title}
        </h1>

        <div className="flex items-center gap-3 mb-5">
          <Avatar
            size={40}
            className="!bg-[#0D1117] flex-shrink-0 !text-base cursor-pointer"
            onClick={() => navigate(`/dashboard/user/${post.author.id}`)}
          >
            {post.author.nickname[0]}
          </Avatar>
          <div>
            <div
              className="text-sm font-semibold text-[#0D1117] cursor-pointer hover:text-[#FF6B35]"
              onClick={() => navigate(`/dashboard/user/${post.author.id}`)}
            >{post.author.nickname}</div>
            <div className="text-xs text-[#8B949E]">{post.createdAt}</div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-5">
          {post.tags.map((tag) => (
            <span key={tag} className="tag tag-flame">{tag}</span>
          ))}
        </div>

        <div className="text-sm text-[#0D1117] leading-relaxed whitespace-pre-line mb-6">
          {post.content}
        </div>

        <div className="flex items-center gap-4 text-sm text-[#8B949E] pb-5 border-b border-[#F0F2F5]">
          <span className="inline-flex items-center gap-1">
            <LikeOutlined /> {post.likes + likes}
          </span>
          <span className="inline-flex items-center gap-1">
            <MessageOutlined /> {post.comments}
          </span>
          <span className="inline-flex items-center gap-1">
            {post.views} 次浏览
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
            onClick={() => {
              setIsFavorited(!isFavorited);
              msg.success(isFavorited ? '已取消收藏' : '已收藏');
            }}
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
        <div className="space-y-4">
          {comments.map((comment) => (
            <div key={comment.id} className="flex gap-3">
              <Avatar size={32} className="!bg-[#0D1117] flex-shrink-0 !text-xs">
                {comment.authorName[0]}
              </Avatar>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-semibold text-[#0D1117]">{comment.authorName}</span>
                  <span className="text-xs text-[#8B949E]">{comment.createdAt}</span>
                </div>
                <p className="text-sm text-[#0D1117] leading-relaxed">{comment.content}</p>
                <div className="flex items-center gap-3 mt-2">
                  <button
                    onClick={() => msg.info('点赞功能即将上线')}
                    className="text-xs text-[#8B949E] hover:text-[#FF6B35] transition-colors inline-flex items-center gap-1"
                  >
                    <LikeOutlined /> {comment.likes}
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
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6">
        <h3 className="text-sm font-bold text-[#0D1117] mb-4">发表评论</h3>
        <div className="flex gap-3">
          <Avatar size={32} className="!bg-[#FF6B35] flex-shrink-0 !text-xs">我</Avatar>
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
                disabled={!commentText.trim()}
                className="btn-flame !py-2 !px-5 !text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                发表评论
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PostDetailPage;