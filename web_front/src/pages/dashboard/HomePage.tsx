import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PlayCircleOutlined,
  FileTextOutlined,
  HistoryOutlined,
  RiseOutlined,
  ThunderboltOutlined,
  RightOutlined,
  BarChartOutlined,
  TrophyOutlined,
} from '@ant-design/icons';
import { useAppStore } from '@/store';
import { getResumes } from '@/lib/api/resume';
import { getInterviewList, INTERVIEW_TYPE_LABEL } from '@/lib/api/interview';
import type { ApiInterviewListItem } from '@/lib/api/interview';
import { useStaggerEntrance } from '@/hooks/useGsapAnimations';

const DashboardHome = () => {
  const navigate = useNavigate();
  const { user } = useAppStore();
  /** GSAP 动画 refs */
  const quickActionsRef = useStaggerEntrance(0.08, 30, 0.5, 0.2);
  const interviewListRef = useStaggerEntrance(0.06, 20, 0.4, 0.3);
  /** 简历数量（从后端 GET /resumes 拉取，仅取数量展示） */
  const [resumeCount, setResumeCount] = useState(0);
  /** 最近面试记录（GET /interviews，工作台统计与最近列表） */
  const [interviews, setInterviews] = useState<ApiInterviewListItem[]>([]);

  // 进入页面时拉取一次简历数量与最近面试
  useEffect(() => {
    getResumes(1, 1)
      .then((res) => setResumeCount(res.total))
      .catch(() => {
        /* 加载失败静默，保持默认0 */
      });
    getInterviewList(1, 100)
      .then((res) => setInterviews(res.items))
      .catch(() => {
        /* 加载失败静默，保留空列表 */
      });
  }, []);

  /** 已完成且有成绩的面试（统计与最近列表） */
  const finished = interviews.filter((it) => it.status === 1 && it.total_score !== null);
  const avgScore = finished.length > 0
    ? Math.round(finished.reduce((s, r) => s + (r.total_score ?? 0), 0) / finished.length)
    : null;

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
      onClick: () => navigate('/dashboard/interview'),
    },
    {
      icon: <HistoryOutlined />,
      label: '面试记录',
      desc: `${interviews.length} 次`,
      onClick: () => navigate('/dashboard/history'),
    },
    {
      icon: <RiseOutlined />,
      label: '能力成长',
      desc: '追踪进步',
      onClick: () => navigate('/dashboard/history'),
    },
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="mb-6">
          <h1 className="text-2xl font-extrabold text-[#232529] mb-1">
            {user?.nickname ? `${user?.nickname}，${getGreeting()}` : getGreeting()}
          </h1>
          <p className="text-sm text-[#666666]">准备开始今天的面试练习了吗？</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <div className="lg:col-span-2 bg-white border border-[#E8E8E8] rounded-2xl p-8 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-1 h-full bg-[#00BFA5]" />
            <div className="relative">
              <h2 className="text-xl font-bold text-[#232529] mb-2">AI 模拟面试</h2>
              <p className="text-sm text-[#666666] mb-6 max-w-sm">
                上传简历，即刻开始 AI 驱动的智能模拟面试，精准定位你的能力短板
              </p>
              <button
                onClick={() => navigate('/dashboard/interview')}
                className="btn-flame"
              >
                <PlayCircleOutlined /> 立即开始
              </button>
            </div>
          </div>

          <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-[#232529] mb-4">本周统计</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-2xl font-bold text-[#00BFA5]">{finished.length}</div>
                <div className="text-xs text-[#666666]">完成面试</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#232529]">{avgScore ?? '--'}</div>
                <div className="text-xs text-[#666666]">平均得分</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#00B578]">{resumeCount}</div>
                <div className="text-xs text-[#666666]">简历数量</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#232529]">1</div>
                <div className="text-xs text-[#666666]">练习天数</div>
              </div>
            </div>
          </div>
        </div>

        <h2 className="text-base font-bold text-[#232529] mb-4 flex items-center gap-2">
          <ThunderboltOutlined className="text-[#00BFA5]" />
          快捷操作
        </h2>
        <div ref={quickActionsRef} className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {quickActions.map((action) => (
            <button
              key={action.label}
              onClick={action.onClick}
              className="bg-white border border-[#E8E8E8] rounded-xl p-5 text-left hover:border-[#00BFA5]/30 hover:shadow-md transition-all duration-150 group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#E0F7F4] flex items-center justify-center text-lg text-[#00BFA5] mb-3 group-hover:scale-110 transition-transform">
                {action.icon}
              </div>
              <h3 className="text-sm font-semibold text-[#232529] mb-1">{action.label}</h3>
              <p className="text-xs text-[#999999]">{action.desc}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-shrink-0 flex items-center justify-between mb-4">
        <h2 className="text-base font-bold text-[#232529] flex items-center gap-2">
          <BarChartOutlined className="text-[#00BFA5]" />
          最近面试
        </h2>
        {interviews.length > 0 && (
          <button
            onClick={() => navigate('/dashboard/history')}
            className="text-sm text-[#00BFA5] font-medium hover:text-[#00A88A] transition-colors flex items-center gap-1"
          >
            查看全部 <RightOutlined className="text-xs" />
          </button>
        )}
      </div>

      {interviews.length === 0 ? (
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-12 text-center">
          <FileTextOutlined className="text-4xl text-[#E8E8E8] mb-4" />
          <h3 className="text-base font-semibold text-[#232529] mb-2">暂无面试记录</h3>
          <p className="text-sm text-[#666666] mb-6">完成一次模拟面试后，记录将显示在这里</p>
          <button onClick={() => navigate('/dashboard/interview')} className="btn-flame">
            开始首次面试
          </button>
        </div>
      ) : (
        <div ref={interviewListRef} className="flex-1 overflow-y-auto min-h-0 space-y-3">
          {interviews.slice(0, 5)
            .map((item) => {
              const score = item.total_score !== null ? Math.round(item.total_score) : null;
              const scoreColor = score === null ? '#999999' : score >= 85 ? '#00B578' : score >= 70 ? '#00BFA5' : score >= 60 ? '#FFAA00' : '#F53535';
              const time = item.interview_time || item.created_at;
              return (
                <div
                  key={item.interview_id}
                  className="bg-white border border-[#E8E8E8] rounded-xl p-4 flex items-center hover:border-[#00BFA5]/30 hover:shadow-sm transition-all cursor-pointer"
                  onClick={() =>
                    navigate(
                      item.status === 0
                        ? `/dashboard/interview/session/${item.interview_id}`
                        : `/dashboard/report/${item.interview_id}`,
                    )
                  }
                >
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold flex-shrink-0"
                    style={{ backgroundColor: `${scoreColor}15`, color: scoreColor }}
                  >
                    {score ?? (item.status === 0 ? '…' : '—')}
                  </div>
                  <div className="flex-1 ml-4 min-w-0">
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-semibold text-[#232529] truncate">
                        {INTERVIEW_TYPE_LABEL[item.type] ?? '模拟面试'}
                      </h4>
                      <span className="tag tag-flame">{INTERVIEW_TYPE_LABEL[item.type] ?? '面试'}</span>
                      {item.status === 0 && (
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-[#FFF7E0] text-[#FFAA00]">
                          进行中
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-1">
                      <span className="text-xs text-[#999999]">
                        {time
                          ? new Date(time).toLocaleString('zh-CN', {
                              month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                            })
                          : ''}
                      </span>
                      <span className="text-xs text-[#999999]">{item.question_count} 题</span>
                    </div>
                  </div>
                  <RightOutlined className="text-[#E8E8E8] text-xs ml-4" />
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
};

export default DashboardHome;