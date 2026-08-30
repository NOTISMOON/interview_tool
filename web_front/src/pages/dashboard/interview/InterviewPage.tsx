import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import App from 'antd/es/app';
import {
  ArrowLeftOutlined,
  FileTextOutlined,
  PlusOutlined,
  CheckOutlined,
  LoadingOutlined,
  DeleteOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
} from '@/components/icons';
import { FileUpload } from '@/components/upload/FileUpload';
import {
  getResumes,
  deleteResume,
  retryResume,
  RESUME_STATUS_LABEL,
} from '@/lib/api/resume';
import type { ApiResume } from '@/lib/api/resume';
import { createInterview, extractConflict } from '@/lib/api/interview';
import type { InterviewType } from '@/lib/api/interview';

/** 面试类型选项（对齐后端 type：1-完整 15题 / 2-快速 9题，均覆盖四维度） */
const TYPE_OPTIONS: { value: InterviewType; title: string; desc: string }[] = [
  { value: 1, title: '完整面试', desc: '15 题 · 约 40-70 分钟' },
  { value: 2, title: '快速面试', desc: '9 题 · 约 25-40 分钟' },
];

/** AI 分析的四个子步骤文案 */
const ANALYSIS_STEPS = [
  '提取简历关键信息',
  '分析技术栈与项目经验',
  '生成个性化面试题目',
  '构建面试者能力画像',
];

// 解析状态 → 标签配色（对齐后端 resume.status）
const STATUS_TAG_CLASS: Record<number, string> = {
  0: 'bg-[#FFF7E0] text-[#FFAA00]',
  1: 'bg-[#F7EBD3] text-[#00B578]',
  2: 'bg-[#FDECEC] text-[#F53535]',
};

const InterviewPage = () => {
  const [showUpload, setShowUpload] = useState(false);
  const [selectedResumeId, setSelectedResumeId] = useState<number | null>(null);
  const [interviewType, setInterviewType] = useState<InterviewType>(1);
  const [resumes, setResumes] = useState<ApiResume[]>([]);
  const [resumesLoading, setResumesLoading] = useState(false);
  /** generating=题目生成中（进入分析动画）；done=生成完成待跳转；null=空闲 */
  const [genState, setGenState] = useState<'generating' | 'done' | null>(null);
  const [analysisStepIdx, setAnalysisStepIdx] = useState(0);
  const [createdInterviewId, setCreatedInterviewId] = useState<number | null>(null);

  const navigate = useNavigate();
  const { message, modal } = App.useApp();

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

  /** 新上传但仍在解析中的简历：轮询状态直到就绪/失败 */
  useEffect(() => {
    if (!showUpload) return;
    const hasParsing = resumes.some((r) => r.status === 0);
    if (!hasParsing) return;
    const timer = setInterval(loadResumes, 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showUpload, resumes]);

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

  const canProceed = !showUpload && selectedResumeId !== null;

  /** 开始生成面试题：成功后直接跳设备检测路由（不驻留、不劫持，草稿互不影响） */
  const handleGenerate = async () => {
    if (!selectedResumeId) {
      message.warning('请先选择一份简历');
      return;
    }
    setGenState('generating');
    setAnalysisStepIdx(0);
    try {
      const res = await createInterview(selectedResumeId, interviewType);
      setCreatedInterviewId(res.interview_id);
      setGenState('done');
    } catch (err) {
      setGenState(null);
      setCreatedInterviewId(null);
      const conflict = extractConflict(err);
      if (conflict?.code === 'analyzing') {
        message.warning('简历正在分析中，请稍后再试');
      } else if (conflict?.code === 'analysis_failed') {
        message.error('简历分析失败，请重试或重新上传');
      } else {
        message.error('面试创建失败（题目生成异常），请稍后重试');
      }
    }
  };

  // 生成完成 → 跳到独立设备检测路由（URL 带 interviewId，刷新/切页天然保持）
  useEffect(() => {
    if (genState === 'done' && createdInterviewId !== null) {
      navigate(`/dashboard/interview/device-check/${createdInterviewId}`, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [genState, createdInterviewId]);

  // 生成中动画推进（后台通知由后端兜底，用户切走也不丢）
  useEffect(() => {
    if (genState !== 'generating') return;
    if (analysisStepIdx >= ANALYSIS_STEPS.length) return;
    const t = setTimeout(() => {
      setAnalysisStepIdx((i) => i + 1);
    }, 1400);
    return () => clearTimeout(t);
  }, [genState, analysisStepIdx]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="flex items-center gap-3 mb-5">
          <button
            onClick={() => navigate('/dashboard')}
            className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-xl font-bold text-[#232529]">AI 模拟面试</h1>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {/* ============ 选择简历 + 生成面试题 ============ */}
        {genState === null && (
          <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-3">
              <FileTextOutlined className="text-[#D9A441]" />
              <h2 className="text-base font-bold text-[#232529]">已有简历</h2>
              {resumes.length > 0 && (
                <span className="text-xs text-[#999999] ml-auto">{resumes.length} 份</span>
              )}
            </div>

            {resumesLoading && resumes.length === 0 ? (
              <div className="flex justify-center py-8">
                <LoadingOutlined className="text-2xl text-[#E5E6EB]" />
              </div>
            ) : resumes.length > 0 ? (
              <div className="border border-[#E8E8E8] rounded-xl overflow-hidden max-h-[240px] overflow-y-auto">
                {resumes.map((resume, idx) => {
                  const selected = selectedResumeId === resume.id && !showUpload;
                  return (
                    <div key={resume.id}>
                      {idx > 0 && <div className="border-t border-[#F2F3F5]" />}
                      <div
                        onClick={() => resume.status === 1 && handleSelectResume(resume.id)}
                        className={`flex items-center gap-4 px-5 py-4 transition-colors ${
                          resume.status === 1 ? 'cursor-pointer' : 'cursor-default'
                        } ${selected ? 'bg-[#F7EBD3]' : resume.status === 1 ? 'hover:bg-[#F7F8FA]' : ''}`}
                      >
                        <div
                          className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                            selected ? 'border-[#D9A441] bg-[#D9A441]' : 'border-[#E5E6EB]'
                          }`}
                        >
                          {selected && <CheckOutlined className="text-white text-[10px]" />}
                        </div>
                        <div className="w-9 h-9 rounded-lg bg-[#F7EBD3] flex items-center justify-center flex-shrink-0">
                          <FileTextOutlined className="text-[#D9A441] text-base" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-[#232529] truncate">{resume.file_name}</p>
                          <p className="text-xs text-[#999999] mt-0.5">
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
                              className="w-7 h-7 rounded-lg bg-white border border-[#E8E8E8] flex items-center justify-center hover:border-[#FFAA00] hover:text-[#FFAA00] transition-colors"
                              title="重新分析"
                            >
                              <ReloadOutlined className="text-xs" />
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteResume(resume)}
                            className="w-7 h-7 rounded-lg bg-white border border-[#E8E8E8] flex items-center justify-center hover:border-[#F53535] hover:text-[#F53535] transition-colors"
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
                <div className="w-16 h-16 rounded-2xl bg-[#F7F8FA] flex items-center justify-center mx-auto mb-3">
                  <FileTextOutlined className="text-2xl text-[#E5E6EB]" />
                </div>
                <p className="text-sm text-[#999999]">还没有上传过简历</p>
              </div>
            )}

            {!showUpload ? (
              <>
                <div className="flex items-center gap-3 my-5">
                  <div className="flex-1 h-px bg-[#E8E8E8]" />
                  <span className="text-xs text-[#999999] flex-shrink-0">或者</span>
                  <div className="flex-1 h-px bg-[#E8E8E8]" />
                </div>
                <div
                  onClick={handleOpenUpload}
                  className="border-2 border-dashed border-[#E8E8E8] rounded-2xl p-8 text-center cursor-pointer hover:border-[#D9A441] hover:bg-[#F7EBD3]/30 transition-all"
                >
                  <div className="w-12 h-12 rounded-full bg-[#F7F8FA] flex items-center justify-center mx-auto mb-2">
                    <PlusOutlined className="text-[#999999]" />
                  </div>
                  <p className="text-sm font-medium text-[#232529] mb-1">上传一份新简历</p>
                  <p className="text-xs text-[#999999]">支持 PDF、Word、图片格式，不超过 10MB</p>
                </div>
              </>
            ) : (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <h3 className="text-sm font-bold text-[#232529]">上传新简历</h3>
                  <button
                    onClick={handleCloseUpload}
                    className="text-xs text-[#999999] hover:text-[#D9A441] ml-auto transition-colors"
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

            {/* 面试类型选择（对齐后端 type：1-完整 15题 / 2-快速 9题） */}
            <div className="grid grid-cols-2 gap-3 mt-5">
              {TYPE_OPTIONS.map((opt) => {
                const selected = interviewType === opt.value;
                return (
                  <button
                    key={opt.value}
                    onClick={() => setInterviewType(opt.value)}
                    className={`text-left px-4 py-3 rounded-xl border-2 transition-all ${
                      selected
                        ? 'border-[#D9A441] bg-[#F7EBD3]'
                        : 'border-[#E8E8E8] bg-white hover:border-[#E5E6EB]'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <ClockCircleOutlined className={selected ? 'text-[#D9A441]' : 'text-[#999999]'} />
                      <span className={`text-sm font-semibold ${selected ? 'text-[#D9A441]' : 'text-[#232529]'}`}>
                        {opt.title}
                      </span>
                      {selected && <CheckOutlined className="text-[#D9A441] text-xs ml-auto" />}
                    </div>
                    <p className="text-xs text-[#999999] mt-1">{opt.desc}</p>
                  </button>
                );
              })}
            </div>

            <button
              onClick={handleGenerate}
              disabled={!canProceed}
              className={`btn-flame btn-flame-lg mt-4 w-full ${!canProceed ? '!opacity-50 !cursor-not-allowed' : ''}`}
            >
                <span className="inline-flex items-center gap-2">
                <ThunderboltOutlined /> 开始生成面试题
                </span>
            </button>
          </div>
        )}

        {/* ============ 题目生成中（后台通知兜底，用户切走也不丢） ============ */}
        {genState === 'generating' && (
          <div className="bg-white border border-[#E8E8E8] rounded-2xl p-10 text-center">
            <div className="w-16 h-16 mx-auto mb-5 rounded-full border-4 border-[#F2F3F5] border-t-[#D9A441] animate-spin" />
            <h2 className="text-lg font-bold text-[#232529] mb-2">AI 正在分析你的简历...</h2>
            <p className="text-sm text-[#666666] mb-6">
              正在解析简历并生成个性化面试题，通常需要 5~20 秒
            </p>
            <div className="flex flex-col gap-2.5 max-w-sm mx-auto">
              {ANALYSIS_STEPS.map((label, i) => {
                const isDone = i < analysisStepIdx;
                const isCurrent = i === analysisStepIdx;
                return (
                  <div
                    key={label}
                    className={`flex items-center gap-3 text-sm px-3 py-2 rounded-lg bg-[#F7F8FA] transition-colors ${
                      isDone ? 'text-[#00B578]' : isCurrent ? 'text-[#D9A441] font-semibold' : 'text-[#666666]'
                    }`}
                  >
                    <span
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        isDone ? 'bg-[#00B578]' : isCurrent ? 'bg-[#D9A441] animate-pulse' : 'bg-[#E8E8E8]'
                      }`}
                    />
                    {label}
                    {isDone && <CheckOutlined className="ml-auto text-xs" />}
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-[#999999] mt-6">
              生成完成后将自动进入设备检测；若你离开了本页，可在消息中心或面试记录中找到该面试继续。
              </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default InterviewPage;
