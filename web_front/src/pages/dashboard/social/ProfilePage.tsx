import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Avatar from 'antd/es/avatar';
import App from 'antd/es/app';
import Modal from 'antd/es/modal';
import Input from 'antd/es/input';
import Upload from 'antd/es/upload';
import DatePicker from 'antd/es/date-picker';
import Radio from 'antd/es/radio';
import Empty from 'antd/es/empty';
import Popconfirm from 'antd/es/popconfirm';
import Switch from 'antd/es/switch';
import Spin from 'antd/es/spin';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import {
  RightOutlined,
  FileTextOutlined,
  HistoryOutlined,
  TrophyOutlined,
  TeamOutlined,
  UserAddOutlined,
  BellOutlined,
  StarOutlined,
  ShareAltOutlined,
  SettingOutlined,
  SafetyOutlined,
  QuestionCircleOutlined,
  LogoutOutlined,
  EditOutlined,
  CameraOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
  EnvironmentOutlined,
  PhoneOutlined,
  WomanOutlined,
  ManOutlined,
  CalendarOutlined,
  SmileOutlined,
  PlusOutlined,
  FireOutlined,
  LikeOutlined,
  MessageOutlined,
  ReloadOutlined,
} from '@/components/icons';
import type { ProfileVisibility } from '@/types';
import type { PostListItem } from '@/types';
import { useAppStore } from '@/store';
import { FileUpload } from '@/components/upload/FileUpload';
import { listPosts } from '@/lib/api/posts';
import { getInterviewList } from '@/lib/api/interview';
import { useUpload } from '@/hooks/useUpload';
import {
  getResumes,
  deleteResume,
  retryResume,
  RESUME_STATUS_LABEL,
} from '@/lib/api/resume';
import type { ApiResume } from '@/lib/api/resume';
import { cachedFetch, invalidateCache } from '@/lib/queryCache';
import { shareUrl } from '@/lib/share';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

/** 格式化时间为相对时间展示 */
function formatTime(dateStr: string): string {
  return dayjs(dateStr).fromNow();
}

/** 面试统计缓存 key（TTL 30s，避免每次进主页重复请求） */
const INTERVIEW_STATS_CACHE_KEY = 'profile:interview-stats';
/** 简历列表缓存 key（TTL 30s） */
const RESUMES_CACHE_KEY = 'profile:resumes';

const ProfilePage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { message, modal } = App.useApp();
  const { user, logout, updateUser, refreshUser } = useAppStore();
  const { upload: uploadAvatar, uploading: avatarUploading } = useUpload('avatar');

  /** 从路由 state 接收打开简历弹窗指令 */
  useEffect(() => {
    const state = location.state as { openResumeModal?: boolean } | null;
    if (state?.openResumeModal) {
      setResumeModalOpen(true);
      // 清除 state 避免刷新页面再次触发
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  /** 面试统计（GET /interviews：次数与平均分） */
  const [interviewCount, setInterviewCount] = useState(0);
  const [avgScore, setAvgScore] = useState<number | null>(null);

  // 拉取面试统计（30s 缓存，数据变化不频繁，避免每次进入重复请求）
  useEffect(() => {
    cachedFetch(INTERVIEW_STATS_CACHE_KEY, 30000, () => getInterviewList(1, 100))
      .then((res) => {
        setInterviewCount(res.total);
        const finished = res.items.filter((it) => it.status === 1 && it.total_score !== null);
        setAvgScore(
          finished.length > 0
            ? Math.round(finished.reduce((s, it) => s + (it.total_score ?? 0), 0) / finished.length)
            : null,
        );
      })
      .catch(() => {
        /* 加载失败静默 */
      });
  }, []);

  const [editModalOpen, setEditModalOpen] = useState(false);
  const [resumeModalOpen, setResumeModalOpen] = useState(false);
  /** 帖子列表状态 */
  const [posts, setPosts] = useState<PostListItem[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [postsCursor, setPostsCursor] = useState<number | undefined>(undefined);
  const [postsHasMore, setPostsHasMore] = useState(true);
  const [showPosts, setShowPosts] = useState(false);
  const [editForm, setEditForm] = useState({
    nickname: '',
    avatar: '',
    gender: 'other' as 'male' | 'female' | 'other',
    birthday: '',
    bio: '',
    phone: '',
    location: '',
    profileVisibility: {
      gender: true,
      birthday: true,
      bio: true,
      location: true,
      phone: false,
    } as ProfileVisibility,
  });
  /** 服务端真实简历列表（GET /resumes，含解析状态） */
  const [resumes, setResumes] = useState<ApiResume[]>([]);
  const [resumesLoading, setResumesLoading] = useState(false);

  /** 拉取服务端简历列表（30s 缓存，失败静默，保留已有展示） */
  const loadResumes = async () => {
    setResumesLoading(true);
    try {
      const res = await cachedFetch(RESUMES_CACHE_KEY, 30000, () => getResumes(1, 20));
      setResumes(res.items);
    } catch {
      // 接口失败不影响已有展示
    } finally {
      setResumesLoading(false);
    }
  };

  // 进入页面时拉取一次简历列表 + 刷新个人资料
  // 后端已开启ETag协商缓存：每次进入都发请求，数据未变返回304（极快），
  // 数据更新（如关注数变化）返回200新数据并同步更新store与localStorage
  useEffect(() => {
    loadResumes();
    refreshUser();
  }, []);

  /** 获取当前用户帖子列表 */
  const fetchPosts = useCallback(async (resetCursor?: boolean) => {
    if (!user) return;
    setPostsLoading(true);
    try {
      const cur = resetCursor ? undefined : postsCursor;
      const res = await listPosts({ author_id: Number(user.id), cursor: cur, limit: 20, sort: 'latest' });
      if (resetCursor || cur === undefined) {
        setPosts(res.items);
      } else {
        setPosts((prev) => [...prev, ...res.items]);
      }
      setPostsCursor(res.next_cursor ?? undefined);
      setPostsHasMore(res.next_cursor !== null);
    } catch {
      message.error('加载帖子列表失败');
    } finally {
      setPostsLoading(false);
    }
  }, [user, postsCursor, message]);

  const handleLogout = () => {
    modal.confirm({
      title: '确定要退出登录吗？',
      content: '退出后需要重新登录才能使用',
      okText: '退出',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => { await logout(); navigate('/login', { replace: true }); },
    });
  };

  const openEditModal = () => {
    setEditForm({
      nickname: user?.nickname || '',
      avatar: user?.avatar || '',
      gender: user?.gender || 'other',
      birthday: user?.birthday || '',
      bio: user?.bio || '',
      phone: user?.phone || '',
      location: user?.location || '',
      profileVisibility: user?.profileVisibility || {
        gender: true,
        birthday: true,
        bio: true,
        location: true,
        phone: false,
      },
    });
    setEditModalOpen(true);
  };

  const handleSaveProfile = async () => {
    if (!editForm.nickname.trim()) {
      message.warning('昵称不能为空');
      return;
    }
    try {
      await updateUser({
        nickname: editForm.nickname.trim(),
        avatar: editForm.avatar || undefined,
        gender: editForm.gender,
        birthday: editForm.birthday,
        bio: editForm.bio,
        phone: editForm.phone,
        location: editForm.location,
        profileVisibility: editForm.profileVisibility,
      });
      message.success('资料已更新');
      setEditModalOpen(false);
    } catch {
      message.error('更新资料失败，请重试');
    }
  };

  /** 上传成功回调：清除缓存并刷新服务端简历列表 */
  const handleResumeUploaded = async () => {
    invalidateCache(RESUMES_CACHE_KEY);
    message.success('简历上传成功');
    await loadResumes();
  };

  /** 上传失败回调：展示用户可读错误 */
  const handleResumeUploadError = (errMsg: string) => {
    message.error(errMsg);
  };

  /** 删除简历：走独立删除接口（软删 + 联动清理） */
  const handleDeleteResume = (resume: ApiResume) => {
    modal.confirm({
      title: '确定要删除这份简历吗？',
      content: '删除后不可恢复',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteResume(resume.id);
          invalidateCache(RESUMES_CACHE_KEY);
          message.success('简历已删除');
          await loadResumes();
        } catch {
          message.error('删除简历失败，请重试');
        }
      },
    });
  };

  /** 对解析失败的简历一键重试 */
  const handleRetryResume = async (resume: ApiResume) => {
    try {
      await retryResume(resume.id);
      invalidateCache(RESUMES_CACHE_KEY);
      message.success('已重新分析，请稍候');
      await loadResumes();
    } catch {
      message.error('重试失败，请稍后重试');
    }
  };

  const handleStartInterview = (_resumeId?: number) => {
    setResumeModalOpen(false);
    navigate('/dashboard/interview');
  };

  interface MenuItem {
    icon: React.ReactNode;
    label: string;
    count?: number | string;
    color: string;
    bg: string;
    onClick: () => void;
  }

  const menuGroups: { title: string; items: MenuItem[] }[] = [
    {
      title: '数据',
      items: [
        { icon: <FileTextOutlined />, label: '我的简历', count: resumes.length, color: '#D9A441', bg: '#F7EBD3', onClick: () => setResumeModalOpen(true) },
        { icon: <HistoryOutlined />, label: '面试记录', count: interviewCount, color: '#00B578', bg: '#F7EBD3', onClick: () => navigate('/dashboard/history') },
        { icon: <TrophyOutlined />, label: '平均得分', count: avgScore !== null ? `${avgScore} 分` : '--', color: '#FFAA00', bg: '#FFF7E0', onClick: () => navigate('/dashboard/history') },
      ],
    },
    {
      title: '社交',
      items: [
        { icon: <TeamOutlined />, label: '我的关注', count: user?.followingCount ?? 0, color: '#D9A441', bg: '#F7EBD3', onClick: () => navigate('/dashboard/following') },
        { icon: <UserAddOutlined />, label: '我的粉丝', count: user?.followersCount ?? 0, color: '#00B578', bg: '#F7EBD3', onClick: () => navigate('/dashboard/followers') },
      ],
    },
    {
      title: '功能',
      items: [
        { icon: <BellOutlined />, label: '消息中心', color: '#D9A441', bg: '#F7EBD3', onClick: () => navigate('/dashboard/messages') },
        { icon: <StarOutlined />, label: '我的收藏', color: '#FFAA00', bg: '#FFF7E0', onClick: () => navigate('/dashboard/favorites') },
        { icon: <ShareAltOutlined />, label: '邀请好友', color: '#00B578', bg: '#F7EBD3', onClick: async () => {
          const url = window.location.origin;
          // 优先系统分享，http 下自动降级为复制链接
          const r = await shareUrl({ url, title: 'AI 超级面试', text: '来 AI 超级面试一起练习面试吧！' });
          if (r === 'copied') message.success('链接已复制，快去分享给好友吧！');
          else if (r === 'failed') message.error('复制失败，请手动复制链接');
        } },
      ],
    },
    {
      title: '其他',
      items: [
        { icon: <SettingOutlined />, label: '设置', color: '#666666', bg: '#F7F8FA', onClick: () => navigate('/dashboard/settings') },
        { icon: <SafetyOutlined />, label: '隐私政策', color: '#666666', bg: '#F7F8FA', onClick: () => navigate('/privacy') },
        { icon: <QuestionCircleOutlined />, label: '帮助与反馈', color: '#666666', bg: '#F7F8FA', onClick: () => navigate('/dashboard/help') },
      ],
    },
  ];

  return (
    <div className="max-w-[900px]">
      <h1 className="text-xl font-bold text-[#232529] mb-6">个人设置</h1>

      <div className="bg-[#232529] rounded-2xl p-6 mb-6">
        <div className="flex items-center gap-4">
          <Avatar size={56} src={user?.avatar} className="!bg-white/20 !text-white !font-bold !text-lg ring-4 ring-white/20">
            {user?.nickname?.[0] || 'U'}
          </Avatar>
          <div className="flex-1 min-w-0">
            <h3 className="text-white font-bold text-lg truncate">{user?.nickname || '用户'}</h3>
            <p className="text-white/60 text-sm truncate">{user?.email}</p>
            {user?.bio && (
              <p className="text-white/40 text-xs mt-0.5 truncate">{user.bio}</p>
            )}
          </div>
          <button onClick={openEditModal} className="text-white/80 hover:text-white transition-colors">
            <EditOutlined />
          </button>
        </div>
        <div className="grid grid-cols-4 gap-3 mt-5">
          <div
            className="bg-white/10 rounded-xl p-3 text-center cursor-pointer hover:bg-white/15 transition-colors"
            onClick={() => navigate('/dashboard/following')}
          >
            <div className="text-white font-bold text-lg">{user?.followingCount ?? 0}</div>
            <div className="text-white/50 text-xs">关注</div>
          </div>
          <div
            className="bg-white/10 rounded-xl p-3 text-center cursor-pointer hover:bg-white/15 transition-colors"
            onClick={() => navigate('/dashboard/followers')}
          >
            <div className="text-white font-bold text-lg">{user?.followersCount ?? 0}</div>
            <div className="text-white/50 text-xs">粉丝</div>
          </div>
          <div
            className="bg-white/10 rounded-xl p-3 text-center cursor-pointer hover:bg-white/15 transition-colors"
            onClick={() => setResumeModalOpen(true)}
          >
            <div className="text-white font-bold text-lg">{resumes.length}</div>
            <div className="text-white/50 text-xs">简历</div>
          </div>
          <div
            className="bg-white/10 rounded-xl p-3 text-center cursor-pointer hover:bg-white/15 transition-colors"
            onClick={() => navigate('/dashboard/history')}
          >
            <div className="text-white font-bold text-lg">{interviewCount}</div>
            <div className="text-white/50 text-xs">面试</div>
          </div>
        </div>
      </div>

      {/* 我的发帖 */}
      <div className="bg-white border border-[#E8E8E8] rounded-xl mb-5 overflow-hidden">
        <button
          onClick={() => {
            if (!showPosts) {
              setShowPosts(true);
              if (posts.length === 0) fetchPosts(true);
            } else {
              setShowPosts(false);
            }
          }}
          className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-[#F7F8FA] transition-colors text-left"
        >
          <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ color: '#D9A441', backgroundColor: '#F7EBD3' }}>
            <FileTextOutlined />
          </div>
          <span className="flex-1 text-sm font-medium text-[#232529]">我的发帖</span>
          {posts.length > 0 && <span className="text-xs text-[#999999] mr-1">{posts.length}</span>}
          <RightOutlined className={`text-[#E8E8E8] text-xs transition-transform ${showPosts ? 'rotate-90' : ''}`} />
        </button>
        {showPosts && (
          <div className="border-t border-[#E8E8E8] px-4 py-3">
            {postsLoading && posts.length === 0 ? (
              <div className="flex justify-center py-8">
                <Spin size="small" />
              </div>
            ) : posts.length === 0 ? (
              <Empty description="暂无发帖" image={Empty.PRESENTED_IMAGE_SIMPLE} className="!py-8" />
            ) : (
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {posts.map((post) => (
                  <div
                    key={post.id}
                    className="border border-[#E8E8E8] rounded-xl p-3 hover:border-[#D9A441]/30 hover:shadow-sm transition-all cursor-pointer"
                    onClick={() => navigate(`/dashboard/community/post/${post.id}`)}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="text-sm font-semibold text-[#232529] truncate">{post.title}</h4>
                      {post.is_hot && (
                        <span className="tag tag-flame text-[10px] px-1.5 py-0.5">
                          <FireOutlined /> 热
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[#666666] line-clamp-2 mb-2">{post.content_preview || post.title}</p>
                    <div className="flex items-center gap-4 text-xs text-[#999999]">
                      <span className="inline-flex items-center gap-1"><LikeOutlined /> {post.likes_count}</span>
                      <span className="inline-flex items-center gap-1"><MessageOutlined /> {post.comments_count}</span>
                      <span>{formatTime(post.created_at)}</span>
                    </div>
                  </div>
                ))}
                {postsHasMore && (
                  <div className="flex justify-center py-2">
                    <button
                      onClick={() => fetchPosts()}
                      disabled={postsLoading}
                      className="text-sm text-[#D9A441] hover:text-[#A97E24] disabled:opacity-50"
                    >
                      {postsLoading ? '加载中...' : '加载更多'}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {menuGroups.map((group) => (
        <div key={group.title} className="mb-5">
          <h3 className="text-xs font-semibold text-[#999999] uppercase tracking-wider mb-2 px-1">{group.title}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {group.items.map((item) => (
              <button
                key={item.label}
                onClick={item.onClick}
                className="w-full flex items-center gap-3 px-4 py-3.5 bg-white border border-[#E8E8E8] rounded-xl hover:bg-[#F7F8FA] hover:border-[#E8E8E8] transition-colors text-left"
              >
                <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{ color: item.color, backgroundColor: item.bg }}>
                  {item.icon}
                </div>
                <span className="flex-1 text-sm font-medium text-[#232529]">{item.label}</span>
                {'count' in item && item.count !== undefined && <span className="text-xs text-[#999999] mr-1">{item.count}</span>}
                <RightOutlined className="text-[#E8E8E8] text-xs" />
              </button>
            ))}
          </div>
        </div>
      ))}

      <button
        onClick={handleLogout}
        className="w-full bg-white border border-[#E8E8E8] rounded-xl p-4 flex items-center justify-center gap-2 text-sm font-medium text-[#F53535] hover:bg-[#FDECEC] hover:border-[#F53535]/30 transition-colors"
      >
        <LogoutOutlined /> 退出登录
      </button>

      <p className="text-center text-xs text-[#999999] mt-8">AI 超级面试 v1.0.0</p>

      <Modal
        title={
          <div className="flex items-center gap-2">
            <EditOutlined className="text-[#D9A441]" />
            <span className="text-lg font-bold text-[#232529]">编辑个人资料</span>
          </div>
        }
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        onOk={handleSaveProfile}
        okText="保存"
        cancelText="取消"
        okButtonProps={{ className: '!bg-[#D9A441] !border-[#D9A441] hover:!bg-[#A97E24] !rounded-lg !px-6' }}
        cancelButtonProps={{ className: '!rounded-lg !px-6' }}
        width={520}
        destroyOnClose
      >
        <div className="py-2">
          <div className="flex flex-col items-center mb-6">
            <Upload
              accept="image/*"
              showUploadList={false}
              beforeUpload={async (file) => {
                try {
                  const record = await uploadAvatar(file);
                  setEditForm((prev) => ({ ...prev, avatar: record.file_url }));
                } catch {
                  message.error('头像上传失败，请重试');
                }
                return false;
              }}
            >
              <div className="relative cursor-pointer group">
                <Avatar
                  size={80}
                  src={editForm.avatar}
                  className="!bg-[#232529] !text-white !font-bold !text-2xl ring-4 ring-[#F7F8FA]"
                >
                  {avatarUploading ? '...' : (editForm.nickname[0] || 'U')}
                </Avatar>
                <div className="absolute inset-0 bg-black/40 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  {avatarUploading ? (
                    <span className="text-white text-xs">上传中</span>
                  ) : (
                    <CameraOutlined className="text-white text-xl" />
                  )}
                </div>
              </div>
            </Upload>
            <p className="text-xs text-[#999999] mt-2">点击头像更换图片</p>
          </div>

          <div className="space-y-5">
            <div className="bg-[#F7F8FA] rounded-xl p-4">
              <h4 className="text-xs font-semibold text-[#999999] uppercase tracking-wider mb-3">基础信息</h4>
              <div>
                <label className="text-sm font-medium text-[#232529] block mb-1.5">昵称</label>
                <Input
                  value={editForm.nickname}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, nickname: e.target.value }))}
                  placeholder="请输入昵称"
                  maxLength={20}
                  showCount
                  className="!rounded-lg"
                />
              </div>
            </div>

            <div className="bg-[#F7F8FA] rounded-xl p-4">
              <h4 className="text-xs font-semibold text-[#999999] uppercase tracking-wider mb-3">个人信息</h4>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-sm font-medium text-[#232529]">
                        <WomanOutlined className="mr-1" />性别
                      </label>
                      <Switch
                        size="small"
                        checked={editForm.profileVisibility.gender}
                        onChange={(checked) => setEditForm((prev) => ({
                          ...prev,
                          profileVisibility: { ...prev.profileVisibility, gender: checked },
                        }))}
                      />
                    </div>
                    <Radio.Group
                      value={editForm.gender}
                      onChange={(e) => setEditForm((prev) => ({ ...prev, gender: e.target.value }))}
                      optionType="button"
                      buttonStyle="solid"
                      size="middle"
                      className="!w-full"
                    >
                      <Radio.Button value="male" className="!w-1/2 !text-center">
                        <ManOutlined className="mr-1" />男
                      </Radio.Button>
                      <Radio.Button value="female" className="!w-1/2 !text-center">
                        <WomanOutlined className="mr-1" />女
                      </Radio.Button>
                    </Radio.Group>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-sm font-medium text-[#232529]">
                        <CalendarOutlined className="mr-1" />生日
                      </label>
                      <Switch
                        size="small"
                        checked={editForm.profileVisibility.birthday}
                        onChange={(checked) => setEditForm((prev) => ({
                          ...prev,
                          profileVisibility: { ...prev.profileVisibility, birthday: checked },
                        }))}
                      />
                    </div>
                    <DatePicker
                      value={editForm.birthday ? dayjs(editForm.birthday) : null}
                      placeholder="选择生日"
                      className="!w-full !rounded-lg"
                      onChange={(_, dateStr) => setEditForm((prev) => ({ ...prev, birthday: dateStr as string }))}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-sm font-medium text-[#232529]">
                      <SmileOutlined className="mr-1" />个人签名
                    </label>
                    <Switch
                      size="small"
                      checked={editForm.profileVisibility.bio}
                      onChange={(checked) => setEditForm((prev) => ({
                        ...prev,
                        profileVisibility: { ...prev.profileVisibility, bio: checked },
                      }))}
                    />
                  </div>
                  <Input.TextArea
                    value={editForm.bio}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, bio: e.target.value }))}
                    placeholder="写一句话介绍自己..."
                    maxLength={100}
                    showCount
                    rows={2}
                    className="!rounded-lg"
                  />
                </div>
              </div>
            </div>

            <div className="bg-[#F7F8FA] rounded-xl p-4">
              <h4 className="text-xs font-semibold text-[#999999] uppercase tracking-wider mb-3">联系方式</h4>
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-sm font-medium text-[#232529]">
                      <PhoneOutlined className="mr-1" />手机号
                    </label>
                    <Switch
                      size="small"
                      checked={editForm.profileVisibility.phone}
                      onChange={(checked) => setEditForm((prev) => ({
                        ...prev,
                        profileVisibility: { ...prev.profileVisibility, phone: checked },
                      }))}
                    />
                  </div>
                  <Input
                    value={editForm.phone}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, phone: e.target.value }))}
                    placeholder="请输入手机号"
                    maxLength={11}
                    className="!rounded-lg"
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-sm font-medium text-[#232529]">
                      <EnvironmentOutlined className="mr-1" />所在地
                    </label>
                    <Switch
                      size="small"
                      checked={editForm.profileVisibility.location}
                      onChange={(checked) => setEditForm((prev) => ({
                        ...prev,
                        profileVisibility: { ...prev.profileVisibility, location: checked },
                      }))}
                    />
                  </div>
                  <Input
                    value={editForm.location}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, location: e.target.value }))}
                    placeholder="如：北京、上海、杭州..."
                    maxLength={30}
                    className="!rounded-lg"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        title={
          <div className="flex items-center gap-2">
            <FileTextOutlined className="text-[#D9A441]" />
            <span className="text-lg font-bold text-[#232529]">我的简历</span>
          </div>
        }
        open={resumeModalOpen}
        onCancel={() => setResumeModalOpen(false)}
        footer={null}
        width={560}
        destroyOnClose
      >
        <div className="py-2">
          {resumesLoading && resumes.length === 0 ? (
            <div className="flex justify-center py-8">
              <Spin size="small" />
            </div>
          ) : resumes.length === 0 ? (
            <Empty
              description="还没有上传简历"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              className="!my-8"
            />
          ) : (
            <div className="space-y-2 mb-6 max-h-[300px] overflow-y-auto">
              {resumes.map((resume) => (
                <div
                  key={resume.id}
                  className="flex items-center gap-3 bg-[#F7F8FA] rounded-xl p-3 hover:bg-[#EEEEEE] transition-colors group"
                >
                  <div className="w-10 h-10 rounded-lg bg-[#F7EBD3] flex items-center justify-center flex-shrink-0">
                    <FileTextOutlined className="text-[#D9A441] text-lg" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-[#232529] truncate">{resume.file_name}</p>
                      <span
                        className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                          resume.status === 1
                            ? 'bg-[#F7EBD3] text-[#00B578]'
                            : resume.status === 2
                              ? 'bg-[#FDECEC] text-[#F53535]'
                              : 'bg-[#FFF7E0] text-[#FFAA00]'
                        }`}
                      >
                        {RESUME_STATUS_LABEL[resume.status] ?? '未知'}
                      </span>
                    </div>
                    <p className="text-xs text-[#999999] mt-0.5">
                      {new Date(resume.created_at).toLocaleDateString('zh-CN', {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {resume.status === 2 && (
                      <button
                        onClick={() => handleRetryResume(resume)}
                        className="w-8 h-8 rounded-lg bg-white border border-[#E8E8E8] flex items-center justify-center hover:border-[#FFAA00] hover:text-[#FFAA00] transition-colors"
                        title="重新分析"
                      >
                        <ReloadOutlined className="text-sm" />
                      </button>
                    )}
                    <button
                      onClick={() => handleStartInterview(resume.id)}
                      className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
                        resume.status === 1
                          ? 'bg-[#D9A441] hover:bg-[#A97E24]'
                          : 'bg-[#E8E8E8] cursor-not-allowed'
                      }`}
                      title={resume.status === 1 ? '使用此简历去面试' : '简历尚未就绪'}
                    >
                      <ThunderboltOutlined className="text-white text-sm" />
                    </button>
                    <Popconfirm
                      title="确定要删除这份简历吗？"
                      onConfirm={() => handleDeleteResume(resume)}
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                    >
                      <button
                        className="w-8 h-8 rounded-lg bg-white border border-[#E8E8E8] flex items-center justify-center hover:border-[#F53535] hover:text-[#F53535] transition-colors"
                        title="删除简历"
                      >
                        <DeleteOutlined className="text-sm" />
                      </button>
                    </Popconfirm>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="border-t border-[#E8E8E8] pt-4">
            <p className="text-sm font-medium text-[#232529] mb-3 flex items-center gap-1.5">
              <PlusOutlined className="text-[#D9A441]" />上传新简历
            </p>
            <FileUpload
              fileType="resume"
              onUploaded={handleResumeUploaded}
              onError={handleResumeUploadError}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ProfilePage;