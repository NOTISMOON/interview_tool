import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Suspense } from 'react';
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
  ThunderboltFilled,
} from '@ant-design/icons';
import { useAppStore } from '@/store';
import { getUnreadCount } from '@/lib/api/messages';
import { useMessageVersion } from '@/lib/messageVersion';
import { useState, useEffect, useRef } from 'react';
import gsap from 'gsap';

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
    <aside className="w-[240px] h-screen bg-[#16181C] flex flex-col flex-shrink-0 fixed left-0 top-0">
      <div
        className="h-[60px] flex items-center gap-2.5 px-5 border-b border-[rgba(255,255,255,0.06)] cursor-pointer"
        onClick={() => navigate('/dashboard')}
      >
        <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#00BFA5] to-[#4DC9B4] flex items-center justify-center text-white text-sm shadow-[0_2px_8px_rgba(0,191,165,0.35)]">
          <ThunderboltFilled />
        </span>
        <span className="font-bold text-white">面试教练</span>
      </div>

      <nav className="flex-1 py-4 px-3 overflow-y-auto">
        <div className="text-[10px] text-[rgba(255,255,255,0.2)] uppercase tracking-wider font-semibold px-3 pb-2">导航</div>
        {SIDEBAR_ITEMS.map((item) => {
          const isActive = location.pathname === item.key;
          return (
            <button
              key={item.key}
              onClick={() => navigate(item.key)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg mb-0.5 text-sm font-medium transition-all duration-150 ${
                isActive
                  ? 'bg-[rgba(0,191,165,0.12)] text-[#00BFA5] font-semibold'
                  : 'text-[#8B909A] hover:bg-[rgba(255,255,255,0.06)] hover:text-[#D1D5DB]'
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="p-3 border-t border-[rgba(255,255,255,0.06)]">
        <button
          onClick={() => {
            const { logout } = useAppStore.getState();
            logout();
            navigate('/login', { replace: true });
          }}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-[#8B909A] hover:bg-[rgba(255,255,255,0.06)] hover:text-[#F87171] transition-all duration-150"
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
  const location = useLocation();
  const { user } = useAppStore();
  const { revision: msgRevision } = useMessageVersion();
  const [unreadCount, setUnreadCount] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);

  /** 页面切换动画：每次路由变化都触发淡入 */
  useEffect(() => {
    if (contentRef.current) {
      gsap.fromTo(
        contentRef.current,
        { y: 12, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.35, ease: 'power2.out', clearProps: 'transform,opacity' },
      );
    }
  }, [location.pathname]);

  /** 获取未读计数 */
  const fetchUnreadCount = async () => {
    try {
      const res = await getUnreadCount();
      setUnreadCount(res.total);
    } catch {
      // 静默失败
    }
  };

  useEffect(() => {
    if (!user) return;
    fetchUnreadCount();
  }, [user]);

  // 全局消息版本号变化（收到 SSE 通知 / 未读 / 系统广播）时刷新未读数
  useEffect(() => {
    if (!user) return;
    fetchUnreadCount();
  }, [msgRevision, user]);

  // 路由变化时重新获取未读计数（确保消息中心页面操作后更新）
  useEffect(() => {
    fetchUnreadCount();
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-[#F1F2F4]">
      <Sidebar />

      <div className="ml-[240px]">
        <header className="h-[60px] bg-[#16181C] border-b border-[rgba(255,255,255,0.06)] flex items-center justify-between px-6 sticky top-0 z-30">
          <div>
            <span className="text-sm text-[#8B909A]">欢迎回来，</span>
            <span className="text-sm font-semibold text-white">{user?.nickname || '用户'}</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/dashboard/messages')}
              className="relative w-9 h-9 rounded-lg border border-[rgba(255,255,255,0.1)] bg-[rgba(255,255,255,0.04)] flex items-center justify-center text-[#8B909A] hover:border-[#00BFA5] hover:text-[#00BFA5] transition-all"
            >
              <Badge count={unreadCount} size="small" offset={[2, -2]}>
                <BellOutlined className="text-lg" />
              </Badge>
            </button>
            <button
              onClick={() => navigate('/dashboard/profile')}
              className="w-8 h-8 rounded-full bg-[#00BFA5] flex items-center justify-center text-white text-xs font-bold hover:ring-2 hover:ring-[#00BFA5]/50 transition-all"
            >
              {user?.avatar ? (
                <img src={user.avatar} alt="" className="w-full h-full rounded-full object-cover" />
              ) : (
                user?.nickname?.[0] || 'U'
              )}
            </button>
          </div>
        </header>

        <main className="p-6 h-[calc(100vh-60px)] overflow-y-auto bg-[#F1F2F4]">
          <div ref={contentRef}>
            <Suspense fallback={<div className="flex items-center justify-center py-20"><span className="w-6 h-6 rounded-full border-2 border-[#E8E8E8] border-t-[#00BFA5] animate-spin" /></div>}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;