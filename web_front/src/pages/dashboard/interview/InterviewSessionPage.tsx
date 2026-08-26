/**
 * 面试会话页（真实后端对接，面试流程功能文档 §5/§6/§8/§9/§12/§13/§15/§16）。
 *
 * 核心机制：
 *   - 三层并发控制：epoch 租约（tab_epoch）随写请求提交；409 冲突按
 *     reason 分类处理（epoch_mismatch 双开降级只读 / version_mismatch
 *     用 latest_state 强制同步 / busy 重试）；
 *   - 刷新恢复：挂载时 GET 状态（携带 tab_id 激活租约），按 Checkpoint
 *     phase 恢复（answering 重新思考倒计时 / analyzing 轮询恢复 /
 *     summarizing 报告轮询）；
 *   - 幂等提交：以 (interview_id, question_index) 为键，超时重发安全；
 *   - 语音作答：Web Speech API 实时转写可编辑，失败降级键盘输入（§8）；
 *   - SSE：复用 notify:push 用户频道监听 interview:taken_over 事件，
 *     新标签页接管时本页即时降级只读（§16）。
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { App } from 'antd';
import {
  getInterviewState,
  submitAnswer,
  getInterviewReport,
  abortInterview,
  regenerateReport,
  extractConflict,
  CATEGORY_LABEL,
  QUESTION_TYPE_LABEL,
} from '@/lib/api/interview';
import type {
  ApiInterviewState,
  ApiInterviewQuestion,
  ApiReportStatus,
} from '@/lib/api/interview';
import { subscribeSSE } from '@/lib/sseBus';
import { TAB_ID } from '@/lib/tabId';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';

/** 思考阶段倒计时总秒数 */
const THINKING_SECONDS = 20;
/** 跳过按钮可用的秒数阈值 */
const SKIP_THRESHOLD = 10;
/** 倒计时环半径与周长（r=68） */
const RING_RADIUS = 68;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
/** 报告轮询间隔与轮询提示阈值 */
const REPORT_POLL_INTERVAL = 3000;
const REPORT_POLL_HINT_ROUNDS = 40;

/** 页面本地阶段（后端 Checkpoint phase 的超集） */
type SessionPhase =
  | 'loading' // 初始加载
  | 'recovering' // 分析中刷新恢复（轮询等待）
  | 'thinking' // 思考倒计时
  | 'answering' // 作答（语音/键盘）
  | 'submitting' // 提交中（Fast Decision 即时判定，秒级）
  | 'summary' // 单题提交后的轻量过渡（loading，异步分析已在后台，追问不暴露）
  | 'summarizing' // 报告生成中
  | 'completed' // 完成
  | 'aborted'; // 已中断

/** 单题统计（完成页汇总用） */
interface SessionStats {
  answered: number;
  followUps: number;
  totalSec: number;
}

const InterviewSession = () => {
  const { id } = useParams<{ id: string }>();
  const interviewId = Number(id);
  const navigate = useNavigate();
  const { message, modal } = App.useApp();

  // ===== 后端状态 =====
  const [epoch, setEpoch] = useState<number>(1);
  const [phase, setPhase] = useState<SessionPhase>('loading');
  const [currentQuestion, setCurrentQuestion] = useState<ApiInterviewQuestion | null>(null);
  const [totalQuestions, setTotalQuestions] = useState(0);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  // ===== 单题作答 =====
  const [thinkingLeft, setThinkingLeft] = useState(THINKING_SECONDS);
  const [answerSec, setAnswerSec] = useState(0);
  /** 报告状态（completed 展示入口） */
  const [reportStatus, setReportStatus] = useState<ApiReportStatus | null>(null);

  // ===== 双开降级 =====
  const [takenOver, setTakenOver] = useState(false);
  /** 接管恢复请求进行中（按钮防抖） */
  const [resumeLoading, setResumeLoading] = useState(false);

  // ===== 统计（完成页） =====
  const statsRef = useRef<SessionStats>({ answered: 0, followUps: 0, totalSec: 0 });

  // ===== 定时器/连接 =====
  const thinkingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const answerTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ===== 语音识别 =====
  const speech = useSpeechRecognition();
  const { isSupported, isListening, transcript, interim, error: speechError } = speech;

  // ------------------------------------------------------------------
  // 定时器清理
  // ------------------------------------------------------------------
  const clearTimers = useCallback(() => {
    if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
    if (answerTimerRef.current) clearInterval(answerTimerRef.current);
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    thinkingTimerRef.current = null;
    answerTimerRef.current = null;
    pollTimerRef.current = null;
  }, []);

  useEffect(() => () => {
    clearTimers();
  }, [clearTimers]);

  // ------------------------------------------------------------------
  // 阶段切换器
  // ------------------------------------------------------------------

  /** 进入思考倒计时（新题/恢复均从此开始） */
  const startThinking = useCallback(() => {
    setPhase('thinking');
    setThinkingLeft(THINKING_SECONDS);
    speech.reset();
    setAnswerSec(0);
    if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
    thinkingTimerRef.current = setInterval(() => {
      setThinkingLeft((prev) => {
        if (prev <= 1) {
          if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
          setPhase('answering');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, [speech]);

  /** 跳过思考直接进入作答 */
  const skipThinking = useCallback(() => {
    if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current);
    setPhase('answering');
  }, []);

  /** 作答阶段：统一启动计时与语音识别（phase 驱动，刷新/跳过/倒计时归零共用） */
  useEffect(() => {
    if (phase !== 'answering') {
      speech.stop();
      return;
    }
    if (answerTimerRef.current) clearInterval(answerTimerRef.current);
    answerTimerRef.current = setInterval(() => setAnswerSec((p) => p + 1), 1000);
    // 支持语音则自动开始识别（麦克风权限已在设备检测授予）
    if (speech.isSupported) {
      speech.start();
    }
    return () => {
      if (answerTimerRef.current) clearInterval(answerTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  /** 提交后轻量过渡（summary）：短暂展示"已收录"后自动进入下一题思考 */
  useEffect(() => {
    if (phase !== 'summary') return;
    const t = setTimeout(() => startThinking(), 500);
    return () => clearTimeout(t);
  }, [phase, startThinking]);

  /** 提交前停止计时与识别 */
  const beforeSubmit = useCallback(() => {
    if (answerTimerRef.current) clearInterval(answerTimerRef.current);
    speech.stop();
  }, [speech]);

  // ------------------------------------------------------------------
  // 报告轮询（summarizing → completed/失败重试）
  // ------------------------------------------------------------------
  const startReportPolling = useCallback(() => {
    setPhase('summarizing');
    let rounds = 0;
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = setInterval(async () => {
      rounds += 1;
      try {
        const res = await getInterviewReport(interviewId);
        setReportStatus(res);
        if (res.status === 'ready' || res.status === 'invalid') {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setPhase('completed');
        }
        // failed：停在轮询外由 UI 提供手动重试（regenerate 后重新轮询）
        if (res.status === 'failed') {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        }
      } catch {
        // 单次轮询失败忽略，下轮重试
      }
      if (rounds === REPORT_POLL_HINT_ROUNDS) {
        message.info('报告生成较慢，仍在努力中…');
      }
    }, REPORT_POLL_INTERVAL);
  }, [interviewId, message]);

  /** 手动重试报告（后端 LLM 失败后暴露的 regenerate，§13.1） */
  const handleRegenerateReport = useCallback(async () => {
    try {
      await regenerateReport(interviewId);
      message.success('已重新触发报告生成');
      startReportPolling();
    } catch {
      message.error('触发重试失败，请稍后再试');
    }
  }, [interviewId, message, startReportPolling]);

  // ------------------------------------------------------------------
  // 状态同步与刷新恢复（§15）
  // ------------------------------------------------------------------

  /** 按 Checkpoint phase 将后端状态映射到本地阶段 */
  const applyState = useCallback((state: ApiInterviewState) => {
    setEpoch(state.epoch);
    setTotalQuestions(state.total_questions);
    setAnsweredCount(state.answered_count);
    setCurrentQuestion(state.current_question);
    statsRef.current.answered = Math.max(statsRef.current.answered, state.answered_count);

    if (state.status === 2) {
      setPhase('aborted');
      return;
    }
    if (state.status === 1) {
      // 已完成：进入报告轮询（刷新直接落完成页）
      startReportPolling();
      return;
    }
    switch (state.phase) {
      case 'analyzing':
        // 提交中刷新：轮询等待分析落库（幂等数据 ready 后推进）
        setPhase('recovering');
        break;
      case 'summarizing':
        startReportPolling();
        break;
      case 'answering':
      default:
        startThinking();
        break;
    }
  }, [startReportPolling, startThinking]);

  /** 恢复轮询：analyzing 状态下等待后端完成或回退作答 */
  useEffect(() => {
    if (phase !== 'recovering') return;
    let elapsed = 0;
    pollTimerRef.current = setInterval(async () => {
      elapsed += 3;
      try {
        const state = await getInterviewState(interviewId);
        if (state.phase !== 'analyzing') {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          applyState(state);
        } else if (elapsed >= 60) {
          // 长时间未恢复（服务重启等）：回退作答重新提交（幂等保证不重跑）
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          startThinking();
        }
      } catch {
        // 网络抖动忽略
      }
    }, 3000);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  /** 挂载：激活租约 + 拉取状态恢复（§5.6/§15） */
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const state = await getInterviewState(interviewId, true);
        if (!mounted) return;
        applyState(state);
      } catch (err) {
        if (!mounted) return;
        // StrictMode 双挂载/页面切换时浏览器取消请求（ERR_CANCELED）
        // 属预期现象，不作为加载失败；仅真实网络错误才提示
        const code = (err as { code?: string })?.code;
        if (code === 'ERR_CANCELED') return;
        setLoadError('面试状态加载失败，请刷新重试');
      }
    })();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  // ------------------------------------------------------------------
  // SSE：双开接管事件（§16 taken_over，共享总线单连接，见 sseBus）
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!interviewId) return;
    const unsubscribe = subscribeSSE((data) => {
      // 仅处理本面试的接管事件，且接管者不是自己（自己触发 epoch+1 时
      // 广播会回环到自己，凭事件体 tab_id 过滤避免自降级）
      if (
        data.kind === 'interview:taken_over' &&
        Number(data.session_id) === interviewId &&
        data.tab_id !== TAB_ID
      ) {
        setTakenOver(true);
        clearTimers();
        speech.stop();
      }
    });
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  /** 被接管页恢复：重新激活租约（epoch+1 接管回来，对方降级）并同步最新状态 */
  const handleResumeFromTakeover = useCallback(async () => {
    setResumeLoading(true);
    try {
      // 携带 tab_id 激活：本页 tab_id ≠ 当前持有者 → epoch+1 接管，
      // 后端广播 taken_over（携带本页 tab_id），对方页面收到后降级只读
      const state = await getInterviewState(interviewId, true);
      setTakenOver(false);
      applyState(state);
      message.success('已在本页面继续作答');
    } catch {
      message.error('接管失败，请稍后重试');
    } finally {
      setResumeLoading(false);
    }
  }, [applyState, interviewId, message]);

  // ------------------------------------------------------------------
  // 提交回答（§8.4：校验→幂等→LLM→落库；409 分类处理）
  // ------------------------------------------------------------------
  const handleSubmit = useCallback(async () => {
    if (!currentQuestion || !transcript.trim()) {
      message.warning('回答内容为空，请先作答');
      return;
    }
    beforeSubmit();
    setPhase('submitting');
    try {
      const res = await submitAnswer(
        interviewId,
        currentQuestion.question_index,
        transcript.trim(),
        epoch,
        answerSec,
      );
      // 仅非幂等计入本地统计；已答题数以服务端 answered_count 为准
      if (!res.duplicated) {
        statsRef.current.answered += 1;
        statsRef.current.totalSec += answerSec;
      }
      setAnsweredCount(statsRef.current.answered);
      // v2：Fast Decision 即时返回 → 提交后立即进入下一题（不暴露追问，loading 过渡）
      if (res.phase === 'summarizing' || !res.next_question) {
        startReportPolling();
      } else {
        setCurrentQuestion(res.next_question);
        setPhase('summary'); // 轻量过渡，随即进入思考/作答
      }
    } catch (err) {
      const conflict = extractConflict(err);
      if (conflict?.reason === 'epoch_mismatch') {
        setTakenOver(true);
        return;
      }
      if (conflict?.reason === 'version_mismatch' && conflict.latest_state) {
        message.warning('状态已变化，已为你同步最新进度');
        applyState(conflict.latest_state);
        return;
      }
      if (conflict?.reason === 'busy') {
        message.warning('操作过于频繁，请稍候重试');
        setPhase('answering');
        return;
      }
      if (conflict?.reason === 'finished' && conflict.latest_state) {
        applyState(conflict.latest_state);
        return;
      }
      // LLM 失败（502等）：回退作答允许重试（后端幂等，同题连续2次自动跳过）
      message.error('分析服务异常，请重试提交');
      setPhase('answering');
    }
  }, [answerSec, applyState, beforeSubmit, currentQuestion, epoch, interviewId, message, startReportPolling, transcript]);

  /** feedback → 下一题 / 进入报告等待（v2 已移除 feedback 停留，本方法删除） */

  // ------------------------------------------------------------------
  // 退出/放弃（§21 abort）
  // ------------------------------------------------------------------
  const handleExit = useCallback(() => {
    modal.confirm({
      title: '退出面试',
      content: '确定要放弃本次面试吗？已完成的回答将保留，但不会生成报告。',
      okText: '放弃面试',
      cancelText: '继续面试',
      okButtonProps: { danger: true },
      onOk: async () => {
        clearTimers();
        speech.stop();
        try {
          await abortInterview(interviewId, epoch);
        } catch {
          // 放弃失败（已超时中断等）不阻塞退出
        }
        navigate('/dashboard/interview', { replace: true });
      },
    });
  }, [clearTimers, epoch, interviewId, navigate, speech]);

  const formatTime = (s: number) =>
    `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  // ------------------------------------------------------------------
  // 渲染
  // ------------------------------------------------------------------

  /** 语音错误提示文案（§8.3） */
  const speechErrorText = !isSupported
    ? '当前浏览器不支持语音识别，请使用 Chrome / Edge，或直接键盘输入'
    : speechError === 'network'
      ? '语音服务连接失败（Chrome 走 Google 云端识别），建议改用 Edge 或键盘输入'
      : speechError === 'not-allowed'
        ? '麦克风权限被拒绝，请在浏览器地址栏允许后重试，或改用键盘输入'
        : null;

  if (loadError) {
    return (
      <div className="fixed inset-0 z-[100] bg-[#232529] text-[#E8E8E8] flex flex-col items-center justify-center gap-4">
        <p className="text-sm text-[#999999]">{loadError}</p>
        <button onClick={() => navigate('/dashboard/interview')} className="btn-ghost">
          返回面试入口
        </button>
      </div>
    );
  }

  // ===== 双开只读覆盖层（§5.6：另一页面持有租约，本页只读待恢复） =====
  if (takenOver) {
    return (
      <div className="fixed inset-0 z-[100] bg-[#232529] text-[#E8E8E8] flex flex-col items-center justify-center gap-5 px-6">
        <div className="w-16 h-16 rounded-full bg-[rgba(4,120,87,0.12)] border-2 border-[rgba(4,120,87,0.32)] flex items-center justify-center text-3xl">
          🖥️
        </div>
        <h2 className="text-xl font-bold text-[#F7F8FA]">面试已在另一个页面打开</h2>
        <p className="text-sm text-[#666666] max-w-sm text-center">
          本场面试正在其他标签页进行作答，两个页面共享同一场面试数据。
          在此页面继续将接管作答权，另一页面会自动变为只读提示。
        </p>
        <div className="flex items-center gap-3 flex-wrap justify-center">
          <button
            onClick={handleResumeFromTakeover}
            disabled={resumeLoading}
            className={`inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold transition-all ${
              resumeLoading
                ? 'bg-[rgba(4,120,87,0.09)] border border-[rgba(4,120,87,0.15)] text-[#666666] cursor-not-allowed'
                : 'bg-[#047857] text-white hover:bg-[#065F46] hover:-translate-y-px'
            }`}
          >
            {resumeLoading ? (
              <>
                <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                正在接管…
              </>
            ) : (
              '在此页面继续作答'
            )}
          </button>
          <button
            onClick={() => navigate('/dashboard')}
            className="inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold bg-transparent border border-[rgba(255,255,255,0.12)] text-[#999999] hover:bg-[rgba(255,255,255,0.05)] hover:text-[#E8E8E8] transition-all"
          >
            返回工作台
          </button>
        </div>
        <p className="text-xs text-[#666666]/60">
          已答题目、评分与追问进度实时共享，接管后从最新进度继续
        </p>
      </div>
    );
  }

  // ===== 已中断 =====
  if (phase === 'aborted') {
    return (
      <div className="fixed inset-0 z-[100] bg-[#232529] text-[#E8E8E8] flex flex-col items-center justify-center gap-4 px-6">
        <h2 className="text-xl font-bold text-[#F7F8FA]">面试已中断</h2>
        <p className="text-sm text-[#666666]">本场面试已结束（主动放弃或超时），已答题目与评分已保留</p>
        <div className="flex gap-3">
          <button onClick={() => navigate('/dashboard/history', { replace: true })} className="btn-ghost">
            查看面试记录
          </button>
          <button onClick={() => navigate('/dashboard/interview', { replace: true })} className="btn-flame">
            再来一次
          </button>
        </div>
      </div>
    );
  }

  // ===== 完成/报告页 =====
  if (phase === 'completed') {
    const stats = statsRef.current;
    return (
      <div className="fixed inset-0 z-[100] bg-[#232529] text-[#E8E8E8] flex flex-col overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: 'radial-gradient(ellipse 80% 60% at 50% 40%, rgba(4,120,87,0.07) 0%, transparent 70%)' }}
        />
        <div className="relative z-[2] flex-1 flex flex-col items-center justify-center px-6 max-w-2xl mx-auto w-full">
          <div className="text-center" style={{ animation: 'room-fade-in 0.6s ease-out' }}>
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-[rgba(16,185,129,0.12)] border-2 border-[rgba(16,185,129,0.32)] flex items-center justify-center text-[#10B981]">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M8 12l3 3 5-5" />
              </svg>
            </div>
            <h2 className="text-3xl font-bold text-[#F7F8FA] mb-2">面试完成</h2>
            <p className="text-sm text-[#666666] mb-8">
              {reportStatus?.status === 'ready' ? '报告已生成完毕' : '恭喜你完成了本次模拟面试'}
            </p>

            <div className="flex items-center justify-center bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-3xl py-5 px-0 max-w-md mx-auto mb-9">
              <div className="flex-1 text-center">
                <span className="block text-3xl font-bold text-[#F7F8FA] tabular-nums">{stats.answered}</span>
                <span className="block text-xs text-[#666666] mt-1">总答题数</span>
              </div>
              <div className="w-px h-9 bg-[rgba(255,255,255,0.08)]" />
              <div className="flex-1 text-center">
                <span className="block text-3xl font-bold text-[#F7F8FA] tabular-nums">{stats.followUps}</span>
                <span className="block text-xs text-[#666666] mt-1">追问次数</span>
              </div>
              <div className="w-px h-9 bg-[rgba(255,255,255,0.08)]" />
              <div className="flex-1 text-center">
                <span className="block text-3xl font-bold text-[#F7F8FA] tabular-nums">{formatTime(stats.totalSec)}</span>
                <span className="block text-xs text-[#666666] mt-1">总用时</span>
              </div>
            </div>

            <div className="flex gap-3 justify-center flex-wrap">
              {reportStatus?.status === 'ready' ? (
                <button
                  onClick={() => navigate(`/dashboard/report/${interviewId}`, { replace: true })}
                  className="inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold bg-[#047857] text-white hover:bg-[#065F46] hover:-translate-y-px transition-all"
                >
                  查看面试报告
                </button>
              ) : reportStatus?.status === 'failed' ? (
                <button
                  onClick={handleRegenerateReport}
                  className="inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold bg-[#047857] text-white hover:bg-[#065F46] hover:-translate-y-px transition-all"
                >
                  报告生成失败，点击重试
                </button>
              ) : (
                <div className="flex items-center gap-3 px-7 py-3 rounded-xl bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)]">
                  <span className="w-4 h-4 rounded-full border-2 border-[rgba(255,255,255,0.15)] border-t-[#047857] animate-spin" />
                  <span className="text-[15px] text-[#999999]">报告生成中…</span>
                </div>
              )}
              <button
                onClick={() => navigate('/dashboard/interview', { replace: true })}
                className="inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold bg-transparent border border-[rgba(255,255,255,0.12)] text-[#999999] hover:bg-[rgba(255,255,255,0.05)] hover:text-[#E8E8E8] transition-all"
              >
                再来一次
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ===== 加载中 =====
  if (phase === 'loading' || !currentQuestion) {
    return (
      <div className="fixed inset-0 z-[100] bg-[#232529] flex flex-col items-center justify-center gap-4">
        <div className="w-10 h-10 rounded-full border-4 border-[rgba(255,255,255,0.08)] border-t-[#047857] animate-spin" />
        <p className="text-sm text-[#666666]">正在恢复面试状态…</p>
      </div>
    );
  }

  const isUrgent = thinkingLeft <= 5 && phase === 'thinking';
  const canSkip = thinkingLeft <= SKIP_THRESHOLD && phase === 'thinking';
  const ringOffset = RING_CIRCUMFERENCE * (1 - thinkingLeft / THINKING_SECONDS);
  // v2 决策3：追问不暴露给用户；进度统一按基础题号展示
  const progressLabel = `第 ${currentQuestion.question_no} / ${totalQuestions} 题`;

  return (
    <div className="fixed inset-0 z-[100] bg-[#232529] text-[#E8E8E8] flex flex-col overflow-hidden font-[inherit]">
      {/* 背景光晕 */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% 40%, rgba(4,120,87,0.07) 0%, transparent 70%), radial-gradient(ellipse 50% 40% at 50% 80%, rgba(6,95,70,0.05) 0%, transparent 70%)',
        }}
      />

      {/* 顶部导航 */}
      <div className="relative z-[2] flex items-center justify-between px-6 py-4 border-b border-[rgba(255,255,255,0.06)]">
        <button
          onClick={handleExit}
          className="text-[#666666] hover:text-[#E8E8E8] hover:bg-[rgba(255,255,255,0.06)] p-1.5 rounded-lg transition-all flex items-center"
          title="放弃并退出面试"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
        <div className="flex items-center gap-2.5">
          <span
            className="w-2 h-2 rounded-full bg-[#10B981]"
            style={{ boxShadow: '0 0 8px rgba(16,185,129,0.5)', animation: 'room-dot-pulse 2s infinite' }}
          />
          <span className="text-[15px] font-semibold text-[#E8E8E8] tracking-wide">
            面试进行中 · {progressLabel}
          </span>
        </div>
        <div className="text-xs text-[#666666] tabular-nums">已答 {answeredCount} 题</div>
      </div>

      {/* 主内容区 */}
      <div className="relative z-[2] flex-1 flex flex-col items-center justify-center px-6 py-8 max-w-2xl w-full mx-auto gap-8 overflow-y-auto">
        {/* 题目卡片 */}
        <div className="relative w-full text-center px-9 py-10 bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-3xl backdrop-blur-md overflow-hidden">
          <div className="flex items-center justify-center gap-2 mb-5 flex-wrap">
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-[rgba(4,120,87,0.18)] text-[#6EE7B7]">
              {CATEGORY_LABEL[currentQuestion.category ?? 1]}
            </span>
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-[rgba(255,255,255,0.06)] text-[#999999]">
              {QUESTION_TYPE_LABEL[currentQuestion.question_type]}
            </span>
          </div>
          <h2 className="text-[22px] font-semibold leading-relaxed text-[#F7F8FA] tracking-wide relative z-[1]">
            {currentQuestion.question_text}
          </h2>
          <div
            className="absolute -top-20 left-1/2 -translate-x-1/2 pointer-events-none"
            style={{ width: '280px', height: '100px', background: 'radial-gradient(ellipse, rgba(4,120,87,0.15), transparent 70%)' }}
          />
        </div>

        {/* 思考阶段：环形倒计时 */}
        {phase === 'thinking' && (
          <div className="flex flex-col items-center gap-5 w-full">
            <div className="relative w-[140px] h-[140px]">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 160 160">
                <circle cx="80" cy="80" r={RING_RADIUS} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
                <circle
                  cx="80" cy="80" r={RING_RADIUS} fill="none"
                  stroke={isUrgent ? '#F53535' : '#047857'} strokeWidth="6" strokeLinecap="round"
                  strokeDasharray={RING_CIRCUMFERENCE} strokeDashoffset={ringOffset}
                  style={{ transition: 'stroke-dashoffset 1s linear, stroke 0.5s', ...(isUrgent ? { animation: 'ring-urgent-pulse 0.5s infinite' } : {}) }}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={`text-[42px] font-bold leading-none tabular-nums transition-colors ${isUrgent ? 'text-[#F53535]' : 'text-[#F7F8FA]'}`}>
                  {thinkingLeft}
                </span>
                <span className="text-[13px] text-[#666666] mt-0.5">秒</span>
              </div>
            </div>
            <p className={`text-[13px] transition-colors ${isUrgent ? 'text-[#F53535]' : 'text-[#666666]'}`}>
              {canSkip ? (isUrgent ? '即将自动进入作答...' : '可以提前作答了') : `${SKIP_THRESHOLD} 秒后可提前作答`}
            </p>
            <button
              onClick={skipThinking}
              disabled={!canSkip}
              className={`inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold transition-all border ${
                canSkip
                  ? 'bg-[rgba(4,120,87,0.15)] border-[rgba(4,120,87,0.32)] text-[#6EE7B7] hover:bg-[rgba(4,120,87,0.25)] hover:border-[rgba(4,120,87,0.45)] hover:-translate-y-px'
                  : 'bg-[rgba(4,120,87,0.09)] border-[rgba(4,120,87,0.15)] text-[#666666] opacity-60 cursor-not-allowed'
              }`}
            >
              <span>跳过思考，开始作答</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        )}

        {/* 作答阶段：语音识别 + 可编辑转写 + 键盘输入兜底（§8） */}
        {phase === 'answering' && (
          <div className="flex flex-col items-center gap-5 w-full">
            <div className="flex items-center gap-3">
              <span
                className={`w-3.5 h-3.5 rounded-full ${isListening ? 'bg-[#F53535]' : 'bg-[#666666]'}`}
                style={isListening ? { boxShadow: '0 0 12px rgba(245,53,53,0.6)', animation: 'room-pulse 1.2s infinite' } : undefined}
              />
              <span className={`text-[15px] font-semibold tracking-wide ${isListening ? 'text-[#F53535]' : 'text-[#666666]'}`}>
                {isListening ? '正在录音识别' : '语音识别已暂停'}
              </span>
              <span className="text-[15px] font-bold text-[#F7F8FA] tabular-nums">{formatTime(answerSec)}</span>
            </div>

            {/* 识别中波形 */}
            {isListening && (
              <div className="flex items-center justify-center gap-1 h-[40px] w-full px-4">
                {Array.from({ length: 36 }).map((_, i) => (
                  <div key={i} className="room-waveform-bar" style={{ ['--wave-delay' as string]: `${i * 0.08}s` }} />
                ))}
              </div>
            )}

            {/* 转写文本（可编辑修正，§8.1） */}
            <div className="w-full">
              <textarea
                value={transcript}
                onChange={(e) => speech.setTranscript(e.target.value)}
                placeholder={
                  isSupported
                    ? '语音识别内容将实时显示在这里，可编辑修正后提交；也可以直接键盘输入'
                    : '当前浏览器不支持语音识别，请直接键盘输入你的回答'
                }
                rows={6}
                className="w-full px-5 py-4 rounded-2xl bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] text-[15px] text-[#F7F8FA] placeholder:text-[#666666] leading-relaxed resize-none focus:outline-none focus:border-[rgba(4,120,87,0.45)] transition-colors"
              />
              {/* 实时中间结果预览 */}
              {interim && (
                <p className="mt-2 px-2 text-sm text-[#666666] italic truncate">{interim}</p>
              )}
              {speechErrorText && (
                <p className="mt-2 px-2 text-xs text-[#C9A24B]">{speechErrorText}</p>
              )}
            </div>

            <div className="flex items-center gap-3 flex-wrap justify-center">
              {isSupported && (
                <button
                  onClick={() => (isListening ? speech.stop() : speech.start())}
                  className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold border transition-all ${
                    isListening
                      ? 'bg-[rgba(245,53,53,0.15)] border-[rgba(245,53,53,0.32)] text-[#F5A3A3] hover:bg-[rgba(245,53,53,0.25)]'
                      : 'bg-[rgba(4,120,87,0.15)] border-[rgba(4,120,87,0.32)] text-[#6EE7B7] hover:bg-[rgba(4,120,87,0.25)]'
                  }`}
                >
                  {isListening ? '暂停语音识别' : '继续语音识别'}
                </button>
              )}
              <button
                onClick={handleSubmit}
                disabled={!transcript.trim()}
                className={`inline-flex items-center gap-2 px-7 py-3 rounded-xl text-[15px] font-semibold transition-all ${
                  transcript.trim()
                    ? 'bg-[rgba(16,185,129,0.15)] border border-[rgba(16,185,129,0.32)] text-[#6EE7B7] hover:bg-[rgba(16,185,129,0.25)] hover:border-[rgba(16,185,129,0.45)] hover:-translate-y-px'
                    : 'bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] text-[#666666] opacity-60 cursor-not-allowed'
                }`}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
                <span>完成回答，提交分析</span>
              </button>
            </div>
          </div>
        )}

        {/* 提交中：Fast Decision 即时判定，秒级进下一题 */}
        {phase === 'submitting' && (
          <div className="flex flex-col items-center gap-5 w-full">
            <div className="w-14 h-14 rounded-full border-4 border-[rgba(255,255,255,0.06)] border-t-[#047857] animate-spin" />
            <div className="text-center">
              <p className="text-[16px] font-semibold text-[#F7F8FA]">正在判定下一题…</p>
              <p className="text-[13px] text-[#666666] mt-1">回答已收录，即将进入下一题</p>
            </div>
          </div>
        )}

        {/* 轻量过渡：回答已收录，异步分析在后台进行（追问不暴露） */}
        {phase === 'summary' && (
          <div className="flex flex-col items-center gap-5 w-full">
            <div className="w-12 h-12 rounded-full border-4 border-[rgba(255,255,255,0.06)] border-t-[#047857] animate-spin" />
            <p className="text-[14px] text-[#999999]">回答已收录，正在准备下一题…</p>
          </div>
        )}

        {/* 分析恢复中（analyzing 刷新，§15） */}
        {phase === 'recovering' && (
          <div className="flex flex-col items-center gap-5 w-full">
            <div className="w-14 h-14 rounded-full border-4 border-[rgba(255,255,255,0.06)] border-t-[#047857] animate-spin" />
            <p className="text-[15px] text-[#999999]">正在恢复上一次的分析结果…</p>
          </div>
        )}

        {/* 报告生成中（summarizing，§13） */}
        {phase === 'summarizing' && (
          <div className="flex flex-col items-center gap-5 w-full">
            <div className="w-16 h-16 rounded-full border-4 border-[rgba(255,255,255,0.06)] border-t-[#047857] animate-spin" />
            <div className="text-center">
              <p className="text-[17px] font-semibold text-[#F7F8FA]">所有题目已完成</p>
              <p className="text-[14px] text-[#666666] mt-1.5">AI 正在后台生成你的面试报告，完成后将通过消息通知你，可先离开稍后查看</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default InterviewSession;
