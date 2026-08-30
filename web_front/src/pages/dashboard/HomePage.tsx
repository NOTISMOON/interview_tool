import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import App from 'antd/es/app';
import {
  PlayCircleOutlined,
  FileTextOutlined,
  HistoryOutlined,
  ThunderboltOutlined,
  RightOutlined,
  BarChartOutlined,
  RadarOutlined,
} from '@/components/icons';
import { useAppStore } from '@/store';
import { getResumes } from '@/lib/api/resume';
import { getInterviewList, getInterviewStats, INTERVIEW_TYPE_LABEL } from '@/lib/api/interview';
import { getCheckinStatus, doCheckin } from '@/lib/api/checkin';
import type { ApiInterviewListItem, ApiInterviewStats } from '@/lib/api/interview';
import { useStaggerEntrance } from '@/hooks/useGsapAnimations';

const DashboardHome = () => {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { user } = useAppStore();
  /** GSAP 动画 refs */
  const quickActionsRef = useStaggerEntrance(0.08, 30, 0.5, 0.2);
  const interviewListRef = useStaggerEntrance(0.06, 20, 0.4, 0.3);
  /** 简历数量（从后端 GET /resumes 拉取，仅取数量展示） */
  const [resumeCount, setResumeCount] = useState(0);
  /** 最近面试记录（GET /interviews，最近列表展示） */
  const [interviews, setInterviews] = useState<ApiInterviewListItem[]>([]);
  /** 面试统计（GET /interviews/stats，含软删除记录，删除不影响平均分） */
  const [stats, setStats] = useState<ApiInterviewStats>({ total: 0, completed_count: 0, avg_score: null });
  /** 签到数据 */
  const [checkinData, setCheckinData] = useState({ signedIn: false, streak: 0, totalDays: 0 });
  const [checkingIn, setCheckingIn] = useState(false);

  /** 处理签到 */
  const handleCheckin = async () => {
    if (checkinData.signedIn || checkingIn) return;
    setCheckingIn(true);
    try {
      const res = await doCheckin();
      setCheckinData(res);
      message.success('签到成功！');
    } catch {
      message.error('签到失败，请重试');
    } finally {
      setCheckingIn(false);
    }
  };

  // 进入页面时拉取数据
  useEffect(() => {
    getResumes(1, 1)
      .then((res) => setResumeCount(res.total))
      .catch(() => {});
    getInterviewList(1, 100)
      .then((res) => setInterviews(res.items))
      .catch(() => {});
    getInterviewStats()
      .then(setStats)
      .catch(() => {});
    getCheckinStatus()
      .then((res) => setCheckinData(res))
      .catch(() => {});
  }, []);

  /** 面试统计：完成数与平均分（含软删除记录，删除不影响统计） */
  const completedCount = stats.completed_count;
  const avgScore = stats.avg_score !== null ? Math.round(stats.avg_score) : null;

  /** 根据当前时间返回问候语 */
  const getGreeting = (): string => {
    const hour = new Date().getHours();
    if (hour < 6) return '夜深了';
    if (hour < 12) return '上午好';
    if (hour < 14) return '中午好';
    if (hour < 18) return '下午好';
    return '晚上好';
  };

  const quickActions = [
    {
      icon: <PlayCircleOutlined />,
      label: '开始面试',
      desc: '上传简历，AI 智能出题',
      onClick: () => navigate('/dashboard/interview'),
    },
    {
      icon: <FileTextOutlined />,
      label: '我的简历',
      desc: `${resumeCount} 份`,
      onClick: () => navigate('/dashboard/profile', { state: { openResumeModal: true } }),
    },
    {
      icon: <HistoryOutlined />,
      label: '面试记录',
      desc: `${interviews.length} 次`,
      onClick: () => navigate('/dashboard/history'),
    },
    {
      icon: <RadarOutlined />,
      label: '能力画像',
      desc: '查看多维报告',
      onClick: () => navigate('/dashboard/interview'),
    },
  ];

  return (
    <div className="flex flex-col h-full gap-[22px]">
      {/* ===== 页面标题 ===== */}
      <div>
        <h1 className="text-[22px] font-extrabold text-[var(--color-ink)] tracking-[0.2px]">
          {user?.nickname ? `${user?.nickname}，${getGreeting()}` : getGreeting()}
        </h1>
        <p className="text-[13px] text-[var(--color-rock)] mt-1">准备开始今天的面试练习了吗？</p>
      </div>

      {/* ===== 顶部两卡：Banner + 本周统计 ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-[14px]">
        <div className="bg-[var(--color-surface)] border border-[var(--color-line)] rounded-[16px] p-[26px_28px] min-h-[158px] flex flex-col justify-center">
          <h2 className="text-lg font-bold text-[var(--color-ink)] mb-1.5">AI 模拟面试</h2>
          <p className="text-[13px] text-[var(--color-rock)] max-w-[360px] mb-[18px] leading-[1.6]">
            上传简历，即刻开始 AI 驱动的智能模拟面试，精准定位你的能力短板
          </p>
          <div>
            <button
              onClick={() => navigate('/dashboard/interview')}
              className="inline-flex items-center gap-2 px-5 py-[11px] rounded-[9px] bg-[#D9A441] text-[#0B0B0C] text-[13.5px] font-bold hover:bg-[#E6AF4E] transition-colors"
            >
              <PlayCircleOutlined /> 立即开始
            </button>
          </div>
        </div>

        <div className="bg-[var(--color-surface)] border border-[var(--color-line)] rounded-[16px] p-[20px_22px]">
          <div className="text-[12.5px] font-semibold text-[var(--color-rock)] mb-[14px] tracking-[0.3px]">本周统计</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[21px] font-extrabold text-[var(--color-brand)] leading-none mb-1">{completedCount}</div>
              <div className="text-[11px] text-[var(--color-slate)]">完成面试</div>
            </div>
            <div>
              <div className="text-[21px] font-extrabold text-[var(--color-ink)] leading-none mb-1">{avgScore ?? '--'}</div>
              <div className="text-[11px] text-[var(--color-slate)]">平均得分</div>
            </div>
            <div>
              <div className="text-[21px] font-extrabold text-[var(--color-success)] leading-none mb-1">{resumeCount}</div>
              <div className="text-[11px] text-[var(--color-slate)]">简历数量</div>
            </div>
            <button
              onClick={handleCheckin}
              disabled={checkinData.signedIn || checkingIn}
              className={`w-full p-2.5 rounded-[9px] font-bold text-center transition-colors ${
                checkinData.signedIn
                  ? 'bg-[var(--color-surface-2)] text-[var(--color-rock)] border border-[var(--color-line)] cursor-default'
                  : 'bg-[#D9A441] text-[#0B0B0C] hover:bg-[#E6AF4E] cursor-pointer'
              }`}
            >
              <div className="text-[17px] font-extrabold">{checkinData.streak}</div>
              <div className="text-[10.5px] opacity-80 mt-0.5">
                {checkingIn ? '签到中...' : checkinData.signedIn ? '已连续签到' : '签到'}
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* ===== 快捷操作 ===== */}
      <div className="flex items-center gap-2 text-[14.5px] font-bold text-[var(--color-ink)]">
        <ThunderboltOutlined className="w-[17px] h-[17px] text-[#D9A441]" />
        快捷操作
      </div>
      <div ref={quickActionsRef} className="grid grid-cols-2 md:grid-cols-4 gap-3 -mt-[14px]">
        {quickActions.map((action) => (
          <button
            key={action.label}
            onClick={action.onClick}
            className="bg-[var(--color-surface)] border border-[var(--color-line)] rounded-[12px] p-4 text-left hover:border-[#D9A441]/40 hover:-translate-y-0.5 hover:bg-[var(--color-surface-hover)] transition-all duration-200 group"
          >
            <div className="w-[38px] h-[38px] rounded-[12px] bg-[rgba(217,164,65,0.12)] flex items-center justify-center text-[#D9A441] mb-3 group-hover:scale-110 transition-transform">
              {action.icon}
            </div>
            <h3 className="text-[13.5px] font-semibold text-[var(--color-ink)] mb-0.5">{action.label}</h3>
            <p className="text-[11.5px] text-[var(--color-slate)]">{action.desc}</p>
          </button>
        ))}
      </div>

      {/* ===== 最近面试 ===== */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[14.5px] font-bold text-[var(--color-ink)]">
          <BarChartOutlined className="w-[17px] h-[17px] text-[#D9A441]" />
          最近面试
        </div>
        {interviews.length > 0 && (
          <button
            onClick={() => navigate('/dashboard/history')}
            className="text-sm text-[var(--color-brand)] font-medium hover:text-[var(--color-brand-hover)] transition-colors flex items-center gap-1"
          >
            查看全部 <RightOutlined className="text-xs" />
          </button>
        )}
      </div>

      {interviews.length === 0 ? (
        <div className="bg-[var(--color-surface)] border border-[var(--color-line)] rounded-[16px] p-12 text-center -mt-[14px]">
          <FileTextOutlined className="text-4xl text-[var(--color-line)] mb-4" />
          <h3 className="text-base font-semibold text-[var(--color-ink)] mb-2">暂无面试记录</h3>
          <p className="text-sm text-[var(--color-rock)] mb-6">完成一次模拟面试后，记录将显示在这里</p>
          <button onClick={() => navigate('/dashboard/interview')} className="btn-flame">
            开始首次面试
          </button>
        </div>
      ) : (
        <div ref={interviewListRef} className="flex-1 overflow-y-auto min-h-0 -mt-[14px]">
          <div className="bg-[var(--color-surface)] border border-[var(--color-line)] rounded-[12px] p-1.5">
            {interviews.slice(0, 5).map((item) => {
              const score = item.total_score !== null ? Math.round(item.total_score) : null;
              const scoreColor = score === null ? 'var(--color-slate)' : score >= 85 ? 'var(--color-success)' : score >= 70 ? 'var(--color-brand)' : score >= 60 ? 'var(--color-warning)' : 'var(--color-error)';
              const time = item.interview_time || item.created_at;
              return (
                <div
                  key={item.interview_id}
                  className="flex items-center gap-[14px] p-3 rounded-[9px] hover:bg-[var(--color-surface-2)] transition-colors cursor-pointer"
                  onClick={() =>
                    navigate(
                      item.status === 0
                        ? `/dashboard/interview/session/${item.interview_id}`
                        : `/dashboard/report/${item.interview_id}`,
                    )
                  }
                >
                  <div
                    className="w-[46px] h-[46px] rounded-[13px] flex items-center justify-center text-[15px] font-extrabold flex-shrink-0"
                    style={{ backgroundColor: `color-mix(in srgb, ${scoreColor} 12%, transparent)`, color: scoreColor }}
                  >
                    {score ?? (item.status === 0 ? '…' : '—')}
                  </div>
                  <div className="flex-1 ml-[14px] min-w-0">
                    <div className="flex items-center gap-2">
                      <h4 className="text-[13.5px] font-semibold text-[var(--color-ink)] truncate">
                        {INTERVIEW_TYPE_LABEL[item.type] ?? '模拟面试'}
                      </h4>
                      <span className="text-[10.5px] px-2 py-0.5 rounded-full bg-[rgba(217,164,65,0.12)] text-[#D9A441]">
                        {INTERVIEW_TYPE_LABEL[item.type] ?? '面试'}
                      </span>
                      {item.status === 0 && (
                        <span className="text-[10.5px] px-2 py-0.5 rounded-full bg-[var(--color-surface-2)] text-[var(--color-rock)] border border-[var(--color-line)]">
                          进行中
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-[14px] mt-1.5">
                      <span className="text-[11.5px] text-[var(--color-slate)]">
                        {time
                          ? new Date(time).toLocaleString('zh-CN', {
                              month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                            })
                          : ''}
                      </span>
                      <span className="text-[11.5px] text-[var(--color-slate)]">{item.question_count} 题</span>
                    </div>
                  </div>
                  <RightOutlined className="text-[var(--color-slate)] !w-[14px] !h-[14px]" />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardHome;