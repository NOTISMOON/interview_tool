import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar, App, Divider, Modal, Input, Upload, DatePicker, Radio, Empty, Popconfirm, Switch } from 'antd';
import dayjs from 'dayjs';
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
} from '@ant-design/icons';
import type { ProfileVisibility } from '@/types';
import type { UploadRecord } from '@/types/upload';
import { useAppStore } from '@/store';
import { FileUpload } from '@/components/upload/FileUpload';
import { deleteUploadRecord, getUploadRecords } from '@/lib/api/upload';
import { useUpload } from '@/hooks/useUpload';

const ProfilePage = () => {
  const navigate = useNavigate();
  const { message, modal } = App.useApp();
  const { user, logout, updateUser, refreshUser, resumes, removeResume, reports } = useAppStore();
  const { upload: uploadAvatar, uploading: avatarUploading } = useUpload('avatar');

  const reportList = Object.values(reports);
  const totalScore = reportList.length > 0
    ? Math.round(reportList.reduce((sum, r) => sum + r.totalScore, 0) / reportList.length)
    : 0;

  const [editModalOpen, setEditModalOpen] = useState(false);
  const [resumeModalOpen, setResumeModalOpen] = useState(false);
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
  /** 服务端真实上传记录（COS直传落库，id为纯数字） */
  const [remoteResumes, setRemoteResumes] = useState<UploadRecord[]>([]);

  /** 拉取服务端简历上传记录（失败静默，保留本地列表） */
  const loadRemoteResumes = async () => {
    try {
      const res = await getUploadRecords('resume');
      setRemoteResumes(res.items);
    } catch {
      // 接口失败不影响本地简历展示
    }
  };

  // 进入页面时拉取一次真实上传记录 + 刷新个人资料
  // 后端已开启ETag协商缓存：每次进入都发请求，数据未变返回304（极快），
  // 数据更新（如关注数变化）返回200新数据并同步更新store与localStorage
  useEffect(() => {
    loadRemoteResumes();
    refreshUser();
  }, []);

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

  /** 上传成功回调：刷新服务端记录列表并提示 */
  const handleResumeUploaded = async () => {
    message.success('简历上传成功');
    await loadRemoteResumes();
  };

  /** 上传失败回调：展示用户可读错误 */
  const handleResumeUploadError = (errMsg: string) => {
    message.error(errMsg);
  };

  /** 删除简历：服务端记录（纯数字id）走COS删除接口，本地mock直接移除 */
  const handleDeleteResume = async (resumeId: string) => {
    if (/^\d+$/.test(resumeId)) {
      try {
        await deleteUploadRecord(Number(resumeId));
        await loadRemoteResumes();
        message.success('简历已删除');
      } catch {
        message.error('删除简历失败，请重试');
      }
      return;
    }
    removeResume(resumeId);
    message.success('简历已删除');
  };

  const handleStartInterview = (_resumeId?: string) => {
    setResumeModalOpen(false);
    navigate('/dashboard/interview');
  };

  /** 合并展示列表：服务端真实记录在前，本地mock简历在后 */
  const resumeItems: { id: string; fileName: string; uploadTime: string }[] = [
    ...remoteResumes.map((r) => ({ id: String(r.upload_id), fileName: r.file_name, uploadTime: r.created_at })),
    ...resumes,
  ];

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
        { icon: <FileTextOutlined />, label: '我的简历', count: resumes.length + remoteResumes.length, color: '#FF6B35', bg: '#FFF3ED', onClick: () => setResumeModalOpen(true) },
        { icon: <HistoryOutlined />, label: '面试记录', count: reportList.length, color: '#2DA44E', bg: '#ECFDF3', onClick: () => navigate('/dashboard/history') },
        { icon: <TrophyOutlined />, label: '平均得分', count: totalScore ? `${totalScore} 分` : '--', color: '#BF8700', bg: '#FFF8E6', onClick: () => navigate('/dashboard/history') },
      ],
    },
    {
      title: '社交',
      items: [
        { icon: <TeamOutlined />, label: '我的关注', count: user?.followingCount ?? 0, color: '#FF6B35', bg: '#FFF3ED', onClick: () => navigate('/dashboard/following') },
        { icon: <UserAddOutlined />, label: '我的粉丝', count: user?.followersCount ?? 0, color: '#2DA44E', bg: '#ECFDF3', onClick: () => navigate('/dashboard/followers') },
      ],
    },
    {
      title: '功能',
      items: [
        { icon: <BellOutlined />, label: '消息中心', color: '#FF6B35', bg: '#FFF3ED', onClick: () => navigate('/dashboard/messages') },
        { icon: <StarOutlined />, label: '我的收藏', color: '#BF8700', bg: '#FFF8E6', onClick: () => navigate('/dashboard/favorites') },
        { icon: <ShareAltOutlined />, label: '邀请好友', color: '#2DA44E', bg: '#ECFDF3', onClick: () => message.info('功能开发中') },
      ],
    },
    {
      title: '其他',
      items: [
        { icon: <SettingOutlined />, label: '设置', color: '#5F6B7A', bg: '#F6F8FA', onClick: () => navigate('/dashboard/settings') },
        { icon: <SafetyOutlined />, label: '隐私政策', color: '#5F6B7A', bg: '#F6F8FA', onClick: () => navigate('/privacy') },
        { icon: <QuestionCircleOutlined />, label: '帮助与反馈', color: '#5F6B7A', bg: '#F6F8FA', onClick: () => navigate('/dashboard/help') },
      ],
    },
  ];

  return (
    <div className="max-w-[700px]">
      <h1 className="text-xl font-bold text-[#0D1117] mb-6">个人设置</h1>

      <div className="bg-[#0D1117] rounded-2xl p-6 mb-6">
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
            <div className="text-white font-bold text-lg">{resumes.length + remoteResumes.length}</div>
            <div className="text-white/50 text-xs">简历</div>
          </div>
          <div
            className="bg-white/10 rounded-xl p-3 text-center cursor-pointer hover:bg-white/15 transition-colors"
            onClick={() => navigate('/dashboard/history')}
          >
            <div className="text-white font-bold text-lg">{reportList.length}</div>
            <div className="text-white/50 text-xs">面试</div>
          </div>
        </div>
      </div>

      {menuGroups.map((group) => (
        <div key={group.title} className="mb-5">
          <h3 className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider mb-2 px-1">{group.title}</h3>
          <div className="bg-white border border-[#E1E4E8] rounded-xl overflow-hidden">
            {group.items.map((item, idx) => (
              <div key={item.label}>
                {idx > 0 && <Divider className="!m-0" />}
                <button
                  onClick={item.onClick}
                  className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-[#F6F8FA] transition-colors text-left"
                >
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ color: item.color, backgroundColor: item.bg }}>
                    {item.icon}
                  </div>
                  <span className="flex-1 text-sm font-medium text-[#0D1117]">{item.label}</span>
                  {'count' in item && item.count !== undefined && <span className="text-xs text-[#8B949E] mr-1">{item.count}</span>}
                  <RightOutlined className="text-[#E1E4E8] text-xs" />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}

      <button
        onClick={handleLogout}
        className="w-full bg-white border border-[#E1E4E8] rounded-xl p-4 flex items-center justify-center gap-2 text-sm font-medium text-[#CF222E] hover:bg-[#FFF0F1] hover:border-[#CF222E]/30 transition-colors"
      >
        <LogoutOutlined /> 退出登录
      </button>

      <p className="text-center text-xs text-[#8B949E] mt-8">面试教练 v1.0.0</p>

      <Modal
        title={
          <div className="flex items-center gap-2">
            <EditOutlined className="text-[#FF6B35]" />
            <span className="text-lg font-bold text-[#0D1117]">编辑个人资料</span>
          </div>
        }
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        onOk={handleSaveProfile}
        okText="保存"
        cancelText="取消"
        okButtonProps={{ className: '!bg-[#FF6B35] !border-[#FF6B35] hover:!bg-[#E85D26] !rounded-lg !px-6' }}
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
                  className="!bg-[#0D1117] !text-white !font-bold !text-2xl ring-4 ring-[#F6F8FA]"
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
            <p className="text-xs text-[#8B949E] mt-2">点击头像更换图片</p>
          </div>

          <div className="space-y-5">
            <div className="bg-[#F6F8FA] rounded-xl p-4">
              <h4 className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider mb-3">基础信息</h4>
              <div>
                <label className="text-sm font-medium text-[#0D1117] block mb-1.5">昵称</label>
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

            <div className="bg-[#F6F8FA] rounded-xl p-4">
              <h4 className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider mb-3">个人信息</h4>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-sm font-medium text-[#0D1117]">
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
                      <label className="text-sm font-medium text-[#0D1117]">
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
                    <label className="text-sm font-medium text-[#0D1117]">
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

            <div className="bg-[#F6F8FA] rounded-xl p-4">
              <h4 className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider mb-3">联系方式</h4>
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-sm font-medium text-[#0D1117]">
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
                    <label className="text-sm font-medium text-[#0D1117]">
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
            <FileTextOutlined className="text-[#FF6B35]" />
            <span className="text-lg font-bold text-[#0D1117]">我的简历</span>
          </div>
        }
        open={resumeModalOpen}
        onCancel={() => setResumeModalOpen(false)}
        footer={null}
        width={560}
        destroyOnClose
      >
        <div className="py-2">
          {resumeItems.length === 0 ? (
            <Empty
              description="还没有上传简历"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              className="!my-8"
            />
          ) : (
            <div className="space-y-2 mb-6 max-h-[300px] overflow-y-auto">
              {resumeItems.map((resume) => (
                <div
                  key={resume.id}
                  className="flex items-center gap-3 bg-[#F6F8FA] rounded-xl p-3 hover:bg-[#EDF0F4] transition-colors group"
                >
                  <div className="w-10 h-10 rounded-lg bg-[#FFF3ED] flex items-center justify-center flex-shrink-0">
                    <FileTextOutlined className="text-[#FF6B35] text-lg" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-[#0D1117] truncate">{resume.fileName}</p>
                    <p className="text-xs text-[#8B949E]">
                      {new Date(resume.uploadTime).toLocaleDateString('zh-CN', {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => handleStartInterview(resume.id)}
                      className="w-8 h-8 rounded-lg bg-[#FF6B35] flex items-center justify-center hover:bg-[#E85D26] transition-colors"
                      title="使用此简历去面试"
                    >
                      <ThunderboltOutlined className="text-white text-sm" />
                    </button>
                    <Popconfirm
                      title="确定要删除这份简历吗？"
                      onConfirm={() => handleDeleteResume(resume.id)}
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                    >
                      <button
                        className="w-8 h-8 rounded-lg bg-white border border-[#E1E4E8] flex items-center justify-center hover:border-[#CF222E] hover:text-[#CF222E] transition-colors"
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

          <div className="border-t border-[#E1E4E8] pt-4">
            <p className="text-sm font-medium text-[#0D1117] mb-3 flex items-center gap-1.5">
              <PlusOutlined className="text-[#FF6B35]" />上传新简历
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