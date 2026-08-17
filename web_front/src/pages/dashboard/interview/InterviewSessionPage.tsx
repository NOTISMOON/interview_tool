import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { App } from 'antd';
import { useAppStore } from '@/store';
import { mockReport } from '@/lib/mocks/data';
import { QUESTION_TYPE_LABEL } from '@/types';
import type { InterviewQuestion } from '@/types';

/** 思考阶段倒计时总秒数 */
const THINKING_SECONDS = 20;
/** 跳过按钮可用的秒数阈值（10 秒后可提前作答） */
const SKIP_THRESHOLD = 10;
/** 倒计时环半径与周长（r=68） */
const RING_RADIUS = 68;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
/** 录音波形条数量 */
const WAVEFORM_BARS = 36;

type Phase = 'thinking' | 'recording' | 'complete';
interface AnswerRecord {
  id: string;
  followUp: boolean;
  seconds: number;
}

const InterviewSession = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { modal } = App.useApp();
  const { currentInterview, submitAnswer, completeInterview, nextQuestion } = useAppStore();

  const questions = currentInterview?.questions || [];
  const currentIndex = currentInterview?.currentQuestionIndex || 0;
  const currentQuestion: InterviewQuestion | undefined = questions[currentIndex];

  const [phase, setPhase] = useState<Phase>('thinking');
  const [thinkingLeft, setThinkingLeft] = useState(THINKING_SECONDS);
  const [recordingSec, setRecordingSec] = useState(0);
  const [answers, setAnswers] = useState<AnswerRecord[]>([]);

  const thinkingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 无面试数据时退回面试入口
  useEffect(() => {
    if (!currentInterview) {
      navigate('/dashboard/interview', { replace: true });
    }
  }, [currentInterview, navigate]);

  // 清理所有定时器
  const clearAllTimers = useCallback(() => {
    if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
  }, []);

  useEffect(() => () => clearAllTimers(), [clearAllTimers]);

  // ===== 思考阶段：环形倒计时 =====
  const startThinking = useCallback(() => {
    setPhase('thinking');
    setThinkingLeft(THINKING_SECONDS);
    if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
    thinkingTimerRef.current = setInterval(() => {
      setThinkingLeft((prev) => {
        if (prev <= 1) {
          if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
          setPhase('recording');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  // 首次挂载时启动第一题的思考倒计时；后续题目由 completeAnswer 直接调用 startThinking，
  // 避免依赖 currentIndex 变化的副作用，防止「录音」面板在新题出现时闪现一帧
  useEffect(() => {
    startThinking();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const skipThinking = () => {
    if (thinkingLeft > SKIP_THRESHOLD) return;
    if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
    setPhase('recording');
  };

  // ===== 录音阶段：计时与波形 =====
  useEffect(() => {
    if (phase !== 'recording') return;
    setRecordingSec(0);
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    recordingTimerRef.current = setInterval(() => {
      setRecordingSec((p) => p + 1);
    }, 1000);
    return () => {
      if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    };
  }, [phase]);

  // ===== 完成单题作答 =====
  const completeAnswer = () => {
    if (!currentQuestion) return;
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);

    submitAnswer(currentQuestion.id, `（语音回答，时长 ${recordingSec} 秒）`);
    setAnswers((prev) => [
      ...prev,
      { id: currentQuestion.id, followUp: !!currentQuestion.followUp, seconds: recordingSec },
    ]);

    if (currentIndex >= questions.length - 1) {
      completeInterview(mockReport);
      setPhase('complete');
    } else {
      nextQuestion();
      startThinking();
    }
  };

  // ===== 退出确认 =====
  const handleExit = () => {
    modal.confirm({
      title: '退出面试',
      content: '确定要退出面试吗？当前进度将不会保存。',
      okText: '退出',
      cancelText: '继续面试',
      okButtonProps: { danger: true },
      onOk: () => {
        clearAllTimers();
        navigate('/dashboard/interview', { replace: true });
      },
    });
  };

  const formatTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  if (!currentInterview) {
    return null;
  }

  // ===== 完成页 =====
  if (phase === 'complete') {
    const totalSec = answers.reduce((sum, a) => sum + a.seconds, 0);
    const followUpCount = answers.filter((a) => a.followUp).length;
    return (
      <div className="fixed inset-0 z-[100] bg-[#0D1117] text-[#E1E4E8] flex flex-col overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse 80% 60% at 50% 40%, rgba(255,107,53,0.04) 0%, transparent 70%)',
          }}
        />
        <div className="relative z-[2] flex-1 flex flex-col items-center justify-center px-6 max-w-2xl mx-auto w-full">
          <div className="text-center" style={{ animation: 'room-fade-in 0.6s ease-out' }}>
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-[rgba(45,164,78,0.1)] border-2 border-[rgba(45,164,78,0.3)] flex items-center justify-center text-[#2DA44E]">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M8 12l3 3 5-5" />
              </svg>
            </div>
            <h2 className="text-3xl font-bold text-[#F6F8FA] mb-2">面试完成</h2>
            <p className="text-sm text-[#5F6B7A] mb-8">恭喜你完成了本次模拟面试</p>

            <div className="flex items-center justify-center bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-3xl py-5 px-0 max-w-md mx-auto mb-9">
              <div className="flex-1 text-center">
                <span className="block text-3xl font-bold text-[#F6F8FA] tabular-nums">{answers.length}</span>
                <span className="block text-xs text-[#5F6B7A] mt-1">总答题数</span>
              </div>
              <div className="w-px h-9 bg-[rgba(255,255,255,0.08)]" />
              <div className="flex-1 text-center">
                <span className="block text-3xl font-bold text-[#F6F8FA] tabular-nums">{followUpCount}</span>
                <span className="block text-xs text-[#5F6B7A] mt-1">追问次数</span>
              </div>
              <div className="w-px h-9 bg-[rgba(255,255,255,0.08)]" />
              <div className="flex-1 text-center">
                <span className="block text-3xl font-bold text-[#F6F8FA] tabular-nums">{formatTime(totalSec)}</span>
                <span className="block text-xs text-[#5F6B7A] mt-1">总用时</span>
              </div>
            </div>

            <div className="flex gap-3 justify-center flex-wrap">
              <button
                onClick={() => navigate(`/dashboard/report/${id}`, { replace: true })}
                className="inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold bg-[#FF6B35] text-white hover:bg-[#E85D26] hover:-translate-y-px transition-all"
              >
                查看面试报告
              </button>
              <button
                onClick={() => navigate('/dashboard/interview', { replace: true })}
                className="inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold bg-transparent border border-[rgba(255,255,255,0.12)] text-[#8B949E] hover:bg-[rgba(255,255,255,0.05)] hover:text-[#E1E4E8] transition-all"
              >
                再来一次
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!currentQuestion) {
    return null;
  }

  const isUrgent = thinkingLeft <= 5 && phase === 'thinking';
  const canSkip = thinkingLeft <= SKIP_THRESHOLD && phase === 'thinking';
  const ringOffset = RING_CIRCUMFERENCE * (1 - thinkingLeft / THINKING_SECONDS);

  return (
    <div className="fixed inset-0 z-[100] bg-[#0D1117] text-[#E1E4E8] flex flex-col overflow-hidden font-[inherit]">
      {/* 背景光晕 */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% 40%, rgba(255,107,53,0.04) 0%, transparent 70%), radial-gradient(ellipse 50% 40% at 50% 80%, rgba(255,107,53,0.02) 0%, transparent 70%)',
        }}
      />

      {/* 顶部导航 */}
      <div className="relative z-[2] flex items-center justify-between px-6 py-4 border-b border-[rgba(255,255,255,0.06)]">
        <button
          onClick={handleExit}
          className="text-[#5F6B7A] hover:text-[#E1E4E8] hover:bg-[rgba(255,255,255,0.06)] p-1.5 rounded-lg transition-all flex items-center"
          title="退出面试"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
        <div className="flex items-center gap-2.5">
          <span
            className="w-2 h-2 rounded-full bg-[#2DA44E]"
            style={{ boxShadow: '0 0 8px rgba(45,164,78,0.5)', animation: 'room-dot-pulse 2s infinite' }}
          />
          <span className="text-[15px] font-semibold text-[#E1E4E8] tracking-wide">面试进行中</span>
        </div>
        <div className="w-9" />
      </div>

      {/* 主内容区 */}
      <div className="relative z-[2] flex-1 flex flex-col items-center justify-center px-6 py-8 max-w-2xl w-full mx-auto gap-8 overflow-y-auto">
        {/* 题目卡片 */}
        <div className="relative w-full text-center px-9 py-10 bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-3xl backdrop-blur-md overflow-hidden">
          <div className="flex items-center justify-center gap-2 mb-5">
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-[rgba(255,107,53,0.15)] text-[#FFA87A]">
              {currentQuestion.category || '技术基础'}
            </span>
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-[rgba(255,255,255,0.06)] text-[#8B949E]">
              {QUESTION_TYPE_LABEL[currentQuestion.questionType]}
            </span>
            {currentQuestion.followUp && (
              <span
                className="px-3 py-1 rounded-full text-xs font-semibold bg-[rgba(191,135,0,0.15)] text-[#F0C040]"
                style={{ animation: 'room-tag-pop 0.3s ease-out' }}
              >
                追问
              </span>
            )}
          </div>
          <h2 className="text-[22px] font-semibold leading-relaxed text-[#F6F8FA] tracking-wide relative z-[1]">
            {currentQuestion.questionText}
          </h2>
          {/* 顶部光晕 */}
          <div
            className="absolute -top-20 left-1/2 -translate-x-1/2 pointer-events-none"
            style={{
              width: '280px',
              height: '100px',
              background: 'radial-gradient(ellipse, rgba(255,107,53,0.12), transparent 70%)',
            }}
          />
        </div>

        {/* 思考阶段：环形倒计时 */}
        {phase === 'thinking' && (
          <div className="flex flex-col items-center gap-5 w-full">
            <div className="relative w-[140px] h-[140px]">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 160 160">
                <circle cx="80" cy="80" r={RING_RADIUS} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
                <circle
                  cx="80"
                  cy="80"
                  r={RING_RADIUS}
                  fill="none"
                  stroke={isUrgent ? '#CF222E' : '#FF6B35'}
                  strokeWidth="6"
                  strokeLinecap="round"
                  strokeDasharray={RING_CIRCUMFERENCE}
                  strokeDashoffset={ringOffset}
                  style={{
                    transition: 'stroke-dashoffset 1s linear, stroke 0.5s',
                    ...(isUrgent ? { animation: 'ring-urgent-pulse 0.5s infinite' } : {}),
                  }}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span
                  className={`text-[42px] font-bold leading-none tabular-nums transition-colors ${
                    isUrgent ? 'text-[#CF222E]' : 'text-[#F6F8FA]'
                  }`}
                >
                  {thinkingLeft}
                </span>
                <span className="text-[13px] text-[#5F6B7A] mt-0.5">秒</span>
              </div>
            </div>

            <p className={`text-[13px] transition-colors ${isUrgent ? 'text-[#CF222E]' : 'text-[#5F6B7A]'}`}>
              {canSkip ? (isUrgent ? '即将自动进入作答...' : '可以提前作答了') : `${SKIP_THRESHOLD} 秒后可提前作答`}
            </p>

            <button
              onClick={skipThinking}
              disabled={!canSkip}
              className={`inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold transition-all border ${
                canSkip
                  ? 'bg-[rgba(255,107,53,0.12)] border-[rgba(255,107,53,0.25)] text-[#FFA87A] hover:bg-[rgba(255,107,53,0.2)] hover:border-[rgba(255,107,53,0.4)] hover:-translate-y-px'
                  : 'bg-[rgba(255,107,53,0.06)] border-[rgba(255,107,53,0.12)] text-[#5F6B7A] opacity-60 cursor-not-allowed'
              }`}
            >
              <span>跳过思考，开始作答</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        )}

        {/* 录音阶段：录音指示 + 波形 + 完成按钮 */}
        {phase === 'recording' && (
          <div className="flex flex-col items-center gap-5 w-full">
            <div className="flex items-center gap-3">
              <span
                className="w-3.5 h-3.5 rounded-full bg-[#CF222E]"
                style={{ boxShadow: '0 0 12px rgba(207,34,46,0.6)', animation: 'room-pulse 1.2s infinite' }}
              />
              <span className="text-[15px] font-semibold text-[#CF222E] tracking-wide">正在录音</span>
            </div>

            <div className="text-[52px] font-bold text-[#F6F8FA] tabular-nums tracking-tight">
              {formatTime(recordingSec)}
            </div>

            <div className="flex items-center justify-center gap-1 h-[52px] w-full px-4">
              {Array.from({ length: WAVEFORM_BARS }).map((_, i) => (
                <div
                  key={i}
                  className="room-waveform-bar"
                  style={{ ['--wave-delay' as string]: `${i * 0.08}s` }}
                />
              ))}
            </div>

            <button
              onClick={completeAnswer}
              className="inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold bg-[rgba(45,164,78,0.12)] border border-[rgba(45,164,78,0.25)] text-[#5CDB7A] hover:bg-[rgba(45,164,78,0.2)] hover:border-[rgba(45,164,78,0.4)] hover:-translate-y-px transition-all"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M20 6L9 17l-5-5" />
              </svg>
              <span>完成回答，进入下一题</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default InterviewSession;
