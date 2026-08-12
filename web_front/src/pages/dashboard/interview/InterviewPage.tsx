import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Steps, Upload, Button, App } from 'antd';
import {
  InboxOutlined,
  ArrowLeftOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import type { UploadProps, UploadFile } from 'antd';
import { useAppStore } from '@/store';
import { mockQuestions } from '@/lib/mocks/data';

const { Dragger } = Upload;

const InterviewPage = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [generating, setGenerating] = useState(false);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { addResume, startInterview } = useAppStore();

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

  const handleGenerate = async () => {
    if (fileList.length === 0) {
      message.warning('请先上传简历');
      return;
    }
    setGenerating(true);
    addResume({
      id: `resume_${Date.now()}`,
      fileName: fileList[0].name,
      uploadTime: new Date().toISOString(),
      status: 'ready',
    });
    await new Promise((r) => setTimeout(r, 2000));
    setGenerating(false);
    setCurrentStep(1);
  };

  const handleStart = () => {
    startInterview('resume_1', mockQuestions);
    navigate(`/dashboard/interview/session/${Date.now()}`);
  };

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/dashboard')}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#0D1117]">AI 模拟面试</h1>
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 mb-6">
        <Steps
          current={currentStep}
          items={[
            { title: '上传简历' },
            { title: '生成题目' },
            { title: '开始面试' },
          ]}
        />
      </div>

      {currentStep === 0 && (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-8">
          <Dragger
            {...uploadProps}
            className="!bg-transparent !border-dashed !border-[#E1E4E8] !rounded-xl hover:!border-[#FF6B35]"
          >
            <p className="text-4xl mb-3">
              <InboxOutlined className="text-[#FF6B35]" />
            </p>
            <p className="text-base font-medium text-[#0D1117] mb-1">点击或拖拽简历文件上传</p>
            <p className="text-sm text-[#8B949E]">支持 PDF、Word、图片格式，不超过 10MB</p>
          </Dragger>
          <div className="mt-6">
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="btn-flame btn-flame-lg w-full"
            >
              {generating ? 'AI 正在解析简历...' : '开始生成面试题'}
            </button>
          </div>
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
  );
};

export default InterviewPage;