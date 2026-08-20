import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Tabs, Avatar, Modal, Input, Upload, Tag, Spin, Empty } from 'antd';
import {
  FireOutlined,
  ClockCircleOutlined,
  LikeOutlined,
  MessageOutlined,
  PushpinOutlined,
  PlusOutlined,
  BulbOutlined,
  QuestionCircleOutlined,
  PictureOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { createPost, listPosts } from '@/lib/api/posts';
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

const CommunityPage = () => {
  const { message: msg } = App.useApp();
  const [activeTab, setActiveTab] = useState('latest');
  const navigate = useNavigate();

  const [posts, setPosts] = useState<PostListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState<number | undefined>(undefined);
  const [hasMore, setHasMore] = useState(true);

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [postTitle, setPostTitle] = useState('');
  const [postContent, setPostContent] = useState('');
  const [postTags, setPostTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [postImages, setPostImages] = useState<string[]>([]);

  const availableTags = ['面试经验', '经验分享', '资源分享', '前端', '后端', '面试技巧', '求助', '职业规划', 'Offer'];

  /** 获取帖子列表 */
  const fetchPosts = useCallback(async (sort: string, resetCursor?: boolean) => {
    setLoading(true);
    try {
      const cur = resetCursor ? undefined : cursor;
      const res = await listPosts({
        sort: sort as 'latest' | 'hot' | 'pinned',
        cursor: cur,
        limit: 20,
      });
      if (resetCursor || cur === undefined) {
        setPosts(res.items);
      } else {
        setPosts((prev) => [...prev, ...res.items]);
      }
      setCursor(res.next_cursor ?? undefined);
      setHasMore(res.next_cursor !== null);
    } catch {
      msg.error('加载帖子列表失败');
    } finally {
      setLoading(false);
    }
  }, [cursor, msg]);

  useEffect(() => {
    fetchPosts(activeTab, true);
  }, [activeTab]);

  /** 切换Tab */
  const handleTabChange = (key: string) => {
    setActiveTab(key);
    setCursor(undefined);
    setHasMore(true);
  };

  /** 添加标签 */
  const handleAddTag = (tag: string) => {
    if (!postTags.includes(tag) && postTags.length < 5) {
      setPostTags([...postTags, tag]);
    }
    setTagInput('');
  };

  /** 移除标签 */
  const handleRemoveTag = (tag: string) => {
    setPostTags(postTags.filter((t) => t !== tag));
  };

  /** 移除图片 */
  const handleRemoveImage = (idx: number) => {
    setPostImages(postImages.filter((_, i) => i !== idx));
  };

  /** 重置发帖表单 */
  const resetForm = () => {
    setPostTitle('');
    setPostContent('');
    setPostTags([]);
    setPostImages([]);
    setTagInput('');
  };

  /** 发布帖子 */
  const handlePublish = async () => {
    if (!postTitle.trim()) {
      msg.warning('请输入帖子标题');
      return;
    }
    if (!postContent.trim()) {
      msg.warning('请输入帖子内容');
      return;
    }
    setPublishing(true);
    try {
      await createPost({ title: postTitle.trim(), content: postContent.trim(), tags: postTags });
      msg.success('帖子发布成功！');
      setCreateModalOpen(false);
      resetForm();
      fetchPosts(activeTab, true);
    } catch {
      msg.error('发布失败，请稍后重试');
    } finally {
      setPublishing(false);
    }
  };

  /** 关闭发帖弹窗 */
  const handleCloseModal = () => {
    setCreateModalOpen(false);
    resetForm();
  };

  const filteredTags = tagInput
    ? availableTags.filter((t) => t.includes(tagInput) && !postTags.includes(t))
    : availableTags.filter((t) => !postTags.includes(t));

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold text-[#0D1117]">社区</h1>
          <button onClick={() => setCreateModalOpen(true)} className="btn-flame">
            <PlusOutlined /> 发帖
          </button>
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          className="mb-4"
          items={[
            { key: 'latest', label: '最新', icon: <ClockCircleOutlined /> },
            { key: 'hot', label: '热门', icon: <FireOutlined /> },
            { key: 'pinned', label: '置顶', icon: <PushpinOutlined /> },
          ].map((tab) => ({
            key: tab.key,
            label: <span className="flex items-center gap-1.5 text-sm">{tab.icon}{tab.label}</span>,
          }))}
        />
      </div>

      <div className="flex-1 overflow-y-auto space-y-3">
        {loading && posts.length === 0 ? (
          <div className="flex justify-center py-16">
            <Spin size="large" />
          </div>
        ) : posts.length === 0 ? (
          <Empty description="暂无帖子" className="py-16" />
        ) : (
          <>
            {posts.map((post) => (
              <div
                key={post.id}
                className="bg-white border border-[#E1E4E8] rounded-xl p-5 hover:border-[#FF6B35]/30 hover:shadow-sm transition-all cursor-pointer"
                onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
              >
                <div className="flex items-start gap-3">
                  <Avatar
                    size={36}
                    className="!bg-[#0D1117] flex-shrink-0 cursor-pointer"
                    onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                  >{post.author?.nickname?.[0] || '?'}</Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      {post.is_pinned && <PushpinOutlined className="text-[#CF222E] text-xs" />}
                      <h4 className="text-sm font-semibold text-[#0D1117] truncate">{post.title}</h4>
                      {post.is_hot && <span className="tag tag-flame"><FireOutlined className="text-[10px]" /> 热</span>}
                    </div>
                    <p className="text-xs text-[#5F6B7A] line-clamp-2 mb-3">{post.content_preview || post.title}</p>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 text-xs text-[#8B949E]">
                        <span
                          className="cursor-pointer hover:text-[#FF6B35]"
                          onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                        >{post.author?.nickname || '未知用户'}</span>
                        <span>{formatTime(post.created_at)}</span>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-[#8B949E]">
                        <span className="inline-flex items-center gap-1"><LikeOutlined /> {post.likes_count}</span>
                        <span className="inline-flex items-center gap-1"><MessageOutlined /> {post.comments_count}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {hasMore && (
              <div className="flex justify-center py-4">
                <button
                  onClick={() => fetchPosts(activeTab)}
                  disabled={loading}
                  className="text-sm text-[#FF6B35] hover:text-[#E85D26] disabled:opacity-50"
                >
                  {loading ? '加载中...' : '加载更多'}
                </button>
              </div>
            )}
          </>
        )}
      </div>

      <Modal
        title="发布帖子"
        open={createModalOpen}
        onCancel={handleCloseModal}
        onOk={handlePublish}
        okText="发布"
        cancelText="取消"
        width={640}
        okButtonProps={{ className: '!bg-[#FF6B35] !border-[#FF6B35] hover:!bg-[#E85D26]', loading: publishing }}
        destroyOnClose
        confirmLoading={publishing}
      >
        <div className="py-2 space-y-4">
          <div>
            <label className="text-sm font-semibold text-[#0D1117] block mb-2">标题</label>
            <Input
              value={postTitle}
              onChange={(e) => setPostTitle(e.target.value)}
              placeholder="请输入帖子标题（必填）"
              maxLength={255}
              showCount
              className="!rounded-lg"
            />
          </div>

          <div>
            <label className="text-sm font-semibold text-[#0D1117] block mb-2">内容</label>
            <Input.TextArea
              value={postContent}
              onChange={(e) => setPostContent(e.target.value)}
              placeholder="分享你的面试经验、问题或想法..."
              rows={5}
              maxLength={5000}
              showCount
              className="!rounded-lg"
            />
          </div>

          <div>
            <label className="text-sm font-semibold text-[#0D1117] block mb-2">标签</label>
            <div className="flex flex-wrap gap-2 mb-2">
              {postTags.map((tag) => (
                <Tag
                  key={tag}
                  closable
                  onClose={() => handleRemoveTag(tag)}
                  className="!bg-[#FFF3ED] !text-[#FF6B35] !border-[#FF6B35]/20 !rounded-md !py-0.5 !px-2"
                >
                  {tag}
                </Tag>
              ))}
            </div>
            <Input
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              placeholder="输入标签名称（最多 5 个）"
              className="!rounded-lg"
              disabled={postTags.length >= 5}
            />
            {tagInput && filteredTags.length > 0 && postTags.length < 5 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {filteredTags.slice(0, 6).map((tag) => (
                  <button
                    key={tag}
                    onClick={() => handleAddTag(tag)}
                    className="text-xs px-3 py-1 rounded-md border border-[#E1E4E8] text-[#5F6B7A] hover:border-[#FF6B35] hover:text-[#FF6B35] transition-colors"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="text-sm font-semibold text-[#0D1117] block mb-2">
              图片
              <span className="text-xs text-[#8B949E] font-normal ml-1">（最多 4 张）</span>
            </label>
            <div className="flex flex-wrap gap-3">
              {postImages.map((img, idx) => (
                <div key={idx} className="relative w-24 h-24 rounded-lg overflow-hidden border border-[#E1E4E8]">
                  <img src={img} alt={`upload-${idx}`} className="w-full h-full object-cover" />
                  <button
                    onClick={() => handleRemoveImage(idx)}
                    className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors"
                  >
                    <CloseOutlined className="text-white text-[10px]" />
                  </button>
                </div>
              ))}
              {postImages.length < 4 && (
                <Upload
                  accept="image/*"
                  showUploadList={false}
                  beforeUpload={(file) => {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                      setPostImages([...postImages, e.target?.result as string]);
                    };
                    reader.readAsDataURL(file);
                    return false;
                  }}
                >
                  <div className="w-24 h-24 rounded-lg border-2 border-dashed border-[#E1E4E8] flex flex-col items-center justify-center gap-1 cursor-pointer hover:border-[#FF6B35] hover:bg-[#FFF3ED]/50 transition-colors">
                    <PictureOutlined className="text-[#8B949E] text-lg" />
                    <span className="text-[10px] text-[#8B949E]">上传图片</span>
                  </div>
                </Upload>
              )}
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default CommunityPage;