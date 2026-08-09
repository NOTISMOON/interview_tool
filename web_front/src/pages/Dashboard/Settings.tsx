import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Switch, Divider, Modal } from 'antd';
import {
  ArrowLeftOutlined,
  BellOutlined,
  SoundOutlined,
  EyeOutlined,
  LockOutlined,
  GlobalOutlined,
  DeleteOutlined,
} from '@ant-design/icons';

const SettingsPage = () => {
  const navigate = useNavigate();
  const { message: msg, modal } = App.useApp();
  const [emailNotify, setEmailNotify] = useState(true);
  const [pushNotify, setPushNotify] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [publicProfile, setPublicProfile] = useState(false);

  const handleClearCache = () => {
    modal.confirm({
      title: '清除缓存',
      content: '确定要清除所有本地缓存数据吗？',
      okText: '确定',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => {
        msg.success('缓存已清除');
      },
    });
  };

  const handleDeleteAccount = () => {
    modal.confirm({
      title: '注销账号',
      content: '注销后所有数据将被永久删除，此操作不可恢复。确定要注销吗？',
      okText: '确认注销',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => {
        msg.success('账号注销申请已提交');
      },
    });
  };

  const settingGroups = [
    {
      title: '通知设置',
      items: [
        {
          icon: <BellOutlined />,
          label: '邮件通知',
          desc: '接收面试报告、社区互动等邮件通知',
          action: <Switch checked={emailNotify} onChange={setEmailNotify} size="small" />,
        },
        {
          icon: <BellOutlined />,
          label: '推送通知',
          desc: '接收浏览器推送通知',
          action: <Switch checked={pushNotify} onChange={setPushNotify} size="small" />,
        },
        {
          icon: <SoundOutlined />,
          label: '声音提示',
          desc: '面试完成时播放提示音',
          action: <Switch checked={soundEnabled} onChange={setSoundEnabled} size="small" />,
        },
      ],
    },
    {
      title: '隐私设置',
      items: [
        {
          icon: <EyeOutlined />,
          label: '公开个人主页',
          desc: '允许其他用户查看你的个人主页',
          action: <Switch checked={publicProfile} onChange={setPublicProfile} size="small" />,
        },
        {
          icon: <LockOutlined />,
          label: '修改密码',
          desc: '更新你的登录密码',
          action: (
            <button
              onClick={() => msg.info('修改密码功能即将上线')}
              className="text-xs text-[#FF6B35] font-medium hover:text-[#E85D26] transition-colors"
            >
              修改
            </button>
          ),
        },
      ],
    },
    {
      title: '通用',
      items: [
        {
          icon: <GlobalOutlined />,
          label: '语言',
          desc: '界面显示语言',
          action: (
            <button
              onClick={() => msg.info('语言切换功能即将上线')}
              className="text-xs text-[#5F6B7A] font-medium hover:text-[#0D1117] transition-colors"
            >
              简体中文
            </button>
          ),
        },
        {
          icon: <DeleteOutlined />,
          label: '清除缓存',
          desc: '清除本地缓存数据',
          action: (
            <button
              onClick={handleClearCache}
              className="text-xs text-[#CF222E] font-medium hover:text-[#a0181e] transition-colors"
            >
              清除
            </button>
          ),
        },
      ],
    },
  ];

  return (
    <div className="max-w-[700px]">
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/dashboard/profile')}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#0D1117]">设置</h1>
      </div>

      {settingGroups.map((group) => (
        <div key={group.title} className="mb-5">
          <h3 className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider mb-2 px-1">
            {group.title}
          </h3>
          <div className="bg-white border border-[#E1E4E8] rounded-xl overflow-hidden">
            {group.items.map((item, idx) => (
              <div key={item.label}>
                {idx > 0 && <Divider className="!m-0" />}
                <div className="flex items-center gap-3 px-5 py-4">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center text-[#5F6B7A] bg-[#F6F8FA] flex-shrink-0">
                    {item.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-[#0D1117]">{item.label}</div>
                    <div className="text-xs text-[#8B949E] truncate">{item.desc}</div>
                  </div>
                  <div className="flex-shrink-0">{item.action}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="mt-8">
        <button
          onClick={handleDeleteAccount}
          className="w-full bg-white border border-[#E1E4E8] rounded-xl p-4 flex items-center justify-center gap-2 text-sm font-medium text-[#CF222E] hover:bg-[#FFF0F1] hover:border-[#CF222E]/30 transition-colors"
        >
          <DeleteOutlined /> 注销账号
        </button>
      </div>
    </div>
  );
};

export default SettingsPage;