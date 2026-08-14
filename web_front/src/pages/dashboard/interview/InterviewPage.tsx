import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Steps, Upload, App } from 'antd';
import {
  InboxOutlined,
  ArrowLeftOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  FileTextOutlined,
  PlusOutlined,
  CheckOutlined,
} from '@ant-design/icons';
import type { UploadProps, UploadFile } from 'antd';
import { useAppStore } from '@/store';
import { mockQuestions } from '@/lib/mocks/data';

const { Dragger } = Upload;

const InterviewPage = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedResumeId, setSelectedResumeId] = useState<string | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [generating, setGenerating] = useState(false);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { resumes, addResume, startInterview } = useAppStore();

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

    await new Promise((r) => setTimeout(r, 2000));
    setGenerating(false);
    setCurrentStep(1);
  };

  const handleStart = () => {
    startInterview(selectedResumeId || 'resume_1', mockQuestions);
    navigate(`/dashboard/interview/session/${Date.now()}`);
  };

  const canProceed = showUpload ? fileList.length > 0 : selectedResumeId !== null;

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0">
        <div className="flex items-center gap-4 mb-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-xl font-bold text-[#0D1117]">AI 模拟面试</h1>
        </div>

        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-4 mb-4">
          <Steps
            current={currentStep}
            items={[
              { title: '选择简历' },
              { title: '生成题目' },
              { title: '开始面试' },
            ]}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">

      {currentStep === 0 && (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <FileTextOutlined className="text-[#FF6B35]" />
            <h2 className="text-base font-bold text-[#0D1117]">已有简历</h2>
            {resumes.length > 0 && (
              <span className="text-xs text-[#8B949E] ml-auto">{resumes.length} 份</span>
            )}
          </div>

          {resumes.length > 0 ? (
            <div className="border border-[#E1E4E8] rounded-xl overflow-hidden max-h-[220px] overflow-y-auto">
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
                      <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                        selected
                          ? 'border-[#FF6B35] bg-[#FF6B35]'
                          : 'border-[#D0D7DE]'
                      }`}>
                        {selected && <CheckOutlined className="text-white text-[10px]" />}
                      </div>
                      <div className="w-9 h-9 rounded-lg bg-[#FFF3ED] flex items-center justify-center flex-shrink-0">
                        <FileTextOutlined className="text-[#FF6B35] text-base" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[#0D1117] truncate">
                          {resume.fileName}
                        </p>
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
              <div className="flex items-center gap-3 mb-5">
                <div className="flex-1 h-px bg-[#E1E4E8]" />
                <span className="text-xs text-[#8B949E] flex-shrink-0">或者</span>
                <div className="flex-1 h-px bg-[#E1E4E8]" />
              </div>

              <div
                onClick={handleOpenUpload}
                className="border-2 border-dashed border-[#E1E4E8] rounded-xl p-6 text-center cursor-pointer hover:border-[#FF6B35] hover:bg-[#FFF3ED]/30 transition-all"
              >
                <div className="w-10 h-10 rounded-full bg-[#F6F8FA] flex items-center justify-center mx-auto mb-2">
                  <PlusOutlined className="text-[#8B949E]" />
                </div>
                <p className="text-sm font-medium text-[#0D1117] mb-1">上传一份新简历</p>
                <p className="text-xs text-[#8B949E]">支持 PDF、Word、图片格式，不超过 10MB</p>
              </div>
            </>
          ) : (
            <div className="mb-8">
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
            className={`btn-flame btn-flame-lg mt-4 w-full ${
              !canProceed ? '!opacity-50 !cursor-not-allowed' : ''
            }`}
          >
            {generating ? (
              <span className="inline-flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                AI 正在解析简历...
              </span>
            ) : (
              '开始生成面试题'
            )}
          </button>
        </div>
      )}

      {currentStep === 1 && (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-8 text-center">
          <CheckCircleOutlined className="text-5xl text-[#2DA44E] mb-4" />
          <h2 className="text-xl font-bold text-[#0D1117] mb-2">题目生成完毕</h2>
          <p className="text-sm text-[#5F6B7A] mb-6">
            AI 已根据你的简历生成了 {mockQuestions.length} 道面试题
          </p>

          <div className="grid grid-cols-3 gap-4 mb-6 max-w-md mx-auto">
            <div className="bg-[#FFF3ED] rounded-xl p-4">
              <div className="text-xl font-bold text-[#FF6B35]">{mockQuestions.length}</div>
              <div className="text-xs text-[#5F6B7A]">总题数</div>
            </div>
            <div className="bg-[#F6F8FA] rounded-xl p-4">
              <div className="text-xl font-bold text-[#0D1117]">
                {mockQuestions.filter((q) => q.questionType === 'technical').length}
              </div>
              <div className="text-xs text-[#5F6B7A]">技术题</div>
            </div>
            <div className="bg-[#ECFDF3] rounded-xl p-4">
              <div className="text-xl font-bold text-[#2DA44E]">
                {mockQuestions.filter((q) => q.questionType === 'behavioral').length}
              </div>
              <div className="text-xs text-[#5F6B7A]">行为题</div>
            </div>
          </div>

          <div className="space-y-2 mb-6 max-w-md mx-auto">
            {mockQuestions.slice(0, 3).map((q) => (
              <div key={q.id} className="flex items-center gap-2 text-left bg-[#F6F8FA] rounded-xl p-3">
                <span className="tag tag-flame flex-shrink-0">
                  {q.questionType === 'technical' ? '技术' : q.questionType === 'behavioral' ? '行为' : '项目'}
                </span>
                <span className="text-xs text-[#0D1117] truncate">{q.questionText}</span>
              </div>
            ))}
          </div>

          <button onClick={handleStart} className="btn-flame btn-flame-lg">
            <ThunderboltOutlined /> 开始面试
          </button>
        </div>
      )}
      </div>
    </div>
  );
};

export default InterviewPage;