import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ThunderboltFilled } from '@/components/icons';
import { useAppStore } from '@/store';
import { useSlideInLeft } from '@/hooks/useGsapAnimations';

const NAV_LINKS = [
  { label: '功能', href: '#features' },
  { label: '运作方式', href: '#how-it-works' },
];

const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  const navigate = useNavigate();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);

  /** GSAP 入场动画 */
  const navRef = useSlideInLeft(0);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  return (
    <nav
      ref={navRef}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-200 ${
        scrolled
          ? 'bg-[var(--color-bg)]/90 backdrop-blur-xl border-b border-[var(--color-line)] shadow-sm'
          : 'bg-transparent'
      }`}
    >
      <div className="max-w-[1200px] mx-auto px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-10">
          <Link to="/" className="flex items-center gap-2.5 font-bold text-lg text-[var(--color-ink)]">
            <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#D9A441] to-[#E6AF4E] flex items-center justify-center text-white text-sm shadow-[0_2px_8px_rgba(217,164,65,0.35)]">
              <ThunderboltFilled />
            </span>
            AI 超级面试
          </Link>
          <div className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="px-3 py-2 text-sm font-medium text-[var(--color-rock)] hover:text-[var(--color-ink)] rounded-lg hover:bg-[var(--color-surface-2)] transition-colors"
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