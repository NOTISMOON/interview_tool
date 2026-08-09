import { useNavigate } from 'react-router-dom';
import { App } from 'antd';
import {
  CalendarOutlined,
  RightOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { useAppStore } from '@/store';

const HistoryPage = () => {
  const navigate = useNavigate();
  const { reports } = useAppStore();
  const reportList = Object.values(reports);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-[#0D1117]">面试记录</h1>
        <button onClick={() => navigate('/dashboard/interview')} className="btn-flame">
          <PlayCircleOutlined /> 开始面试
        </button>
      </div>

      {reportList.length === 0 ? (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 text-center">
          <FileTextOutlined className="text-5xl text-[#E1E4E8] mb-4" />
          <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无面试记录</h3>
          <p className="text-sm text-[#5F6B7A] mb-6">完成一次 AI 模拟面试后，记录将显示在这里</p>
          <button onClick={() => navigate('/dashboard/interview')} className="btn-flame">开始首次面试</button>
        </div>
      ) : (
        <div className="space-y-3">
          {reportList
            .sort((a, b) => new Date(b.interviewTime).getTime() - new Date(a.interviewTime).getTime())
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
                      <h4 className="text-sm font-semibold text-[#0D1117] truncate">{report.resumeName || '面试记录'}</h4>
                      <span className="tag tag-flame">{report.type === 'full' ? '完整面试' : '快速面试'}</span>
                    </div>
                    <div className="flex items-center gap-4 mt-1">
                      <span className="text-xs text-[#8B949E] inline-flex items-center gap-1">
                        <CalendarOutlined /> {report.interviewTime}
                      </span>
                      <span className="text-xs text-[#8B949E] inline-flex items-center gap-1">
                        <CheckCircleOutlined /> {report.questionCount} 题
                      </span>
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

export default HistoryPage;