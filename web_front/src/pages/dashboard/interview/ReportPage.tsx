/**
 * 面试报告页（真实后端对接：GET /report + GET /questions + regenerate）。
 *
 * 报告未生成时轮询（generating）；失败可手动重试（§13.1）；
 * 报告内容含维度得分、能力画像与逐题详情（仅已结束面试返回全量）。
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Progress, App, Rate, Tag, Empty } from 'antd';
import {
  ArrowLeftOutlined,
  ReloadOutlined,
  ShareAltOutlined,
  StarOutlined,
  BulbOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  UserOutlined,
} from '@ant-design/icons';
import {
  getInterviewReport,
  getInterviewQuestions,
  regenerateReport,
  CATEGORY_LABEL,
} from '@/lib/api/interview';
import type {
  ApiInterviewReport,
  ApiInterviewQuestionDetail,
} from '@/lib/api/interview';

/** 报告轮询间隔 */
const POLL_INTERVAL = 3000;

const ReportPage = () => {
  const { id } = useParams<{ id: string }>();
  const interviewId = Number(id);
  const navigate = useNavigate();
  const { message } = App.useApp();

  const [loading, setLoading] = useState(true);
  const [reportStatus, setReportStatus] = useState<string>('generating');
  const [report, setReport] = useState<ApiInterviewReport | null>(null);
  const [questions, setQuestions] = useState<ApiInterviewQuestionDetail[]>([]);
  const [regenerating, setRegenerating] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** 拉取报告状态；未就绪时启动轮询（§13.1 惰性触发） */
  const loadReport = useCallback(async () => {
    try {
      const res = await getInterviewReport(interviewId);
      setReportStatus(res.status);
      setReport(res.report);
      return res.status;
    } catch {
      setReportStatus('error');
      return 'error';
    }
  }, [interviewId]);

  /** 拉取逐题详情（仅已结束面试返回） */
  const loadQuestions = useCallback(async () => {
    try {
      const res = await getInterviewQuestions(interviewId);
      setQuestions(res.items);
    } catch {
      // 面试进行中或无权限时不展示逐题区
      setQuestions([]);
    }
  }, [interviewId]);

  // 初始加载 + generating 状态轮询
  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      const status = await loadReport();
      if (!mounted) return;
      setLoading(false);
      if (status === 'ready' || status === 'invalid') {
        await loadQuestions();
      } else if (status === 'generating') {
        pollTimerRef.current = setInterval(async () => {
          const s = await loadReport();
          if (s === 'ready' || s === 'failed' || s === 'invalid' || s === 'error') {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            if (s === 'ready') await loadQuestions();
          }
        }, POLL_INTERVAL);
      }
    })();
    return () => {
      mounted = false;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  /** 手动重试报告生成（§13.1 regenerate） */
  const handleRegenerate = useCallback(async () => {
    setRegenerating(true);
    try {
      await regenerateReport(interviewId);
      message.success('已重新触发报告生成');
      setReportStatus('generating');
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      pollTimerRef.current = setInterval(async () => {
        const s = await loadReport();
        if (s === 'ready' || s === 'failed' || s === 'invalid' || s === 'error') {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          if (s === 'ready') await loadQuestions();
          setRegenerating(false);
        }
      }, POLL_INTERVAL);
    } catch {
      message.error('触发重试失败，请稍后再试');
      setRegenerating(false);
    }
  }, [interviewId, loadQuestions, loadReport, message]);

  // ===== 加载中 =====
  if (loading) {
    return (
      <div className="max-w-[900px] flex justify-center py-24">
        <LoadingOutlined className="text-3xl text-[#E5E6EB]" />
      </div>
    );
  }

  // ===== 无效（进行中/已中断） =====
  if (reportStatus === 'invalid') {
    return (
      <div className="max-w-[900px]">
        <div className="flex items-center justify-between mb-6">
          <button
            onClick={() => navigate('/dashboard/history')}
            className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
        </div>
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-16">
          <Empty description="该面试暂无报告（进行中或已中断）" />
        </div>
      </div>
    );
  }

  // ===== 生成中 / 失败 =====
  if (reportStatus !== 'ready' || !report) {
    return (
      <div className="max-w-[900px]">
        <div className="flex items-center justify-between mb-6">
          <button
            onClick={() => navigate('/dashboard/history')}
            className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
        </div>
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-16 text-center">
          {reportStatus === 'failed' ? (
            <>
              <WarningOutlined className="text-4xl text-[#FFAA00] mb-4" />
              <h3 className="text-base font-semibold text-[#232529] mb-2">报告生成失败</h3>
              <p className="text-sm text-[#666666] mb-6">AI 分析多次超时，题目与评分已保留，可手动重试生成</p>
              <button onClick={handleRegenerate} disabled={regenerating} className="btn-flame">
                {regenerating ? <LoadingOutlined /> : <ReloadOutlined />} 重新生成报告
              </button>
            </>
          ) : (
            <>
              <div className="w-12 h-12 mx-auto mb-4 rounded-full border-4 border-[#F2F3F5] border-t-[#00BFA5] animate-spin" />
              <h3 className="text-base font-semibold text-[#232529] mb-2">报告生成中…</h3>
              <p className="text-sm text-[#666666]">AI 正在汇总你的整场表现，通常需要 10~30 秒</p>
            </>
          )}
        </div>
      </div>
    );
  }

  // ===== 报告就绪 =====
  const score = Math.round(report.total_score);
  const scoreEmoji = score >= 85 ? '🏆' : score >= 70 ? '👍' : score >= 60 ? '💪' : '📚';
  const scoreLevel = score >= 85 ? '表现优秀' : score >= 70 ? '表现良好' : score >= 60 ? '需要提升' : '继续努力';
  const dimensionEntries = Object.entries(report.dimension_scores ?? {});

  return (
    <div className="max-w-[900px]">
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={() => navigate('/dashboard/history')}
          className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/dashboard/interview')} className="text-sm text-[#00BFA5] font-medium hover:text-[#00A88A] transition-colors inline-flex items-center gap-1">
            <ReloadOutlined /> 重新面试
          </button>
          <button
            onClick={() => { navigator.clipboard.writeText(window.location.href); message.success('链接已复制'); }}
            className="text-sm text-[#666666] font-medium hover:text-[#232529] transition-colors inline-flex items-center gap-1"
          >
            <ShareAltOutlined /> 分享
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-8 text-center">
          <Progress type="circle" percent={score} strokeColor="#00BFA5" size={140} format={(p) => (
            <div>
              <div className="text-3xl font-bold text-[#232529]">{p}</div>
              <div className="text-[10px] text-[#999999]">总分</div>
            </div>
          )} />
          <h2 className="text-xl font-bold text-[#232529] mt-4 mb-1">{scoreEmoji} {scoreLevel}</h2>
          <p className="text-sm text-[#666666]">{report.summary}</p>
          {/* 能力画像（§14.3 capability_profile） */}
          {report.capability_profile && Object.keys(report.capability_profile).length > 0 && (
            <div className="mt-4 pt-4 border-t border-[#F2F3F5]">
              <p className="text-xs font-semibold text-[#999999] mb-2 flex items-center justify-center gap-1">
                <UserOutlined /> 能力画像
              </p>
              <div className="flex flex-wrap gap-1.5 justify-center">
                {Object.entries(report.capability_profile).map(([k, v]) => (
                  <Tag key={k} className="!m-0">{k}: {v}</Tag>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-2 space-y-4">
          {/* 各维度得分（§14.3 dimension_scores） */}
          {dimensionEntries.length > 0 && (
            <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6">
              <h3 className="text-sm font-bold text-[#232529] mb-4">维度得分</h3>
              <div className="space-y-3">
                {dimensionEntries.map(([name, val]) => (
                  <div key={name} className="flex items-center gap-3">
                    <span className="text-sm text-[#232529] w-20 flex-shrink-0">{name}</span>
                    <div className="flex-1 h-2 rounded-full bg-[#F7F8FA] overflow-hidden">
                      <div
                        className="h-full rounded-full bg-[#00BFA5] transition-all"
                        style={{ width: `${Math.min(100, Math.max(0, val))}%` }}
                      />
                    </div>
                    <span className="text-sm font-semibold text-[#232529] w-10 text-right tabular-nums">
                      {Math.round(val)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6">
            <h3 className="text-sm font-bold text-[#232529] mb-3 flex items-center gap-2">
              <StarOutlined className="text-[#00BFA5]" /> 优势亮点
            </h3>
            <div className="space-y-2">
              {report.strengths.map((s, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <CheckCircleOutlined className="text-[#00B578] mt-0.5 flex-shrink-0" />
                  <span className="text-[#232529]">{s}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6">
            <h3 className="text-sm font-bold text-[#232529] mb-3 flex items-center gap-2">
              <WarningOutlined className="text-[#FFAA00]" /> 待改进
            </h3>
            <div className="space-y-2">
              {report.weaknesses.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#FFAA00] mt-1.5 flex-shrink-0" />
                  <span className="text-[#232529]">{w}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6">
            <h3 className="text-sm font-bold text-[#232529] mb-3 flex items-center gap-2">
              <BulbOutlined className="text-[#00BFA5]" /> 改进建议
            </h3>
            <div className="space-y-2">
              {report.suggestions.map((s, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className="text-[#999999] text-xs font-mono min-w-[16px]">{i + 1}.</span>
                  <span className="text-[#232529]">{s}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 逐题详情（全量，仅已结束面试返回） */}
      {questions.length > 0 && (
        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6 mb-6">
          <h3 className="text-sm font-bold text-[#232529] mb-4">
            逐题详情（{questions.length} 题 · 追问 {report.follow_up_count} 次）
          </h3>
          <div className="space-y-3">
            {questions.map((qd) => (
              <div key={qd.question_id} className="bg-[#F7F8FA] rounded-xl p-4">
                <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="tag tag-flame">第 {qd.question_no} 题</span>
                    {qd.category !== null && (
                      <span className="text-xs text-[#999999]">{CATEGORY_LABEL[qd.category] ?? ''}</span>
                    )}
                    {qd.is_follow_up && (
                      <span className="text-xs font-semibold text-[#FFAA00]">追问</span>
                    )}
                  </div>
                  {qd.ai_score !== null ? (
                    <Rate disabled value={qd.ai_score} count={5} className="!text-xs" />
                  ) : (
                    <span className="text-xs text-[#999999]">未评分</span>
                  )}
                </div>
                <p className="text-sm text-[#232529] mb-2 font-medium">{qd.question_text}</p>
                {qd.user_answer && (
                  <p className="text-xs text-[#666666] bg-white rounded-lg p-3 mb-2 leading-relaxed whitespace-pre-wrap">
                    <span className="text-[#999999] font-semibold">我的回答：</span>
                    {qd.user_answer}
                  </p>
                )}
                {qd.ai_comment && (
                  <p className="text-xs text-[#666666] bg-white rounded-lg p-3 leading-relaxed">
                    <span className="text-[#00BFA5] font-semibold">AI 点评：</span>
                    {qd.ai_comment}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <button onClick={() => navigate('/dashboard/interview')} className="btn-flame flex-1">再来一次</button>
        <button onClick={() => navigate('/dashboard/history')} className="btn-ghost flex-1">查看记录</button>
      </div>
    </div>
  );
};

export default ReportPage;
