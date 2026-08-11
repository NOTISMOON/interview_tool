import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAppStore } from '@/store';

const NAV_LINKS = [
  { label: '功能', href: '#features' },
  { label: '运作方式', href: '#how-it-works' },
  { label: '用户反馈', href: '#testimonials' },
];

const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  const navigate = useNavigate();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);

  if (typeof window !== 'undefined') {
    window.addEventListener('scroll', () => {
      setScrolled(window.scrollY > 20);
    });
  }

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-200 ${
        scrolled
          ? 'bg-white/90 backdrop-blur-xl border-b border-[#E1E4E8] shadow-sm'
          : 'bg-transparent'
      }`}
    >
      <div className="max-w-[1200px] mx-auto px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-10">
          <Link to="/" className="flex items-center gap-2.5 font-bold text-lg text-[#0D1117]">
            <span className="w-8 h-8 rounded-lg bg-[#FF6B35] flex items-center justify-center text-white text-sm">
              AI
            </span>
            面试教练
          </Link>
          <div className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="px-3 py-2 text-sm font-medium text-[#5F6B7A] hover:text-[#0D1117] rounded-lg hover:bg-[#F6F8FA] transition-colors"
              >
                {link.label}
              </a>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {isLoggedIn ? (
            <button
              onClick={() => navigate('/dashboard')}
              className="btn-flame"
            >
              进入后台
            </button>
          ) : (
            <>
              <button
                onClick={() => navigate('/login')}
                className="text-sm font-medium text-[#5F6B7A] hover:text-[#0D1117] px-3 py-2 rounded-lg transition-colors"
              >
                登录
              </button>
              <button
                onClick={() => navigate('/login')}
                className="btn-flame"
              >
                登录 / 注册
              </button>
            </>
          )}
        </div>
      </div>
    </nav>
  );
};

export default Navbar;