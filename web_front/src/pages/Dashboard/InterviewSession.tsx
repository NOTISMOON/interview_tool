import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Progress, App, Input } from 'antd';
import {
  ClockCircleOutlined,
  SendOutlined,
  ArrowLeftOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { useAppStore } from '@/store';
import { mockReport } from '@/mocks/data';
import { QUESTION_TYPE_LABEL } from '@/types';

const { TextArea } = Input;
const QUESTION_TIME = 120;

const InterviewSession = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { currentInterview, submitAnswer, completeInterview, nextQuestion } = useAppStore();

  const [timeLeft, setTimeLeft] = useState(QUESTION_TIME);
  const [answer, setAnswer] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const questions = currentInterview?.questions || [];
  const currentIndex = currentInterview?.currentQuestionIndex || 0;
  const currentQuestion = questions[currentIndex];
  const isLastQuestion = currentIndex === questions.length - 1;
  const progress = questions.length > 0 ? (currentIndex / questions.length) * 100 : 0;

  useEffect(() => {
    if (!currentInterview) {
      navigate('/dashboard/interview', { replace: true });
      return;
    }
    setTimeLeft(QUESTION_TIME);
    setAnswer('');
  }, [currentIndex]);

  useEffect(() => {
    if (timeLeft <= 0) return;
    const timer = setInterval(() => setTimeLeft((p) => (p <= 1 ? 0 : p - 1)), 1000);
    return () => clearInterval(timer);
  }, [timeLeft, currentIndex]);

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const handleSubmit = useCallback(async () => {
    if (!answer.trim()) { message.warning('请输入你的回答'); return; }
    if (!currentQuestion) return;
    setSubmitting(true);
    submitAnswer(currentQuestion.id, answer);
    if (isLastQuestion) {
      await new Promise((r) => setTimeout(r, 1000));
      completeInterview(mockReport);
      setSubmitting(false);
      navigate(`/dashboard/report/${id}`, { replace: true });
    } else {
      await new Promise((r) => setTimeout(r, 500));
      nextQuestion();
      setSubmitting(false);
    }
  }, [answer, isLastQuestion, currentQuestion]);

  if (!currentQuestion) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingOutlined className="text-2xl text-[#FF6B35]" />
      </div>
    );
  }

  return (
    <div className="max-w-[800px]">
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={() => navigate('/dashboard/interview')}
          className="w-9 h-9 rounded-lg border border-[#E1E4E8] flex items-center justify-center text-[#5F6B7A] hover:text-[#0D1117] hover:border-[#0D1117] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <div className="flex items-center gap-4">
          <span className="text-sm text-[#5F6B7A]">{currentIndex + 1} / {questions.length}</span>
          <span className="tag tag-flame">{QUESTION_TYPE_LABEL[currentQuestion.questionType]}</span>
          <span className={`text-sm font-mono font-semibold ${timeLeft < 30 ? 'text-[#CF222E]' : 'text-[#5F6B7A]'}`}>
            <ClockCircleOutlined className="mr-1" />{formatTime(timeLeft)}
          </span>
        </div>
      </div>

      <Progress percent={Math.round(progress)} showInfo={false} strokeColor="#FF6B35" trailColor="#E1E4E8" className="mb-6" />

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 mb-4">
        <div className="mb-3">
          <span className="tag tag-flame">第 {currentQuestion.questionNo} 题</span>
        </div>
        <p className="text-[15px] leading-relaxed text-[#0D1117]">{currentQuestion.questionText}</p>
      </div>

      <div className="bg-white border border-[#E1E4E8] rounded-2xl p-6 mb-4">
        <h4 className="text-sm font-semibold text-[#0D1117] mb-3">你的回答</h4>
        <TextArea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="在此输入你的回答..."
          autoSize={{ minRows: 4, maxRows: 10 }}
          className="!rounded-xl !text-sm"
          disabled={submitting}
          autoFocus
          onPressEnter={(e) => { if (e.ctrlKey || e.metaKey) handleSubmit(); }}
        />
        <p className="text-xs text-[#8B949E] mt-2">
          {timeLeft === 0 ? <span className="text-[#CF222E]">时间到，请尽快提交</span> : 'Ctrl + Enter 快速提交'}
        </p>
      </div>

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="btn-flame btn-flame-lg w-full"
        style={isLastQuestion ? { background: '#2DA44E' } : undefined}
      >
        {submitting ? (
          <><LoadingOutlined /> 提交中...</>
        ) : isLastQuestion ? (
          '提交并查看报告'
        ) : (
          <>下一题（{currentIndex + 1}/{questions.length}）</>
        )}
      </button>
    </div>
  );
};

export default InterviewSession;