import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import App from 'antd/es/app';
import Steps from 'antd/es/steps';
import {
  ArrowLeftOutlined,
  ThunderboltOutlined,
  AudioOutlined,
  VideoCameraOutlined,
} from '@/components/icons';
import { extractConflict, getInterviewState, startInterview } from '@/lib/api/interview';

/** 设备检测状态 */
type DeviceState = 'idle' | 'testing' | 'ready' | 'error';

const DeviceCheckPage = () => {
  const { id } = useParams<{ id: string }>();
  const interviewId = Number(id);

  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  /** 题目生成中（create_interview 尚未返回，total_questions=0） */
  const [generating, setGenerating] = useState(false);

  // 设备检测状态
  const [micState, setMicState] = useState<DeviceState>('idle');
  const [camState, setCamState] = useState<DeviceState>('idle');
  const [volumeBars, setVolumeBars] = useState<number[]>(() => Array(20).fill(8));

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const volumeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const navigate = useNavigate();
  const { message } = App.useApp();

  // 校验：面试存在且为草稿态（not_started），非草稿/已启动/已完成则分流；
  // 题目生成中（total_questions=0，create_interview 未返回）展示生成中状态
  const runCheck = useCallback(async () => {
    setLoading(true);
    setNotFound(false);
    setGenerating(false);
    try {
      const state = await getInterviewState(interviewId);
      if (state.status !== 0) {
        // 已完成/中断：引导回记录页
        navigate(`/dashboard/history`, { replace: true });
        return;
      }
      if (state.phase !== 'not_started') {
        // 已正式启动：直接进面试间
        navigate(`/dashboard/interview/session/${interviewId}`, { replace: true });
        return;
      }
      if (state.total_questions === 0) {
        // 题目仍在生成中：展示生成中状态，等待重新检测
        setGenerating(true);
        setLoading(false);
        return;
      }
      setLoading(false);
    } catch {
      setNotFound(true);
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  // 挂载时校验
  useEffect(() => {
    runCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  // 组件卸载时释放摄像头/麦克风资源
  useEffect(() => {
    return () => {
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (volumeTimerRef.current) clearInterval(volumeTimerRef.current);
    };
  }, []);

  /** 麦克风检测 */
  const testMicrophone = async () => {
    setMicState('testing');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      }
      mediaStreamRef.current = stream;

      // 模拟音量条波动
      if (volumeTimerRef.current) clearInterval(volumeTimerRef.current);
      volumeTimerRef.current = setInterval(() => {
        setVolumeBars(Array(20).fill(0).map(() => Math.floor(Math.random() * 30) + 6));
      }, 120);

      setTimeout(() => {
        setMicState('ready');
      }, 1800);
    } catch {
      setMicState('error');
    }
  };

  /** 摄像头检测 */
  const testCamera = async () => {
    setCamState('testing');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      // 合并到同一个 stream 引用，便于统一释放
      if (!mediaStreamRef.current) {
        mediaStreamRef.current = stream;
      } else {
        const existing = mediaStreamRef.current;
        stream.getVideoTracks().forEach((t) => existing.addTrack(t));
      }
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play().catch(() => {});
      }
      setCamState('ready');
    } catch {
      setCamState('error');
    }
  };

  const bothReady = micState === 'ready' && camState === 'ready';

  /** 设备检测通过 → 正式启动面试（草稿→作答）→ 跳面试间 */
  const handleStart = async () => {
    try {
      await startInterview(interviewId);
      navigate(`/dashboard/interview/session/${interviewId}`);
    } catch (err) {
      const conflict = extractConflict(err);
      if (conflict?.reason === 'finished') {
        message.info('该面试已结束，请重新创建');
        navigate('/dashboard/interview', { replace: true });
      } else {
        message.error('启动面试失败，请重试');
      }
    }
  };

  const micText: Record<DeviceState, string> = {
    idle: '等待检测',
    testing: '正在检测...',
    ready: '✅ 麦克风正常',
    error: '❌ 无法访问麦克风，请检查权限',
  };
  const camText: Record<DeviceState, string> = {
    idle: '等待检测',
    testing: '正在检测...',
    ready: '✅ 摄像头正常',
    error: '❌ 无法访问摄像头，请检查权限',
  };

  const deviceCardClass = (s: DeviceState) =>
    `bg-[#F7F8FA] border-2 rounded-2xl p-6 text-center transition-all duration-300 ${
      s === 'ready' ? 'border-[#00B578]' : s === 'error' ? 'border-[#F53535]' : s === 'testing' ? 'border-[#FFAA00]' : 'border-[#E8E8E8]'
    }`;

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="flex items-center gap-3 mb-5">
          <button
            onClick={() => navigate('/dashboard/interview')}
            className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-xl font-bold text-[#232529]">设备检测</h1>
        </div>

        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-4 mb-5">
          <Steps
            current={1}
            items={['选择简历', '设备检测', '开始面试'].map((t, i) => ({
              title: (
                <span
                  style={{
                    color: 'var(--color-ink)',
                    opacity: i === 1 ? 1 : 0.85,
                    fontWeight: i === 1 ? 600 : 400,
                  }}
                >
                  {t}
                </span>
              ),
            }))}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <span className="text-sm text-[#999999]">正在校验面试状态...</span>
          </div>
        ) : notFound ? (
          <div className="bg-white border border-[#E8E8E8] rounded-2xl p-16 text-center">
            <h2 className="text-lg font-bold text-[#232529] mb-2">面试不存在</h2>
            <p className="text-sm text-[#666666] mb-6">该面试可能已被删除或链接无效</p>
            <button onClick={() => navigate('/dashboard/interview')} className="btn-flame">
              返回开始面试
            </button>
          </div>
        ) : generating ? (
          <div className="bg-white border border-[#E8E8E8] rounded-2xl p-16 text-center">
            <div className="w-10 h-10 rounded-full border-4 border-[rgba(217,164,65,0.25)] border-t-[#D9A441] animate-spin mx-auto mb-4" />
            <h2 className="text-lg font-bold text-[#232529] mb-2">题目正在生成中</h2>
            <p className="text-sm text-[#666666] mb-6">AI 正在根据你的简历生成面试题目，请稍候后重新检测</p>
            <div className="flex items-center justify-center gap-3">
              <button onClick={runCheck} className="btn-flame">重新检测</button>
              <button onClick={() => navigate('/dashboard/interview')} className="btn-ghost">返回面试入口</button>
            </div>
          </div>
        ) : (
          <div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              {/* 麦克风检测 */}
              <div className={deviceCardClass(micState)}>
                <div className="text-4xl mb-3 text-[#666666]">
                  <AudioOutlined />
                </div>
                <div className="text-[15px] font-bold text-[#232529] mb-1">麦克风检测</div>
                <div
                  className={`text-[13px] mb-3 ${
                    micState === 'ready' ? 'text-[#00B578]' : micState === 'error' ? 'text-[#F53535]' : 'text-[#666666]'
                  }`}
                >
                  {micText[micState]}
                </div>
                <div className="w-full h-[120px] rounded-xl bg-[#232529] flex items-center justify-center mb-3 overflow-hidden">
                  <div className="flex items-end justify-center gap-[3px] h-10 w-full px-4">
                    {volumeBars.map((h, i) => (
                      <div
                        key={i}
                        className="w-1 rounded-sm transition-all duration-100"
                        style={{
                          height: `${h}px`,
                          background: micState === 'ready' ? '#00B578' : '#E8E8E8',
                        }}
                      />
                    ))}
                  </div>
                </div>
                <button
                  onClick={testMicrophone}
                  disabled={micState === 'testing'}
                  className="btn-ghost w-full !py-2 !text-sm"
                >
                  {micState === 'testing' ? '检测中...' : micState === 'ready' ? '重新测试' : '测试麦克风'}
                </button>
              </div>

              {/* 摄像头检测 */}
              <div className={deviceCardClass(camState)}>
                <div className="text-4xl mb-3 text-[#666666]">
                  <VideoCameraOutlined />
                </div>
                <div className="text-[15px] font-bold text-[#232529] mb-1">摄像头检测</div>
                <div
                  className={`text-[13px] mb-3 ${
                    camState === 'ready' ? 'text-[#00B578]' : camState === 'error' ? 'text-[#F53535]' : 'text-[#666666]'
                  }`}
                >
                  {camText[camState]}
                </div>
                <div className="w-full h-[120px] rounded-xl bg-[#232529] flex items-center justify-center mb-3 overflow-hidden">
                  <video
                    ref={videoRef}
                    autoPlay
                    muted
                    playsInline
                    className="w-full h-full object-cover rounded-xl"
                    style={{ display: camState === 'ready' ? 'block' : 'none' }}
                  />
                  {camState !== 'ready' && (
                    <span className="text-[#8A8F99] text-xs">摄像头预览</span>
                  )}
                </div>
                <button
                  onClick={testCamera}
                  disabled={camState === 'testing'}
                  className="btn-ghost w-full !py-2 !text-sm"
                >
                  {camState === 'testing' ? '检测中...' : camState === 'ready' ? '重新测试' : '测试摄像头'}
                </button>
              </div>
            </div>

            <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6 text-center">
              <p className="text-sm text-[#666666] mb-3">
                面试将以<strong className="text-[#232529]">语音回答</strong>为主，请确保麦克风正常工作
              </p>
              <button
                onClick={handleStart}
                disabled={!bothReady}
                className={`btn-flame btn-flame-lg ${!bothReady ? '!opacity-50 !cursor-not-allowed' : ''}`}
              >
                {bothReady ? (
                  <span className="inline-flex items-center gap-2">
                    <ThunderboltOutlined /> 开始面试
                  </span>
                ) : (
                  '请先完成设备检测'
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DeviceCheckPage;
