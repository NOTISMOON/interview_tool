import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import App from 'antd/es/app';
import Tabs from 'antd/es/tabs';
import Avatar from 'antd/es/avatar';
import Modal from 'antd/es/modal';
import Input from 'antd/es/input';
import Upload from 'antd/es/upload';
import Tag from 'antd/es/tag';
import Spin from 'antd/es/spin';
import Empty from 'antd/es/empty';
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
  ReloadOutlined,
  EyeOutlined,
} from '@/components/icons';
import { createPost, listPosts } from '@/lib/api/posts';
import type { PostListItem } from '@/types';
import { useUpload } from '@/hooks/useUpload';
import { useTimelineLayout, useTimelineReveal } from '@/hooks/useTimelineLayout';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

/** 格式化时间为相对时间展示 */
function formatTime(dateStr: string): string {
  const d = dayjs(dateStr);
  if (!d.isValid()) return dateStr;
  if (dayjs().diff(d, 'day') > 7) return d.format('YYYY-MM-DD HH:mm');
  return d.fromNow();
}

const CommunityPage = () => {
  const { message: msg } = App.useApp();
  const [activeTab, setActiveTab] = useState('latest');
  const navigate = useNavigate();

  // 时间线布局模式（交错/单侧，localStorage 记忆）
  const { layout, setLayout, layoutClass } = useTimelineLayout('alt');

  const [posts, setPosts] = useState<PostListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // 时间线条目浮现动画（数据变化时重新观察）
  useTimelineReveal([posts.length, activeTab, layout]);
  const [cursor, setCursor] = useState<number | undefined>(undefined);
  const [hasMore, setHasMore] = useState(true);
  /** 底部哨兵元素引用，用于 IntersectionObserver 触发加载更多 */
  const sentinelRef = useRef<HTMLDivElement>(null);

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
    if (resetCursor) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
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
      setLoadingMore(false);
    }
  }, [cursor, msg]);

  /** 初始加载 & 切换 Tab 时重置 */
  useEffect(() => {
    fetchPosts(activeTab, true);
  }, [activeTab]);

  /** 上拉加载更多：IntersectionObserver 监听底部哨兵 */
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore || loadingMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore) {
          fetchPosts(activeTab);
        }
      },
      { rootMargin: '200px' },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, activeTab, fetchPosts]);

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
      // 未选标签时追加提示：热门榜单要求帖子有标签
      if (postTags.length === 0) {
        msg.info('提示：添加标签的帖子才能进入热门榜单');
      }
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

        <div className="flex items-center justify-between mb-4">
          <Tabs
            activeKey={activeTab}
            onChange={handleTabChange}
            className="mb-0"
            items={[
              { key: 'latest', label: '最新', icon: <ClockCircleOutlined /> },
              { key: 'hot', label: '热门', icon: <FireOutlined /> },
            ].map((tab) => ({
              key: tab.key,
              label: <span className="flex items-center gap-1.5 text-sm">{tab.icon}{tab.label}</span>,
            }))}
          />
          <div className="flex items-center gap-3">
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
            <button
              onClick={() => { setCursor(undefined); setHasMore(true); fetchPosts(activeTab, true); }}
              disabled={loading}
              className="flex items-center gap-1 text-xs text-[#999999] hover:text-[#D9A441] transition-colors disabled:opacity-50"
            >
              <ReloadOutlined className={loading ? 'animate-spin' : ''} />
              刷新
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && posts.length === 0 ? (
          <div className="flex justify-center py-16">
            <Spin size="large" />
          </div>
        ) : posts.length === 0 ? (
          <Empty description="暂无帖子" className="py-16" />
        ) : (
          <div className={`timeline pb-4 ${layoutClass}`}>
            {posts.map((post) => (
              <div key={post.id} className="tl-item">
                {/* 节点：热帖橙色，普通青色 */}
                <div className={`tl-node ${post.is_hot ? 'hot' : ''}`}>
                  <span className="ring" />
                  <span className="pulse" />
                </div>
                {/* 卡片 */}
                <div
                  className="tl-card cursor-pointer"
                  onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
                >
                  <div className="flex items-center gap-2.5 mb-2">
                    <Avatar
                      size={30}
                      src={post.author?.avatar}
                      className="!bg-[#232529] flex-shrink-0"
                      onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                    >{post.author?.nickname?.[0] || '?'}</Avatar>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="text-[13px] font-semibold text-[#232529] cursor-pointer hover:text-[#D9A441] transition-colors"
                          onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author?.id}`); }}
                        >{post.author?.nickname || '未知用户'}</span>
                        {post.is_hot && (
                          <span className="tag tag-flame !text-[10px] !px-1.5 !py-px">
                            <FireOutlined className="text-[10px]" /> 热
                          </span>
                        )}
                      </div>
                      <div className="text-[11.5px] text-[#999999]">{formatTime(post.created_at)}</div>
                    </div>
                  </div>
                  <h4 className="text-[15px] font-bold text-[#232529] leading-snug mb-1.5 hover:text-[#D9A441] transition-colors">
                    {post.title}
                  </h4>
                  <p className="text-[13px] text-[#666666] leading-relaxed line-clamp-2 mb-3">
                    {post.content_preview || post.title}
                  </p>
                  {post.tags?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {post.tags.slice(0, 4).map((tag) => (
                        <span key={tag} className="text-[11px] text-[#0d9488] bg-[#F7EBD3] px-2 py-0.5 rounded-full">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center gap-5 pt-2.5 border-t border-[#F2F3F5] text-[12.5px] text-[#999999]">
                    <span className="inline-flex items-center gap-1 hover:text-[#D9A441] transition-colors">
                      <LikeOutlined /> {post.likes_count}
                    </span>
                    <span className="inline-flex items-center gap-1 hover:text-[#D9A441] transition-colors">
                      <MessageOutlined /> {post.comments_count}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <EyeOutlined /> {post.views_count}
                    </span>
                  </div>
                </div>
              </div>
            ))}
            {hasMore && (
              <div className="flex justify-center py-4">
                {/* 底部哨兵：IntersectionObserver 触发自动加载 */}
                <div ref={sentinelRef} className="w-full h-4" />
                {loadingMore && <Spin size="small" className="text-[#D9A441]" />}
              </div>
            )}
            {!hasMore && posts.length > 0 && (
              <div className="text-center py-4 text-xs text-[#999999]">— 已加载全部帖子 —</div>
            )}
          </div>
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
        okButtonProps={{ className: '!bg-[#D9A441] !border-[#D9A441] hover:!bg-[#A97E24]', loading: publishing }}
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
                  className="!bg-[#F7EBD3] !text-[#D9A441] !border-[#D9A441]/20 !rounded-md !py-0.5 !px-2"
                >
                  {tag}
                </Tag>
              ))}
            </div>
            <Input
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onPressEnter={() => {
                // 回车直接添加自定义标签
                const v = tagInput.trim();
                if (v && !postTags.includes(v) && postTags.length < 5) {
                  handleAddTag(v);
                }
              }}
              placeholder="输入标签名称后回车添加（最多 5 个）"
              className="!rounded-lg"
              disabled={postTags.length >= 5}
            />
            {tagInput && postTags.length < 5 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {/* 匹配的建议标签 */}
                {filteredTags.slice(0, 6).map((tag) => (
                  <button
                    key={tag}
                    onClick={() => handleAddTag(tag)}
                    className="text-xs px-3 py-1 rounded-md border border-[#E8E8E8] text-[#666666] hover:border-[#D9A441] hover:text-[#D9A441] transition-colors"
                  >
                    {tag}
                  </button>
                ))}
                {/* 无匹配建议时提供"创建自定义标签"入口 */}
                {filteredTags.length === 0 && tagInput.trim() && !postTags.includes(tagInput.trim()) && (
                  <button
                    onClick={() => handleAddTag(tagInput.trim())}
                    className="text-xs px-3 py-1 rounded-md border border-dashed border-[#D9A441] text-[#D9A441] hover:bg-[#F7EBD3] transition-colors"
                  >
                    创建「{tagInput.trim()}」标签
                  </button>
                )}
              </div>
            )}
            {/* 热门规则提示：有标签才参与热门，引导用户添加标签 */}
            {postTags.length === 0 && (
              <p className="text-xs text-[#FFAA00] mt-1.5">提示：添加标签的帖子才能进入热门榜单</p>
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
                  <div className="w-24 h-24 rounded-lg border-2 border-dashed border-[#E8E8E8] flex flex-col items-center justify-center gap-1 cursor-pointer hover:border-[#D9A441] hover:bg-[#F7EBD3]/50 transition-colors">
                    {imageUploading ? (
                      <LoadingOutlined className="text-[#D9A441] text-lg" />
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