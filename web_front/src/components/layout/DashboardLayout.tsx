import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Badge } from 'antd';
import {
  HomeOutlined,
  PlayCircleOutlined,
  HistoryOutlined,
  TeamOutlined,
  BellOutlined,
  SettingOutlined,
  LogoutOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useAppStore } from '@/store';

const SIDEBAR_ITEMS = [
  { key: '/dashboard', label: '工作台', icon: <HomeOutlined /> },
  { key: '/dashboard/interview', label: '开始面试', icon: <PlayCircleOutlined /> },
  { key: '/dashboard/history', label: '面试记录', icon: <HistoryOutlined /> },
  { key: '/dashboard/feed', label: '动态', icon: <ThunderboltOutlined /> },
  { key: '/dashboard/community', label: '社区', icon: <TeamOutlined /> },
  { key: '/dashboard/messages', label: '消息中心', icon: <BellOutlined /> },
  { key: '/dashboard/profile', label: '个人设置', icon: <SettingOutlined /> },
];

const Sidebar = () => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside className="w-[240px] h-screen bg-white border-r border-[#E1E4E8] flex flex-col flex-shrink-0 fixed left-0 top-0">
      <div
        className="h-[60px] flex items-center gap-2.5 px-5 border-b border-[#F0F2F5] cursor-pointer"
        onClick={() => navigate('/dashboard')}
      >
        <span className="w-8 h-8 rounded-lg bg-[#FF6B35] flex items-center justify-center text-white text-sm font-bold">
          AI
        </span>
        <span className="font-bold text-[#0D1117]">面试教练</span>
      </div>

      <nav className="flex-1 py-4 px-3 overflow-y-auto">
        {SIDEBAR_ITEMS.map((item) => {
          const isActive = location.pathname === item.key;
          return (
            <button
              key={item.key}
              onClick={() => navigate(item.key)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 text-sm font-medium transition-all duration-150 ${
                isActive
                  ? 'bg-[#FFF3ED] text-[#FF6B35]'
                  : 'text-[#5F6B7A] hover:bg-[#F6F8FA] hover:text-[#0D1117]'
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="p-3 border-t border-[#F0F2F5]">
        <button
          onClick={() => {
            const { logout } = useAppStore.getState();
            logout();
            navigate('/login', { replace: true });
          }}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-[#5F6B7A] hover:bg-[#FEF2F2] hover:text-[#CF222E] transition-all duration-150"
        >
          <LogoutOutlined className="text-lg" />
          退出登录
        </button>
      </div>
    </aside>
  );
};

const DashboardLayout = () => {
  const navigate = useNavigate();
  const { user } = useAppStore();

  return (
    <div className="min-h-screen bg-[#F6F8FA]">
      <Sidebar />

      <div className="ml-[240px]">
        <header className="h-[60px] bg-white border-b border-[#E1E4E8] flex items-center justify-between px-6 sticky top-0 z-30">
          <div>
            <span className="text-sm text-[#8B949E]">欢迎回来，</span>
            <span className="text-sm font-semibold text-[#0D1117]">{user?.nickname || '用户'}</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/dashboard/messages')}
              className="relative w-9 h-9 rounded-lg flex items-center justify-center text-[#5F6B7A] hover:bg-[#F6F8FA] hover:text-[#0D1117] transition-colors"
            >
              <Badge dot size="small">
                <BellOutlined className="text-lg" />
              </Badge>
            </button>
            <button
              onClick={() => navigate('/dashboard/profile')}
              className="w-8 h-8 rounded-full bg-[#0D1117] flex items-center justify-center text-white text-xs font-bold hover:ring-2 hover:ring-[#FF6B35]/30 transition-all"
            >
              {user?.avatar ? (
                <img src={user.avatar} alt="" className="w-full h-full rounded-full object-cover" />
              ) : (
                user?.nickname?.[0] || 'U'
              )}
            </button>
          </div>
        </header>

        <main className="p-6">
          <div className="animate-fade-in-up">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;