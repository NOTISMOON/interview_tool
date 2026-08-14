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

const DashboardHome = () => {
  const navigate = useNavigate();
  const { user, resumes, reports } = useAppStore();

  const reportList = Object.values(reports);

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
      desc: `${resumes.length} 份`,
      onClick: () => navigate('/dashboard/interview'),
    },
    {
      icon: <HistoryOutlined />,
      label: '面试记录',
      desc: `${reportList.length} 次`,
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
          <h1 className="text-2xl font-extrabold text-[#0D1117] mb-1">
            {user?.nickname ? `${user?.nickname}，${getGreeting()}` : getGreeting()}
          </h1>
          <p className="text-sm text-[#5F6B7A]">准备开始今天的面试练习了吗？</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <div className="lg:col-span-2 bg-gradient-to-br from-[#0D1117] to-[#1A2332] rounded-2xl p-8 text-white relative overflow-hidden">
            <div className="absolute top-0 right-0 w-48 h-48 bg-[#FF6B35]/10 rounded-full blur-3xl" />
            <div className="relative">
              <h2 className="text-xl font-bold mb-2">AI 模拟面试</h2>
              <p className="text-sm text-white/60 mb-6 max-w-sm">
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

          <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-[#0D1117] mb-4">本周统计</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-2xl font-bold text-[#FF6B35]">{reportList.length}</div>
                <div className="text-xs text-[#5F6B7A]">完成面试</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#0D1117]">
                  {reportList.length > 0
                    ? Math.round(reportList.reduce((s, r) => s + r.totalScore, 0) / reportList.length)
                    : '--'}
                </div>
                <div className="text-xs text-[#5F6B7A]">平均得分</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#2DA44E]">{resumes.length}</div>
                <div className="text-xs text-[#5F6B7A]">简历数量</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#0D1117]">1</div>
                <div className="text-xs text-[#5F6B7A]">练习天数</div>
              </div>
            </div>
          </div>
        </div>

        <h2 className="text-base font-bold text-[#0D1117] mb-4 flex items-center gap-2">
          <ThunderboltOutlined className="text-[#FF6B35]" />
          快捷操作
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {quickActions.map((action) => (
            <button
              key={action.label}
              onClick={action.onClick}
              className="bg-white border border-[#E1E4E8] rounded-xl p-5 text-left hover:border-[#FF6B35]/30 hover:shadow-md transition-all duration-150 group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#FFF3ED] flex items-center justify-center text-lg text-[#FF6B35] mb-3 group-hover:scale-110 transition-transform">
                {action.icon}
              </div>
              <h3 className="text-sm font-semibold text-[#0D1117] mb-1">{action.label}</h3>
              <p className="text-xs text-[#8B949E]">{action.desc}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-shrink-0 flex items-center justify-between mb-4">
        <h2 className="text-base font-bold text-[#0D1117] flex items-center gap-2">
          <BarChartOutlined className="text-[#FF6B35]" />
          最近面试
        </h2>
        {reportList.length > 0 && (
          <button
            onClick={() => navigate('/dashboard/history')}
            className="text-sm text-[#FF6B35] font-medium hover:text-[#E85D26] transition-colors flex items-center gap-1"
          >
            查看全部 <RightOutlined className="text-xs" />
          </button>
        )}
      </div>

      {reportList.length === 0 ? (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-12 text-center">
          <FileTextOutlined className="text-4xl text-[#E1E4E8] mb-4" />
          <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无面试记录</h3>
          <p className="text-sm text-[#5F6B7A] mb-6">完成一次模拟面试后，记录将显示在这里</p>
          <button onClick={() => navigate('/dashboard/interview')} className="btn-flame">
            开始首次面试
          </button>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto min-h-0 space-y-3">
          {reportList
            .sort((a, b) => new Date(b.interviewTime).getTime() - new Date(a.interviewTime).getTime())
            .slice(0, 5)
            .map((report) => {
              const score = report.totalScore;
              const scoreColor = score >= 85 ? '#2DA44E' : score >= 70 ? '#FF6B35' : score >= 60 ? '#BF8700' : '#CF222E';
              return (
                <div
                  key={report.id}
                  className="bg-white border border-[#E1E4E8] rounded-xl p-4 flex items-center hover:border-[#FF6B35]/30 hover:shadow-sm transition-all cursor-pointer"
                  onClick={() => navigate(`/dashboard/report/${report.id}`)}
                >
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold flex-shrink-0"
                    style={{ backgroundColor: `${scoreColor}15`, color: scoreColor }}
                  >
                    {score}
                  </div>
                  <div className="flex-1 ml-4 min-w-0">
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-semibold text-[#0D1117] truncate">
                        {report.resumeName || '面试记录'}
                      </h4>
                      <span className="tag tag-flame">{report.type === 'full' ? '完整面试' : '快速面试'}</span>
                    </div>
                    <div className="flex items-center gap-4 mt-1">
                      <span className="text-xs text-[#8B949E]">{report.interviewTime}</span>
                      <span className="text-xs text-[#8B949E]">{report.questionCount} 题</span>
                    </div>
                  </div>
                  <RightOutlined className="text-[#E1E4E8] text-xs ml-4" />
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
};

export default DashboardHome;