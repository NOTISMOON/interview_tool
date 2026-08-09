import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar, App, Divider, Modal, Input, Upload } from 'antd';
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
} from '@ant-design/icons';
import { useAppStore } from '@/store';

const ProfilePage = () => {
  const navigate = useNavigate();
  const { message, modal } = App.useApp();
  const { user, logout, updateUser, resumes, reports } = useAppStore();

  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editNickname, setEditNickname] = useState('');
  const [editAvatar, setEditAvatar] = useState('');

  const reportList = Object.values(reports);
  const totalScore = reportList.length > 0
    ? Math.round(reportList.reduce((sum, r) => sum + r.totalScore, 0) / reportList.length)
    : 0;

  const handleLogout = () => {
    modal.confirm({
      title: '确定要退出登录吗？',
      content: '退出后需要重新登录才能使用',
      okText: '退出',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => { logout(); navigate('/login', { replace: true }); },
    });
  };

  const openEditModal = () => {
    setEditNickname(user?.nickname || '');
    setEditAvatar(user?.avatar || '');
    setEditModalOpen(true);
  };

  const handleSaveProfile = () => {
    if (!editNickname.trim()) {
      message.warning('昵称不能为空');
      return;
    }
    updateUser(editNickname.trim(), editAvatar || undefined);
    message.success('资料已更新');
    setEditModalOpen(false);
  };

  const menuGroups = [
    {
      title: '数据',
      items: [
        { icon: <FileTextOutlined />, label: '我的简历', count: resumes.length, color: '#FF6B35', bg: '#FFF3ED', onClick: () => navigate('/dashboard/interview') },
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
            onClick={() => navigate('/dashboard/interview')}
          >
            <div className="text-white font-bold text-lg">{resumes.length}</div>
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
                  {item.count !== undefined && <span className="text-xs text-[#8B949E] mr-1">{item.count}</span>}
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
        title="编辑资料"
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        onOk={handleSaveProfile}
        okText="保存"
        cancelText="取消"
        okButtonProps={{ className: '!bg-[#FF6B35] !border-[#FF6B35] hover:!bg-[#E85D26]' }}
        destroyOnClose
      >
        <div className="py-4">
          <div className="flex flex-col items-center mb-6">
            <Upload
              accept="image/*"
              showUploadList={false}
              beforeUpload={(file) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                  setEditAvatar(e.target?.result as string);
                };
                reader.readAsDataURL(file);
                return false;
              }}
            >
              <div className="relative cursor-pointer group">
                <Avatar
                  size={72}
                  src={editAvatar}
                  className="!bg-[#0D1117] !text-white !font-bold !text-xl"
                >
                  {editNickname[0] || 'U'}
                </Avatar>
                <div className="absolute inset-0 bg-black/40 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <CameraOutlined className="text-white text-lg" />
                </div>
              </div>
            </Upload>
            <p className="text-xs text-[#8B949E] mt-2">点击头像更换图片</p>
          </div>
          <div>
            <label className="text-sm font-medium text-[#0D1117] block mb-2">昵称</label>
            <Input
              value={editNickname}
              onChange={(e) => setEditNickname(e.target.value)}
              placeholder="请输入昵称"
              maxLength={20}
              showCount
              className="!rounded-lg"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ProfilePage;