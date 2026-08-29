import { useNavigate } from 'react-router-dom';
import { HomeOutlined, DashboardOutlined } from '@/components/icons';
import { useAppStore } from '@/store';

const NotFoundPage = () => {
  const navigate = useNavigate();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);

  const handleGoHome = () => {
    navigate(isLoggedIn ? '/dashboard' : '/');
  };

  return (
    <div className="min-h-screen bg-[#232529] flex items-center justify-center px-6">
      <div className="text-center max-w-md">
        <div className="text-[120px] font-extrabold leading-none mb-4">
          <span className="gradient-text">404</span>
        </div>
        <h1 className="text-2xl font-extrabold text-white mb-3">
          页面不见了
        </h1>
        <p className="text-[#999999] text-sm leading-relaxed mb-8">
          你访问的页面可能已被删除、移动或暂时不可用。
          <br />
          请检查网址是否正确，或返回首页继续浏览。
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={handleGoHome}
            className="btn-flame btn-flame-lg"
          >
            {isLoggedIn ? <DashboardOutlined /> : <HomeOutlined />}
            {isLoggedIn ? '返回工作台' : '返回首页'}
          </button>
          <button
            onClick={() => navigate(-1)}
            className="btn-ghost btn-ghost-lg !text-white !border-white/20 hover:!border-white/50"
          >
            返回上一步
          </button>
        </div>
      </div>
    </div>
  );
};

export default NotFoundPage;