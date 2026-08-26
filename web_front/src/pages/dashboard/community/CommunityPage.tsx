import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Tabs, Avatar, Modal, Input, Upload, Tag, Spin, Empty } from 'antd';
import {
  FireOutlined,
  ClockCircleOutlined,
  LikeOutlined,
  MessageOutlined,
  PlusOutlined,
  BulbOutlined,
  QuestionCircleOutlined,
  PictureOutlined,
  CloseOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { createPost, listPosts } from '@/lib/api/posts';
import type { PostListItem } from '@/types';
import { useUpload } from '@/hooks/useUpload';
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
  /** 已上传到 COS 的图片 URL 列表 */
  const [postImages, setPostImages] = useState<string[]>([]);
  /** 图片上传中状态 */
  const [imageUploading, setImageUploading] = useState(false);
  const { upload: uploadImage } = useUpload('post_image');

  const availableTags = ['面试经验', '经验分享', '资源分享', '前端', '后端', '面试技巧', '求助', '职业规划', 'Offer'];

  /** 获取帖子列表 */
  const fetchPosts = useCallback(async (sort: string, resetCursor?: boolean) => {
    setLoading(true);
    try {
      const cur = resetCursor ? undefined : cursor;
      const res = await listPosts({
          sort: sort as 'latest' | 'hot',
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
      await createPost({
        title: postTitle.trim(),
        content: postContent.trim(),
        tags: postTags,
        images: postImages.length > 0 ? postImages : undefined,
      });
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
          <h1 className="text-xl font-bold text-[#232529]">社区</h1>
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
                className="group bg-white border border-[#E8E8E8] rounded-xl p-5 hover:border-[#00BFA5]/30 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer relative overflow-hidden"
                onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
              >
                <div className="absolute left-0 top-3 bottom-3 w-0.5 bg-[#00BFA5] rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
                <div className="flex items-start gap-3">
                  <Avatar
                    size={36}
                    src={post.author?.avatar}
                    className="!bg-[#232529] flex-shrink-0 cursor-pointer ring-2 ring-transparent hover:ring-[#00BFA5]/30 transition-all"
                    onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                  >{post.author?.nickname?.[0] || '?'}</Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <h4 className="text-sm font-semibold text-[#232529] truncate group-hover:text-[#00BFA5] transition-colors">{post.title}</h4>
                      {post.is_hot && <span className="tag tag-flame shrink-0"><FireOutlined className="text-[10px]" /> 热</span>}
                    </div>
                    <p className="text-xs text-[#666666] leading-relaxed line-clamp-2 mb-3">{post.content_preview || post.title}</p>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 text-xs text-[#999999]">
                        <span
                          className="cursor-pointer hover:text-[#00BFA5] transition-colors"
                          onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                        >{post.author?.nickname || '未知用户'}</span>
                        <span className="text-[#D8DBE0]">·</span>
                        <span>{formatTime(post.created_at)}</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-[#999999]">
                        <span className="inline-flex items-center gap-1 hover:text-[#00BFA5] transition-colors"><LikeOutlined className="text-[11px]" /> {post.likes_count}</span>
                        <span className="inline-flex items-center gap-1 hover:text-[#00BFA5] transition-colors"><MessageOutlined className="text-[11px]" /> {post.comments_count}</span>
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
                  className="text-sm text-[#00BFA5] hover:text-[#00A88A] disabled:opacity-50"
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
        okButtonProps={{ className: '!bg-[#00BFA5] !border-[#00BFA5] hover:!bg-[#00A88A]', loading: publishing }}
        destroyOnClose
        confirmLoading={publishing}
      >
        <div className="py-2 space-y-4">
          <div>
            <label className="text-sm font-semibold text-[#232529] block mb-2">标题</label>
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
            <label className="text-sm font-semibold text-[#232529] block mb-2">内容</label>
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
            <label className="text-sm font-semibold text-[#232529] block mb-2">标签</label>
            <div className="flex flex-wrap gap-2 mb-2">
              {postTags.map((tag) => (
                <Tag
                  key={tag}
                  closable
                  onClose={() => handleRemoveTag(tag)}
                  className="!bg-[#E0F7F4] !text-[#00BFA5] !border-[#00BFA5]/20 !rounded-md !py-0.5 !px-2"
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
                    className="text-xs px-3 py-1 rounded-md border border-[#E8E8E8] text-[#666666] hover:border-[#00BFA5] hover:text-[#00BFA5] transition-colors"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="text-sm font-semibold text-[#232529] block mb-2">
              图片
              <span className="text-xs text-[#999999] font-normal ml-1">（最多 4 张）</span>
            </label>
            <div className="flex flex-wrap gap-3">
              {postImages.map((img, idx) => (
                <div key={idx} className="relative w-24 h-24 rounded-lg overflow-hidden border border-[#E8E8E8]">
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
                  disabled={imageUploading}
                  beforeUpload={async (file) => {
                    setImageUploading(true);
                    try {
                      const record = await uploadImage(file);
                      setPostImages([...postImages, record.file_url]);
                    } catch (err) {
                      msg.error(err instanceof Error ? err.message : '图片上传失败，请重试');
                    } finally {
                      setImageUploading(false);
                    }
                    return false;
                  }}
                >
                  <div className="w-24 h-24 rounded-lg border-2 border-dashed border-[#E8E8E8] flex flex-col items-center justify-center gap-1 cursor-pointer hover:border-[#00BFA5] hover:bg-[#E0F7F4]/50 transition-colors">
                    {imageUploading ? (
                      <LoadingOutlined className="text-[#00BFA5] text-lg" />
                    ) : (
                      <>
                        <PictureOutlined className="text-[#999999] text-lg" />
                        <span className="text-[10px] text-[#999999]">上传图片</span>
                      </>
                    )}
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