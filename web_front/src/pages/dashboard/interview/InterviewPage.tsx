import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Steps } from 'antd';
import {
  ArrowLeftOutlined,
  ThunderboltOutlined,
  FileTextOutlined,
  PlusOutlined,
  CheckOutlined,
  AudioOutlined,
  VideoCameraOutlined,
  LoadingOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useAppStore } from '@/store';
import { mockQuestions } from '@/lib/mocks/data';
import { FileUpload } from '@/components/upload/FileUpload';
import {
  getResumes,
  deleteResume,
  retryResume,
  RESUME_STATUS_LABEL,
} from '@/lib/api/resume';
import type { ApiResume } from '@/lib/api/resume';

/** 步骤条索引：0=选择简历, 1=AI 分析, 2=设备检测 */
type StepIndex = 0 | 1 | 2;
type DeviceState = 'idle' | 'testing' | 'ready' | 'error';

/** AI 分析的四个子步骤文案 */
const ANALYSIS_STEPS = [
  '提取简历关键信息',
  '分析技术栈与项目经验',
  '生成个性化面试题目',
  '构建面试者能力画像',
];

// 解析状态 → 标签配色（对齐后端 resume.status）
const STATUS_TAG_CLASS: Record<number, string> = {
  0: 'bg-[#FFF8E6] text-[#BF8700]',
  1: 'bg-[#ECFDF3] text-[#2DA44E]',
  2: 'bg-[#FFF0F1] text-[#CF222E]',
};

const InterviewPage = () => {
  const [step, setStep] = useState<StepIndex>(0);
  const [analysisStepIdx, setAnalysisStepIdx] = useState(0);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedResumeId, setSelectedResumeId] = useState<number | null>(null);
  const [resumes, setResumes] = useState<ApiResume[]>([]);
  const [resumesLoading, setResumesLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  // 设备检测状态
  const [micState, setMicState] = useState<DeviceState>('idle');
  const [camState, setCamState] = useState<DeviceState>('idle');
  const [volumeBars, setVolumeBars] = useState<number[]>(() => Array(20).fill(8));

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const volumeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const navigate = useNavigate();
  const { message, modal } = App.useApp();
  const { startInterview } = useAppStore();

  // 组件卸载时释放摄像头/麦克风资源
  useEffect(() => {
    return () => {
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (volumeTimerRef.current) clearInterval(volumeTimerRef.current);
    };
  }, []);

  /** 拉取当前用户的简历列表（含解析状态，供选择/轮询） */
  const loadResumes = async () => {
    setResumesLoading(true);
    try {
      const res = await getResumes(1, 20);
      setResumes(res.items);
    } catch {
      message.error('加载简历列表失败');
    } finally {
      setResumesLoading(false);
    }
  };

  // 进入页面时拉取一次真实简历
  useEffect(() => {
    loadResumes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectResume = (id: number) => {
    setSelectedResumeId(id);
    setShowUpload(false);
  };

  const handleOpenUpload = () => {
    setShowUpload(true);
    setSelectedResumeId(null);
  };

  const handleCloseUpload = () => {
    setShowUpload(false);
  };

  /** 上传成功后刷新列表并自动选中新简历 */
  const handleResumeUploaded = async () => {
    message.success('简历上传成功');
    await loadResumes();
  };

  /** 删除简历（后端软删+联动清理） */
  const handleDeleteResume = (resume: ApiResume) => {
    modal.confirm({
      title: '确定要删除这份简历吗？',
      content: '删除后不可恢复，且需重新上传才能再次使用',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteResume(resume.id);
          message.success('简历已删除');
          if (selectedResumeId === resume.id) setSelectedResumeId(null);
          await loadResumes();
        } catch {
          message.error('删除简历失败，请重试');
        }
      },
    });
  };

  /** 对解析失败的简历一键重试 */
  const handleRetryResume = async (resume: ApiResume) => {
    try {
      await retryResume(resume.id);
      message.success('已重新分析，请稍候');
      await loadResumes();
    } catch {
      message.error('重试失败，请稍后重试');
    }
  };

  /** 新上传但仍在解析中的简历：轮询状态直到就绪/失败（蓝图§3.5 面试模块进度） */
  useEffect(() => {
    if (!showUpload) return;
    const hasParsing = resumes.some((r) => r.status === 0);
    if (!hasParsing) return;
    const timer = setInterval(loadResumes, 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showUpload, resumes]);

  const canProceed = !showUpload && selectedResumeId !== null;

  // STEP 1 -> STEP 2: 触发 AI 分析动画（简历已就绪才可进入）
  const handleGenerate = async () => {
    if (!selectedResumeId) {
      message.warning('请先选择一份简历');
      return;
    }
    setGenerating(true);
    await new Promise((r) => setTimeout(r, 600));
    setGenerating(false);
    setStep(1);
    setAnalysisStepIdx(0);
  };

  // STEP 2: 分析中动画推进，四个子步骤跑完后直接进入设备检测
  useEffect(() => {
    if (step !== 1) return;
    if (analysisStepIdx >= ANALYSIS_STEPS.length) {
      const t = setTimeout(() => {
        setStep(2);
      }, 600);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => {
      setAnalysisStepIdx((i) => i + 1);
    }, 1400);
    return () => clearTimeout(t);
  }, [step, analysisStepIdx]);

  // STEP 3: 麦克风检测
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

  // STEP 3: 摄像头检测
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

  // STEP 3 -> 面试间
  const handleStart = () => {
    startInterview(selectedResumeId ? String(selectedResumeId) : 'resume_1', mockQuestions);
    navigate(`/dashboard/interview/session/${Date.now()}`);
  };

  const deviceCardClass = (s: DeviceState) =>
    `bg-[#F6F8FA] border-2 rounded-2xl p-6 text-center transition-all duration-300 ${
      s === 'ready' ? 'border-[#2DA44E]' : s === 'error' ? 'border-[#CF222E]' : s === 'testing' ? 'border-[#BF8700]' : 'border-[#E1E4E8]'
    }`;

  const deviceStatusText = (s: DeviceState, label: { idle: string; testing: string; ready: string; error: string }) =>
    label[s];

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="flex items-center gap-3 mb-5">
          <button
            onClick={() => navigate('/dashboard')}
            className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-xl font-bold text-[#0D1117]">AI 模拟面试</h1>
        </div>

        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-4 mb-5">
          <Steps
            current={step}
            items={[
              { title: '选择简历' },
              { title: 'AI 分析' },
              { title: '设备检测' },
            ]}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {/* ============ STEP 1: 选择简历 ============ */}
        {step === 0 && (
          <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-3">
              <FileTextOutlined className="text-[#FF6B35]" />
              <h2 className="text-base font-bold text-[#0D1117]">已有简历</h2>
              {resumes.length > 0 && (
                <span className="text-xs text-[#8B949E] ml-auto">{resumes.length} 份</span>
              )}
            </div>

            {resumesLoading && resumes.length === 0 ? (
              <div className="flex justify-center py-8">
                <LoadingOutlined className="text-2xl text-[#D0D7DE]" />
              </div>
            ) : resumes.length > 0 ? (
              <div className="border border-[#E1E4E8] rounded-xl overflow-hidden max-h-[240px] overflow-y-auto">
                {resumes.map((resume, idx) => {
                  const selected = selectedResumeId === resume.id && !showUpload;
                  return (
                    <div key={resume.id}>
                      {idx > 0 && <div className="border-t border-[#F0F2F5]" />}
                      <div
                        onClick={() => resume.status === 1 && handleSelectResume(resume.id)}
                        className={`flex items-center gap-4 px-5 py-4 transition-colors ${
                          resume.status === 1 ? 'cursor-pointer' : 'cursor-default'
                        } ${selected ? 'bg-[#FFF3ED]' : resume.status === 1 ? 'hover:bg-[#F6F8FA]' : ''}`}
                      >
                        <div
                          className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                            selected ? 'border-[#FF6B35] bg-[#FF6B35]' : 'border-[#D0D7DE]'
                          }`}
                        >
                          {selected && <CheckOutlined className="text-white text-[10px]" />}
                        </div>
                        <div className="w-9 h-9 rounded-lg bg-[#FFF3ED] flex items-center justify-center flex-shrink-0">
                          <FileTextOutlined className="text-[#FF6B35] text-base" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-[#0D1117] truncate">{resume.file_name}</p>
                          <p className="text-xs text-[#8B949E] mt-0.5">
                            {new Date(resume.created_at).toLocaleDateString('zh-CN', {
                              year: 'numeric',
                              month: '2-digit',
                              day: '2-digit',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </p>
                        </div>
                        <span
                          className={`text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${STATUS_TAG_CLASS[resume.status] ?? ''}`}
                        >
                          {RESUME_STATUS_LABEL[resume.status] ?? '未知'}
                        </span>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {resume.status === 2 && (
                            <button
                              onClick={() => handleRetryResume(resume)}
                              className="w-7 h-7 rounded-lg bg-white border border-[#E1E4E8] flex items-center justify-center hover:border-[#BF8700] hover:text-[#BF8700] transition-colors"
                              title="重新分析"
                            >
                              <ReloadOutlined className="text-xs" />
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteResume(resume)}
                            className="w-7 h-7 rounded-lg bg-white border border-[#E1E4E8] flex items-center justify-center hover:border-[#CF222E] hover:text-[#CF222E] transition-colors"
                            title="删除简历"
                          >
                            <DeleteOutlined className="text-xs" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-5 mb-5">
                <div className="w-16 h-16 rounded-2xl bg-[#F6F8FA] flex items-center justify-center mx-auto mb-3">
                  <FileTextOutlined className="text-2xl text-[#D0D7DE]" />
                </div>
                <p className="text-sm text-[#8B949E]">还没有上传过简历</p>
              </div>
            )}

            {!showUpload ? (
              <>
                <div className="flex items-center gap-3 my-5">
                  <div className="flex-1 h-px bg-[#E1E4E8]" />
                  <span className="text-xs text-[#8B949E] flex-shrink-0">或者</span>
                  <div className="flex-1 h-px bg-[#E1E4E8]" />
                </div>
                <div
                  onClick={handleOpenUpload}
                  className="border-2 border-dashed border-[#E1E4E8] rounded-2xl p-8 text-center cursor-pointer hover:border-[#FF6B35] hover:bg-[#FFF3ED]/30 transition-all"
                >
                  <div className="w-12 h-12 rounded-full bg-[#F6F8FA] flex items-center justify-center mx-auto mb-2">
                    <PlusOutlined className="text-[#8B949E]" />
                  </div>
                  <p className="text-sm font-medium text-[#0D1117] mb-1">上传一份新简历</p>
                  <p className="text-xs text-[#8B949E]">支持 PDF、Word、图片格式，不超过 10MB</p>
                </div>
              </>
            ) : (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <h3 className="text-sm font-bold text-[#0D1117]">上传新简历</h3>
                  <button
                    onClick={handleCloseUpload}
                    className="text-xs text-[#8B949E] hover:text-[#FF6B35] ml-auto transition-colors"
                  >
                    取消
                  </button>
                </div>
                <FileUpload
                  fileType="resume"
                  onUploaded={handleResumeUploaded}
                  onError={(msg) => message.error(msg)}
                />
              </div>
            )}

            <button
              onClick={handleGenerate}
              disabled={generating || !canProceed}
              className={`btn-flame btn-flame-lg mt-5 w-full ${!canProceed ? '!opacity-50 !cursor-not-allowed' : ''}`}
            >
              {generating ? (
                <span className="inline-flex items-center gap-2">
                  <LoadingOutlined /> AI 正在解析简历...
                </span>
              ) : (
                '开始生成面试题'
              )}
            </button>
          </div>
        )}

        {/* ============ STEP 2: AI 分析中 ============ */}
        {step === 1 && (
          <div className="bg-white border border-[#E1E4E8] rounded-2xl p-10 text-center">
            <div className="w-16 h-16 mx-auto mb-5 rounded-full border-4 border-[#F0F2F5] border-t-[#FF6B35] animate-spin" />
            <h2 className="text-lg font-bold text-[#0D1117] mb-2">AI 正在分析你的简历...</h2>
            <p className="text-sm text-[#5F6B7A] mb-6">正在解析简历并生成个性化面试题，请稍候</p>
            <div className="flex flex-col gap-2.5 max-w-sm mx-auto">
              {ANALYSIS_STEPS.map((label, i) => {
                const isDone = i < analysisStepIdx;
                const isCurrent = i === analysisStepIdx;
                return (
                  <div
                    key={label}
                    className={`flex items-center gap-3 text-sm px-3 py-2 rounded-lg bg-[#F6F8FA] transition-colors ${
                      isDone ? 'text-[#2DA44E]' : isCurrent ? 'text-[#FF6B35] font-semibold' : 'text-[#5F6B7A]'
                    }`}
                  >
                    <span
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        isDone ? 'bg-[#2DA44E]' : isCurrent ? 'bg-[#FF6B35] animate-pulse' : 'bg-[#E1E4E8]'
                      }`}
                    />
                    {label}
                    {isDone && <CheckOutlined className="ml-auto text-xs" />}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ============ STEP 3: 设备检测 ============ */}
        {step === 2 && (
          <div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              {/* 麦克风检测 */}
              <div className={deviceCardClass(micState)}>
                <div className="text-4xl mb-3 text-[#5F6B7A]">
                  <AudioOutlined />
                </div>
                <div className="text-[15px] font-bold text-[#0D1117] mb-1">麦克风检测</div>
                <div
                  className={`text-[13px] mb-3 ${
                    micState === 'ready' ? 'text-[#2DA44E]' : micState === 'error' ? 'text-[#CF222E]' : 'text-[#5F6B7A]'
                  }`}
                >
                  {deviceStatusText(micState, {
                    idle: '等待检测',
                    testing: '正在检测...',
                    ready: '✅ 麦克风正常',
                    error: '❌ 无法访问麦克风，请检查权限',
                  })}
                </div>
                <div className="w-full h-[120px] rounded-xl bg-[#1a1a2e] flex items-center justify-center mb-3 overflow-hidden">
                  <div className="flex items-end justify-center gap-[3px] h-10 w-full px-4">
                    {volumeBars.map((h, i) => (
                      <div
                        key={i}
                        className="w-1 rounded-sm transition-all duration-100"
                        style={{
                          height: `${h}px`,
                          background: micState === 'ready' ? '#2DA44E' : '#E1E4E8',
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
                <div className="text-4xl mb-3 text-[#5F6B7A]">
                  <VideoCameraOutlined />
                </div>
                <div className="text-[15px] font-bold text-[#0D1117] mb-1">摄像头检测</div>
                <div
                  className={`text-[13px] mb-3 ${
                    camState === 'ready' ? 'text-[#2DA44E]' : camState === 'error' ? 'text-[#CF222E]' : 'text-[#5F6B7A]'
                  }`}
                >
                  {deviceStatusText(camState, {
                    idle: '等待检测',
                    testing: '正在检测...',
                    ready: '✅ 摄像头正常',
                    error: '❌ 无法访问摄像头，请检查权限',
                  })}
                </div>
                <div className="w-full h-[120px] rounded-xl bg-[#1a1a2e] flex items-center justify-center mb-3 overflow-hidden">
                  <video
                    ref={videoRef}
                    autoPlay
                    muted
                    playsInline
                    className="w-full h-full object-cover rounded-xl"
                    style={{ display: camState === 'ready' ? 'block' : 'none' }}
                  />
                  {camState !== 'ready' && (
                    <span className="text-[#666] text-xs">摄像头预览</span>
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

            <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 text-center">
              <p className="text-sm text-[#5F6B7A] mb-3">
                面试将以<strong className="text-[#0D1117]">语音回答</strong>为主，请确保麦克风正常工作
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

export default InterviewPage;
