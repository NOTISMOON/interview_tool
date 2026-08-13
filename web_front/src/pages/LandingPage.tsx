import { useNavigate } from 'react-router-dom';
import {
  PlayCircleOutlined,
  FileTextOutlined,
  BarChartOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  RightOutlined,
  CheckCircleOutlined,
  StarFilled,
} from '@ant-design/icons';

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

const testimonials = [
  {
    name: '陈同学',
    role: '应届生 · 拿到字节 Offer',
    content: '面试前用这个工具练了两周，面试时发现很多题目都练过类似的，心态稳了很多。',
    rating: 5,
  },
  {
    name: '李工',
    role: '3 年经验 · 前端工程师',
    content: 'AI 出的题比我自己准备的全面多了，暴露了很多知识盲区，针对性补强后顺利通过。',
    rating: 5,
  },
  {
    name: '王女士',
    role: '5 年经验 · 产品经理',
    content: '报告里的改进建议特别实用，照着练了几次，表达逻辑明显提升。',
    rating: 4,
  },
];

const LandingPage = () => {
  const navigate = useNavigate();

  return (
    <div className="bg-[#F6F8FA]">
      <section className="pt-32 pb-20 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-20 left-[10%] w-72 h-72 bg-[#FF6B35]/5 rounded-full blur-3xl" />
          <div className="absolute bottom-10 right-[5%] w-96 h-96 bg-[#FF6B35]/4 rounded-full blur-3xl" />
        </div>

        <div className="max-w-[1200px] mx-auto px-8 relative">
          <div className="max-w-[720px]">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#FFF3ED] text-[#FF6B35] text-sm font-semibold mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-[#FF6B35] animate-pulse" />
              AI 驱动的面试练习平台
            </div>
            <h1 className="text-[56px] font-extrabold leading-[1.1] tracking-[-1px] text-[#0D1117] mb-6">
              模拟面试，
              <br />
              <span className="gradient-text">自信上场</span>
            </h1>
            <p className="text-lg text-[#5F6B7A] leading-relaxed mb-10 max-w-[520px]">
              基于真实简历，AI 为你生成个性化面试题。多轮练习、深度分析，让每一次面试都成为你拿 offer 的底气。
            </p>
            <div className="flex items-center gap-4">
              <button onClick={() => navigate('/login')} className="btn-flame btn-flame-lg text-base">
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

            <div className="flex items-center gap-8 mt-10 pt-8 border-t border-[#E1E4E8]">
              <div>
                <div className="text-2xl font-bold text-[#0D1117]">10,000+</div>
                <div className="text-sm text-[#5F6B7A]">注册用户</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#0D1117]">50,000+</div>
                <div className="text-sm text-[#5F6B7A]">完成面试</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#0D1117]">92%</div>
                <div className="text-sm text-[#5F6B7A]">用户好评率</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="py-20 bg-white border-t border-[#E1E4E8]">
        <div className="max-w-[1200px] mx-auto px-8">
          <div className="text-center mb-14">
            <h2 className="section-title mb-4">为什么选择面试教练</h2>
            <p className="section-subtitle mx-auto">
              不只是刷题，而是让你真正理解面试的逻辑，建立自信
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((f) => (
              <div key={f.title} className="card !border-[#F0F2F5] hover:!border-[#FF6B35]/30">
                <div className="w-12 h-12 rounded-xl bg-[#FFF3ED] flex items-center justify-center text-xl text-[#FF6B35] mb-4">
                  {f.icon}
                </div>
                <h3 className="text-base font-bold text-[#0D1117] mb-2">{f.title}</h3>
                <p className="text-sm text-[#5F6B7A] leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how-it-works" className="py-20">
        <div className="max-w-[1200px] mx-auto px-8">
          <div className="text-center mb-14">
            <h2 className="section-title mb-4">四步开始你的面试练习</h2>
            <p className="section-subtitle mx-auto">
              从上传简历到查看报告，全程不到 30 分钟
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {steps.map((s, i) => (
              <div key={s.step} className="relative text-center">
                <div className="w-14 h-14 rounded-2xl bg-[#0D1117] text-white flex items-center justify-center text-lg font-bold mx-auto mb-4">
                  {s.step}
                </div>
                <h3 className="text-base font-bold text-[#0D1117] mb-2">{s.title}</h3>
                <p className="text-sm text-[#5F6B7A] leading-relaxed">{s.desc}</p>
                {i < steps.length - 1 && (
                  <div className="hidden md:block absolute top-7 -right-3 text-[#E1E4E8]">
                    <RightOutlined />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="testimonials" className="py-20 bg-white border-t border-[#E1E4E8]">
        <div className="max-w-[1200px] mx-auto px-8">
          <div className="text-center mb-14">
            <h2 className="section-title mb-4">用户怎么说</h2>
            <p className="section-subtitle mx-auto">
              来自真实用户的反馈
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {testimonials.map((t) => (
              <div key={t.name} className="card !border-[#F0F2F5]">
                <div className="flex items-center gap-1 mb-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <StarFilled
                      key={i}
                      className={i < t.rating ? 'text-[#FF6B35]' : 'text-[#E1E4E8]'}
                      style={{ fontSize: 14 }}
                    />
                  ))}
                </div>
                <p className="text-sm text-[#0D1117] leading-relaxed mb-4">{t.content}</p>
                <div className="flex items-center gap-3 pt-3 border-t border-[#F0F2F5]">
                  <div className="w-9 h-9 rounded-full bg-[#FFF3ED] flex items-center justify-center text-[#FF6B35] font-bold text-sm">
                    {t.name[0]}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-[#0D1117]">{t.name}</div>
                    <div className="text-xs text-[#8B949E]">{t.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
      <footer className="border-t border-[#E1E4E8] py-12">
        <div className="max-w-[1200px] mx-auto px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2.5 font-bold text-[#0D1117]">
              <span className="w-7 h-7 rounded-md bg-[#FF6B35] flex items-center justify-center text-white text-xs">
                AI
              </span>
              面试教练
            </div>
            <div className="flex items-center gap-6 text-sm text-[#5F6B7A]">
              <a href="#" className="hover:text-[#0D1117] transition-colors">关于我们</a>
              <a href="#" className="hover:text-[#0D1117] transition-colors">隐私政策</a>
              <a href="#" className="hover:text-[#0D1117] transition-colors">服务条款</a>
              <a href="#" className="hover:text-[#0D1117] transition-colors">联系我们</a>
            </div>
            <span className="text-sm text-[#8B949E]">© 2024 面试教练 All rights reserved.</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;