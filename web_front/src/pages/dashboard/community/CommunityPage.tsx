import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Tabs, Avatar, Modal, Input, Upload, Tag } from 'antd';
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
import type { CommunityPost } from '@/types';

const MOCK_POSTS: CommunityPost[] = [
  {
    id: '1', title: '前端三年经验，面试字节挂了三次，求大佬指点',
    content: '三年 Vue 经验，最近在学 React，面试总挂在系统设计上...',
    author: { id: 'u7', nickname: '前端小张', avatar: '' },
    tags: ['面试经验', '前端'], likes: 128, comments: 45, views: 2300,
    isPinned: true, isHot: true, createdAt: '10 分钟前',
  },
  {
    id: '2', title: 'AI 模拟面试真的有用！拿到 offer 了',
    content: '用这个工具练习了两周，面试时明显感觉更自信了...',
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

const CommunityPage = () => {
  const { message: msg } = App.useApp();
  const [activeTab, setActiveTab] = useState('hot');
  const navigate = useNavigate();

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [postTitle, setPostTitle] = useState('');
  const [postContent, setPostContent] = useState('');
  const [postTags, setPostTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [postImages, setPostImages] = useState<string[]>([]);

  const availableTags = ['面试经验', '经验分享', '资源分享', '前端', '后端', '面试技巧', '求助', '职业规划', 'Offer'];

  const handleAddTag = (tag: string) => {
    if (!postTags.includes(tag) && postTags.length < 5) {
      setPostTags([...postTags, tag]);
    }
    setTagInput('');
  };

  const handleRemoveTag = (tag: string) => {
    setPostTags(postTags.filter((t) => t !== tag));
  };

  const handleRemoveImage = (idx: number) => {
    setPostImages(postImages.filter((_, i) => i !== idx));
  };

  const handlePublish = () => {
    if (!postTitle.trim()) {
      msg.warning('请输入帖子标题');
      return;
    }
    if (!postContent.trim()) {
      msg.warning('请输入帖子内容');
      return;
    }
    msg.success('帖子发布成功！');
    setCreateModalOpen(false);
    setPostTitle('');
    setPostContent('');
    setPostTags([]);
    setPostImages([]);
  };

  const filteredTags = tagInput
    ? availableTags.filter((t) => t.includes(tagInput) && !postTags.includes(t))
    : availableTags.filter((t) => !postTags.includes(t));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-[#0D1117]">社区</h1>
        <button onClick={() => setCreateModalOpen(true)} className="btn-flame">
          <PlusOutlined /> 发帖
        </button>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        className="mb-4"
        items={[
          { key: 'hot', label: '热门', icon: <FireOutlined /> },
          { key: 'latest', label: '最新', icon: <ClockCircleOutlined /> },
          { key: 'tips', label: '面经', icon: <BulbOutlined /> },
          { key: 'qa', label: '问答', icon: <QuestionCircleOutlined /> },
        ].map((tab) => ({
          key: tab.key,
          label: <span className="flex items-center gap-1.5 text-sm">{tab.icon}{tab.label}</span>,
        }))}
      />

      <div className="space-y-3">
        {MOCK_POSTS.filter((p) => {
          if (activeTab === 'hot') return p.isHot;
          if (activeTab === 'tips') return p.tags.includes('面试经验') || p.tags.includes('经验分享');
          if (activeTab === 'qa') return p.tags.includes('求助') || p.tags.includes('问答');
          return true;
        }).map((post) => (
          <div
            key={post.id}
            className="bg-white border border-[#E1E4E8] rounded-xl p-5 hover:border-[#FF6B35]/30 hover:shadow-sm transition-all cursor-pointer"
            onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
          >
            <div className="flex items-start gap-3">
              <Avatar
                  size={36}
                  className="!bg-[#0D1117] flex-shrink-0 cursor-pointer"
                  onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author.id}`); }}
                >{post.author.nickname[0]}</Avatar>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1.5">
                  {post.isPinned && <PushpinOutlined className="text-[#CF222E] text-xs" />}
                  <h4 className="text-sm font-semibold text-[#0D1117] truncate">{post.title}</h4>
                  {post.isHot && <span className="tag tag-flame"><FireOutlined className="text-[10px]" /> 热</span>}
                </div>
                <p className="text-xs text-[#5F6B7A] line-clamp-2 mb-3">{post.content}</p>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 text-xs text-[#8B949E]">
                    <span
                    className="cursor-pointer hover:text-[#FF6B35]"
                    onClick={(e) => { e?.stopPropagation(); navigate(`/dashboard/user/${post.author.id}`); }}
                  >{post.author.nickname}</span>
                    <span>{post.createdAt}</span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-[#8B949E]">
                    <span className="inline-flex items-center gap-1"><LikeOutlined /> {post.likes}</span>
                    <span className="inline-flex items-center gap-1"><MessageOutlined /> {post.comments}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <Modal
        title="发布帖子"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          setPostTitle('');
          setPostContent('');
          setPostTags([]);
          setPostImages([]);
        }}
        onOk={handlePublish}
        okText="发布"
        cancelText="取消"
        width={640}
        okButtonProps={{ className: '!bg-[#FF6B35] !border-[#FF6B35] hover:!bg-[#E85D26]' }}
        destroyOnClose
      >
        <div className="py-2 space-y-4">
          <div>
            <label className="text-sm font-semibold text-[#0D1117] block mb-2">标题</label>
            <Input
              value={postTitle}
              onChange={(e) => setPostTitle(e.target.value)}
              placeholder="请输入帖子标题（必填）"
              maxLength={100}
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
              maxLength={2000}
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