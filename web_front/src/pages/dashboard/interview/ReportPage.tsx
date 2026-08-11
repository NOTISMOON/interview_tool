import { useParams, useNavigate } from 'react-router-dom';
import { Progress, App, Rate } from 'antd';
import {
  ArrowLeftOutlined,
  ReloadOutlined,
  ShareAltOutlined,
  StarOutlined,
  BulbOutlined,
  WarningOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { useAppStore } from '@/store';
import { mockReport } from '@/lib/mocks/data';

const ReportPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const reports = useAppStore((s) => s.reports);

  const report = id ? reports[id] : null;
  const displayReport = report || mockReport;
  const score = displayReport.totalScore;
  const scoreEmoji = score >= 85 ? '🏆' : score >= 70 ? '👍' : score >= 60 ? '💪' : '📚';
  const scoreLevel = score >= 85 ? '表现优秀' : score >= 70 ? '表现良好' : score >= 60 ? '需要提升' : '继续努力';

  return (
    <div className="max-w-[900px]">
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={() => navigate('/dashboard/history')}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/dashboard/interview')} className="text-sm text-[#FF6B35] font-medium hover:text-[#E85D26] transition-colors inline-flex items-center gap-1">
            <ReloadOutlined /> 重新面试
          </button>
          <button
            onClick={() => { navigator.clipboard.writeText(window.location.href); message.success('链接已复制'); }}
            className="text-sm text-[#5F6B7A] font-medium hover:text-[#0D1117] transition-colors inline-flex items-center gap-1"
          >
            <ShareAltOutlined /> 分享
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-8 text-center">
          <Progress type="circle" percent={score} strokeColor="#FF6B35" size={140} format={(p) => (
            <div>
              <div className="text-3xl font-bold text-[#0D1117]">{p}</div>
              <div className="text-[10px] text-[#8B949E]">总分</div>
            </div>
          )} />
          <h2 className="text-xl font-bold text-[#0D1117] mt-4 mb-1">{scoreEmoji} {scoreLevel}</h2>
          <p className="text-sm text-[#5F6B7A]">{displayReport.summary}</p>
        </div>

        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6">
            <h3 className="text-sm font-bold text-[#0D1117] mb-3 flex items-center gap-2">
              <StarOutlined className="text-[#FF6B35]" /> 优势亮点
            </h3>
            <div className="space-y-2">
              {displayReport.strengths.map((s, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <CheckCircleOutlined className="text-[#2DA44E] mt-0.5 flex-shrink-0" />
                  <span className="text-[#0D1117]">{s}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6">
            <h3 className="text-sm font-bold text-[#0D1117] mb-3 flex items-center gap-2">
              <WarningOutlined className="text-[#BF8700]" /> 待改进
            </h3>
            <div className="space-y-2">
              {displayReport.weaknesses.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#BF8700] mt-1.5 flex-shrink-0" />
                  <span className="text-[#0D1117]">{w}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6">
            <h3 className="text-sm font-bold text-[#0D1117] mb-3 flex items-center gap-2">
              <BulbOutlined className="text-[#FF6B35]" /> 改进建议
            </h3>
            <div className="space-y-2">
              {displayReport.suggestions.map((s, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className="text-[#8B949E] text-xs font-mono min-w-[16px]">{i + 1}.</span>
                  <span className="text-[#0D1117]">{s}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 mb-6">
        <h3 className="text-sm font-bold text-[#0D1117] mb-4">逐题详情</h3>
        <div className="space-y-3">
          {displayReport.questionDetails?.slice(0, 5).map((qd, i) => (
            <div key={i} className="bg-[#F6F8FA] rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="tag tag-flame">第 {qd.questionNo} 题</span>
                <Rate disabled value={qd.aiScore} count={5} className="!text-xs" />
              </div>
              <p className="text-sm text-[#0D1117] mb-2">{qd.questionText}</p>
              <p className="text-xs text-[#5F6B7A] bg-white rounded-lg p-3">{qd.aiComment}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <button onClick={() => navigate('/dashboard/interview')} className="btn-flame flex-1">再来一次</button>
        <button onClick={() => navigate('/dashboard/history')} className="btn-ghost flex-1">查看记录</button>
      </div>
    </div>
  );
};

export default ReportPage;