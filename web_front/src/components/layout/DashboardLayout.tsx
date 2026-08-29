﻿﻿import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Suspense } from 'react';
import Badge from 'antd/es/badge';
import Modal from 'antd/es/modal';
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
} from '@/components/icons';
import { useAppStore } from '@/store';
import { getUnreadCount } from '@/lib/api/messages';
import { useMessageVersion } from '@/lib/messageVersion';
import { subscribeSSE } from '@/lib/sseBus';
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

/** 主题存储 key */
const THEME_STORAGE_KEY = 'app_theme';

/** 读取并应用初始主题（默认炭黑暗色） */
function applyInitialTheme() {
  let theme: string | null = null;
  try {
    theme = localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    /* localStorage 不可用忽略 */
  }
  document.documentElement.setAttribute('data-theme', theme === 'light' ? 'light' : 'dark');
}

/** 侧边栏（与原型 glass-admin-prototype.html 一比一） */
const Sidebar = () => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside
      className="w-[232px] h-screen bg-[var(--color-surface)] flex flex-col flex-shrink-0"
      style={{ borderRight: '1px solid var(--color-line)' }}
    >
      <div
        className="h-[56px] flex items-center gap-2.5 px-[18px] cursor-pointer flex-shrink-0"
        style={{ borderBottom: '1px solid var(--color-line)' }}
        onClick={() => navigate('/dashboard')}
      >
        <span className="w-[26px] h-[26px] rounded-[8px] bg-[#D9A441] flex items-center justify-center text-[#0B0B0C]">
          <ThunderboltFilled />
        </span>
        <span className="font-bold text-[15px] text-[var(--color-ink)] tracking-[0.3px]">AI 超级面试</span>
      </div>

      <nav className="flex-1 py-3 px-3 overflow-y-auto">
        <div className="text-[10px] text-[var(--color-slate)] uppercase tracking-[1.6px] font-semibold px-2.5 pb-2.5">导航</div>
        {SIDEBAR_ITEMS.map((item) => {
          const isActive = location.pathname === item.key;
          return (
            <button
              key={item.key}
              onClick={() => navigate(item.key)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-[9px] mb-1 text-[13.5px] font-medium transition-colors duration-150 ${
                isActive
                  ? 'bg-[rgba(217,164,65,0.12)] text-[var(--color-ink)] font-semibold shadow-[inset_0_0_0_1px_rgba(217,164,65,0.35)]'
                  : 'text-[var(--color-rock)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)]'
              }`}
            >
              <span className={`text-lg ${isActive ? 'text-[#D9A441]' : 'opacity-85'}`}>{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      <div
        className="px-3 py-3 flex-shrink-0"
        style={{ borderTop: '1px solid var(--color-line)' }}
      >
        <button
          onClick={() => {
            const { logout } = useAppStore.getState();
            logout();
            navigate('/login', { replace: true });
          }}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-[9px] text-[13.5px] font-medium text-[var(--color-rock)] hover:bg-[var(--color-surface-hover)] hover:text-[#E07A6A] transition-colors duration-150"
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
  const { revision: msgRevision, bump: bumpRevision } = useMessageVersion();
  const [unreadCount, setUnreadCount] = useState(0);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const contentRef = useRef<HTMLDivElement>(null);

  /** 挂载时应用初始主题 */
  useEffect(() => {
    applyInitialTheme();
    setTheme(document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark');
  }, []);

  /** 切换主题（深色炭黑/浅色米白，localStorage 记忆） */
  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* localStorage 不可用忽略 */
    }
  };

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

  /** SSE: 统一处理所有事件；版本号递增 + session_kicked 下线处理 */
  useEffect(() => {
    const unsub = subscribeSSE((data) => {
      const kind = (data.kind as string) || 'message';
      // 所有事件都 bump 版本号，触发未读数刷新
      bumpRevision(kind);

      if (kind === 'session_kicked') {
        // 检查 jti：如果 jti 与当前设备相同，说明是自己刚登录发的，跳过
        const myJti = localStorage.getItem('auth_jti');
        if (myJti && data.jti === myJti) {
          return;
        }
        // 清除本地登录状态
        localStorage.removeItem('auth_user');
        localStorage.removeItem('auth_jti');
        // 弹出下线提示框
        Modal.confirm({
          title: '账号已在其他设备登录',
          icon: null,
          content: '您的账号已在其他设备登录，请重新登录。',
          okText: '确定',
          cancelText: null,
          cancelButtonProps: { style: { display: 'none' } },
          centered: true,
          maskClosable: false,
          keyboard: false,
          onOk: () => {
            window.location.href = '/login';
          },
        });
      }
    });
    return unsub;
  }, [bumpRevision]);

  return (
    <div className="h-screen overflow-hidden bg-[var(--color-bg)] text-[var(--color-ink)] flex">
      <Sidebar />

      {/* 主区 */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* 顶栏 */}
        <header
          className="h-[56px] bg-[var(--color-surface)] flex items-center justify-between px-[22px] flex-shrink-0 z-30"
          style={{ borderBottom: '1px solid var(--color-line)' }}
        >
          <div className="text-[13.5px] text-[var(--color-rock)]">
            欢迎回来，<b className="font-semibold text-[var(--color-ink)]">{user?.nickname || '用户'}</b>
          </div>

          <div className="flex items-center gap-[10px]">
            {/* 主题切换 */}
            <button
              onClick={toggleTheme}
              title={theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'}
              className="h-8 flex items-center gap-1.5 px-2.5 rounded-full border border-[var(--color-line)] bg-transparent text-[12px] text-[var(--color-rock)] hover:text-[var(--color-ink)] hover:bg-[var(--color-surface-hover)] transition-colors"
            >
              {theme === 'dark' ? (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/><circle cx="12" cy="12" r="4"/></svg>
              ) : (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8Z" /></svg>
              )}
              主题
            </button>
            {/* 通知铃铛 */}
            <button
              onClick={() => navigate('/dashboard/messages')}
              className="relative w-[34px] h-[34px] rounded-[10px] border border-[var(--color-line)] bg-transparent flex items-center justify-center text-[var(--color-ink)] hover:border-[#D9A441]/50 hover:text-[#D9A441] hover:bg-[rgba(217,164,65,0.08)] transition-colors"
            >
              <Badge count={unreadCount} size="small" offset={[2, -2]}>
                <BellOutlined className="text-lg !text-[var(--color-ink)]" />
              </Badge>
            </button>
            {/* 头像 */}
            <button
              onClick={() => navigate('/dashboard/profile')}
              className="w-[34px] h-[34px] rounded-full bg-[#D9A441] text-[#0B0B0C] flex items-center justify-center text-[13px] font-bold"
            >
              {user?.avatar ? (
                <img src={user.avatar} alt="" className="w-full h-full rounded-full object-cover" />
              ) : (
                user?.nickname?.[0] || 'U'
              )}
            </button>
          </div>
        </header>

        {/* 内容区 */}
        <main className="flex-1 min-h-0 overflow-y-auto bg-[var(--color-bg)] p-[22px]">
          <div ref={contentRef}>
            <Suspense fallback={<div className="flex items-center justify-center py-20"><span className="w-6 h-6 rounded-full border-2 border-[var(--color-line)] border-t-[#D9A441] animate-spin" /></div>}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;