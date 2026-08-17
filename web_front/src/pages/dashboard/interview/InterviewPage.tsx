import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Steps, Upload, App } from 'antd';
import {
  InboxOutlined,
  ArrowLeftOutlined,
  ThunderboltOutlined,
  FileTextOutlined,
  PlusOutlined,
  CheckOutlined,
  AudioOutlined,
  VideoCameraOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import type { UploadProps, UploadFile } from 'antd';
import { useAppStore } from '@/store';
import { mockQuestions } from '@/lib/mocks/data';

const { Dragger } = Upload;

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

const InterviewPage = () => {
  const [step, setStep] = useState<StepIndex>(0);
  const [analysisStepIdx, setAnalysisStepIdx] = useState(0);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedResumeId, setSelectedResumeId] = useState<string | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
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
  const { resumes, addResume, startInterview } = useAppStore();

  // 组件卸载时释放摄像头/麦克风资源
  useEffect(() => {
    return () => {
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (volumeTimerRef.current) clearInterval(volumeTimerRef.current);
    };
  }, []);

  const uploadProps: UploadProps = {
    name: 'resume',
    multiple: false,
    fileList,
    accept: '.pdf,.doc,.docx,.png,.jpg,.jpeg',
    beforeUpload: (file) => {
      if (file.size / 1024 / 1024 > 10) {
        message.error('文件大小不能超过 10MB');
        return Upload.LIST_IGNORE;
      }
      setFileList([file]);
      return false;
    },
    onRemove: () => setFileList([]),
  };

  const handleSelectResume = (id: string) => {
    setSelectedResumeId(id);
    setShowUpload(false);
    setFileList([]);
  };

  const handleOpenUpload = () => {
    setShowUpload(true);
    setSelectedResumeId(null);
  };

  const handleCloseUpload = () => {
    setShowUpload(false);
    setFileList([]);
  };

  const canProceed = showUpload ? fileList.length > 0 : selectedResumeId !== null;

  // STEP 1 -> STEP 2: 触发 AI 分析动画
  const handleGenerate = async () => {
    if (showUpload && fileList.length === 0) {
      message.warning('请先上传简历');
      return;
    }
    if (!showUpload && !selectedResumeId) {
      message.warning('请先选择一份简历');
      return;
    }

    setGenerating(true);
    if (showUpload) {
      addResume({
        id: `resume_${Date.now()}`,
        fileName: fileList[0].name,
        uploadTime: new Date().toISOString(),
        status: 'ready',
      });
    }

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
    startInterview(selectedResumeId || 'resume_1', mockQuestions);
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

            {resumes.length > 0 ? (
              <div className="border border-[#E1E4E8] rounded-xl overflow-hidden max-h-[240px] overflow-y-auto">
                {resumes.map((resume, idx) => {
                  const selected = selectedResumeId === resume.id && !showUpload;
                  return (
                    <div key={resume.id}>
                      {idx > 0 && <div className="border-t border-[#F0F2F5]" />}
                      <div
                        onClick={() => handleSelectResume(resume.id)}
                        className={`flex items-center gap-4 px-5 py-4 cursor-pointer transition-colors ${
                          selected ? 'bg-[#FFF3ED]' : 'hover:bg-[#F6F8FA]'
                        }`}
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
                          <p className="text-sm font-medium text-[#0D1117] truncate">{resume.fileName}</p>
                          <p className="text-xs text-[#8B949E] mt-0.5">
                            {new Date(resume.uploadTime).toLocaleDateString('zh-CN', {
                              year: 'numeric',
                              month: '2-digit',
                              day: '2-digit',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </p>
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
                <Dragger
                  {...uploadProps}
                  className="!bg-transparent !border-dashed !border-[#E1E4E8] !rounded-xl hover:!border-[#FF6B35]"
                >
                  <p className="text-3xl mb-2">
                    <InboxOutlined className="text-[#FF6B35]" />
                  </p>
                  <p className="text-sm font-medium text-[#0D1117] mb-0.5">点击或拖拽简历文件到此处</p>
                  <p className="text-xs text-[#8B949E]">支持 PDF、Word、图片格式，不超过 10MB</p>
                </Dragger>
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
