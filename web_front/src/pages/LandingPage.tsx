import { useNavigate } from 'react-router-dom';
import { useAppStore } from '@/store';
import { useHeroEntrance, useScrollReveal } from '@/hooks/useGsapAnimations';
import {
  PlayCircleOutlined,
  FileTextOutlined,
  BarChartOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  RightOutlined,
  CheckCircleOutlined,
  ThunderboltFilled,
} from '@/components/icons';

const features = [
  {
    icon: <ThunderboltOutlined />,
    title: 'AI 智能出题',
    desc: '上传简历，AI 深度解析你的技术栈和项目经历，自动生成个性化面试题目，精准匹配目标岗位。',
  },
  {
    icon: <PlayCircleOutlined />,
    title: '仿真对话体验',
    desc: '逐题模拟真实面试场景，限时作答，还原面试现场的紧张感和节奏，让你提前适应。',
  },
  {
    icon: <BarChartOutlined />,
    title: '多维深度分析',
    desc: '从技术深度、表达逻辑、沟通能力等多维度评分，精准定位优势与短板，给出改进建议。',
  },
  {
    icon: <SyncOutlined />,
    title: '持续追踪进步',
    desc: '多轮面试对比分析，可视化能力成长曲线，见证每一次练习带来的提升。',
  },
];

const steps = [
  { step: 1, title: '上传简历', desc: '支持 PDF、Word 格式，AI 自动解析你的技能与经历' },
  { step: 2, title: 'AI 生成题目', desc: '根据简历内容，智能匹配技术栈与岗位要求出题' },
  { step: 3, title: '模拟面试', desc: '逐题限时作答，真实还原面试节奏与压力' },
  { step: 4, title: '查看报告', desc: '多维度评分 + 改进建议，精准定位提升方向' },
];

const stats = [
  { value: '10,000+', label: '注册用户' },
  { value: '50,000+', label: '完成面试' },
  { value: '92%', label: '用户好评率' },
];

const LandingPage = () => {
  const navigate = useNavigate();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);

  /** GSAP 动画 refs */
  const heroRef = useHeroEntrance();
  const featuresRef = useScrollReveal(0.12, 40, 'top 85%');
  const stepsRef = useScrollReveal(0.12, 40, 'top 85%');

  const handleStartPractice = () => {
    navigate(isLoggedIn ? '/dashboard' : '/login');
  };

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* ===== Hero ===== */}
      <section className="pt-32 pb-24 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-24 left-[8%] w-80 h-80 bg-[#D9A441]/[0.06] rounded-full blur-3xl animate-float-slow" />
          <div className="absolute bottom-8 right-[4%] w-96 h-96 bg-[#D9A441]/[0.04] rounded-full blur-3xl animate-float-slower" />
          {/* 细微网格纹理 */}
          <div
            className="absolute inset-0 opacity-[0.35]"
            style={{
              backgroundImage:
                'linear-gradient(var(--color-line) 1px, transparent 1px), linear-gradient(90deg, var(--color-line) 1px, transparent 1px)',
              backgroundSize: '56px 56px',
              maskImage: 'radial-gradient(ellipse 70% 60% at 50% 30%, black 20%, transparent 100%)',
              WebkitMaskImage: 'radial-gradient(ellipse 70% 60% at 50% 30%, black 20%, transparent 100%)',
            }}
          />
        </div>

        <div className="max-w-[1200px] mx-auto px-8 relative">
          <div ref={heroRef} className="max-w-[760px]">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--color-brand-light)] text-[var(--color-brand)] text-sm font-semibold mb-8">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-brand)] animate-pulse" />
              AI 驱动的全流程面试练习平台
            </div>
            <h1 className="text-[64px] font-extrabold leading-[1.04] tracking-[-1.5px] text-[var(--color-ink)] mb-8">
              每一次模拟，
              <br />
              都让你离
              <span className="text-[var(--color-brand)]"> Offer</span>
              <br />
              更近一步
            </h1>
            <p className="text-lg text-[var(--color-rock)] leading-relaxed mb-12 max-w-[520px]">
              上传真实简历，AI 为你生成个性化面试题。仿真对练、多维分析，把面试练成条件反射。
            </p>
            <div className="flex items-center gap-4">
              <button onClick={handleStartPractice} className="btn-flame btn-flame-lg text-base">
                免费开始练习
                <RightOutlined />
              </button>
              <button
                onClick={() => {
                  document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' });
                }}
                className="btn-ghost btn-ghost-lg text-base"
              >
                了解更多
              </button>
            </div>

            <div className="flex items-center gap-10 mt-12 pt-8 border-t border-[var(--color-line)]">
              {stats.map((s) => (
                <div key={s.label}>
                  <div className="text-2xl font-bold text-[var(--color-ink)]">{s.value}</div>
                  <div className="text-sm text-[var(--color-rock)] mt-1">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ===== 核心优势 ===== */}
      <section id="features" className="py-24 bg-[var(--color-surface)] border-t border-[var(--color-line)]">
        <div className="max-w-[1200px] mx-auto px-8">
          <div className="text-center mb-16">
            <div className="text-sm font-semibold text-[var(--color-brand)] uppercase tracking-[2px] mb-3">Core Advantages</div>
            <h2 className="text-[40px] font-extrabold text-[var(--color-ink)] tracking-[-0.5px] mb-4">
              为什么选择 AI 超级面试
            </h2>
            <p className="text-base text-[var(--color-rock)] max-w-[560px] mx-auto leading-relaxed">
              不只是刷题，而是让你真正理解面试的逻辑，建立面对任何问题的自信
            </p>
          </div>
          <div ref={featuresRef} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((f) => (
              <div
                key={f.title}
                className="card group !border-[var(--color-line)] hover:!border-[var(--color-brand)]/40 hover:!-translate-y-1.5 hover:!shadow-lg transition-all duration-300"
              >
                <div className="w-12 h-12 rounded-xl bg-[var(--color-brand-light)] flex items-center justify-center text-xl text-[var(--color-brand)] mb-5 group-hover:scale-110 group-hover:-rotate-3 transition-transform duration-300">
                  {f.icon}
                </div>
                <h3 className="text-base font-bold text-[var(--color-ink)] mb-2">{f.title}</h3>
                <p className="text-sm text-[var(--color-rock)] leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 四步流程 ===== */}
      <section id="how-it-works" className="py-24">
        <div className="max-w-[1200px] mx-auto px-8">
          <div className="text-center mb-16">
            <div className="text-sm font-semibold text-[var(--color-brand)] uppercase tracking-[2px] mb-3">How It Works</div>
            <h2 className="text-[40px] font-extrabold text-[var(--color-ink)] tracking-[-0.5px] mb-4">四步开始你的面试练习</h2>
            <p className="text-base text-[var(--color-rock)] max-w-[560px] mx-auto leading-relaxed">
              从上传简历到查看报告，全程不到 30 分钟
            </p>
          </div>
          <div ref={stepsRef} className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {steps.map((s, i) => (
              <div key={s.step} className="relative text-center">
                <div className="w-14 h-14 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-brand)]/40 text-[var(--color-brand)] flex items-center justify-center text-lg font-bold mx-auto mb-5 transition-transform duration-300 hover:scale-110">
                  {s.step}
                </div>
                <h3 className="text-base font-bold text-[var(--color-ink)] mb-2">{s.title}</h3>
                <p className="text-sm text-[var(--color-rock)] leading-relaxed">{s.desc}</p>
                {i < steps.length - 1 && (
                  <div className="hidden md:block absolute top-7 -right-3 text-[var(--color-slate)]">
                    <RightOutlined />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 页脚 ===== */}
      <footer className="border-t border-[var(--color-line)] py-12">
        <div className="max-w-[1200px] mx-auto px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2.5 font-bold text-[var(--color-ink)]">
              <span className="w-7 h-7 rounded-md bg-gradient-to-br from-[#D9A441] to-[#E6AF4E] flex items-center justify-center text-white text-xs">
                <ThunderboltFilled />
              </span>
              AI 超级面试
            </div>
            <div className="flex items-center gap-6 text-sm text-[var(--color-rock)]">
              <a href="#" className="hover:text-[var(--color-brand)] transition-colors">关于我们</a>
              <a href="#" className="hover:text-[var(--color-brand)] transition-colors">隐私政策</a>
              <a href="#" className="hover:text-[var(--color-brand)] transition-colors">服务条款</a>
              <a href="#" className="hover:text-[var(--color-brand)] transition-colors">联系我们</a>
            </div>
            <span className="text-sm text-[var(--color-slate)]">© 2024 AI 超级面试 All rights reserved.</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;